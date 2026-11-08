"""4 字节大端长度前缀 + UTF-8 载荷的帧编解码。"""

import logging
import struct
import threading
import time

# 单帧上限。失步的字节流会把任意 4 个字节读成长度，不设上限就可能一直等
# 一个永远凑不齐的帧，缓冲反而越积越大。
MAX_FRAME_BYTES = 1 << 20

# 上行片头的两段位宽。消息 ID 在连接内自增、16 位回绕；片序号上限 65535，
# 512 字节分片对应约 33 MB，最低 MTU 的 20 字节分片也对应约 1 MB，远大于
# 实际最大消息（测速 256 KB）。
MAX_MESSAGE_ID = 0x10000


class FrameError(Exception):
    """字节流不符合帧格式。抛出后解码器内容不可信，调用方应 reset()。"""


def encode(text: str) -> bytes:
    payload = text.encode("utf-8")
    return struct.pack(">I", len(payload)) + payload


class UplinkAssembler:
    """上行分片重组：每片头 2 字节消息 ID + 2 字节片序号。

    消息之间按 ID 顺序提交——上屏顺序不能乱；消息内部按片序号拼接。某条
    消息缺片只影响它自己：在途缓冲里其他消息照常收，等它超时被丢弃后，
    后面的消息继续提交，不会因为一个缺口把整条链路卡死。乱序不出在空中
    （链路层按序可靠），出在电脑侧——WinRT 写回调跑在线程池上，并发回调
    投递的字节顺序会颠倒（实测 517 片三轮坏一次，帧边界完好、内容错位）。
    不完整的消息根本到不了解码器，连接边界处的半帧问题也随之消失。
    """

    def __init__(self, submit) -> None:
        # submit 收到 bytes 表示一条完整的消息，收到 None 表示对端开了新流：
        # 下游的解码器必须丢掉手里的半帧。
        self._submit = submit
        self._lock = threading.Lock()
        self._next_id = 0
        # msg_id -> [最后一片到达时刻, {片序号: 载荷}]
        self._inflight: dict[int, list] = {}
        self._last_activity = time.monotonic()

    def reset(self) -> None:
        # 连接边界＝帧边界：旧连接的半帧与乱序片都不能带进新连接。
        with self._lock:
            self._next_id = 0
            self._inflight.clear()
            self._last_activity = time.monotonic()

    def feed(self, chunk: bytes) -> None:
        if len(chunk) < 4:
            raise FrameError(f"上行分片只有 {len(chunk)} 字节，容不下 4 字节片头")
        msg_id = int.from_bytes(chunk[0:2], "big")
        frag = int.from_bytes(chunk[2:4], "big")
        now = time.monotonic()
        with self._lock:
            # 手机端每条连接从消息 0 开始编号。收到 0 而已经在等更大的 ID，
            # 说明对端换了流（订阅事件可能漏报），就地重同步。
            if msg_id == 0 and self._next_id != 0:
                self._next_id = 0
                self._inflight.clear()
                self._submit(None)
            if msg_id < self._next_id:
                return  # 已提交消息的迟到片，丢
            entry = self._inflight.get(msg_id)
            if entry is None:
                entry = [now, {}]
                self._inflight[msg_id] = entry
            entry[0] = now
            entry[1][frag] = chunk[4:]
            self._last_activity = now
            self._drain()

    def expire(self, timeout: float) -> None:
        """丢弃停滞超时的消息，让后面的消息继续提交。

        手机端串行发送（前一条的最后一片等 ATT 应答才发下一条），所以队首
        缺片就是真的缺了，不会再有补片。整条链路安静超过 timeout 才跳过，
        避免把还在回调队列里排队的片误判成丢失。
        """
        with self._lock:
            now = time.monotonic()
            while self._inflight:
                entry = self._inflight.get(self._next_id)
                if entry is None:
                    # 队首这一条一片都没到（全丢，或对端换了序号起点）。
                    if now - self._last_activity < timeout:
                        return
                    self._next_id = min(self._inflight)
                    continue
                if self._extract(entry[1]) is not None:
                    self._drain()
                    continue
                if now - entry[0] < timeout:
                    return
                logging.getLogger("ble").warning(
                    "上行消息 %d 缺失分片，已丢弃", self._next_id,
                )
                del self._inflight[self._next_id]
                self._next_id = (self._next_id + 1) % MAX_MESSAGE_ID

    def _drain(self) -> None:
        while True:
            entry = self._inflight.get(self._next_id)
            if entry is None:
                return
            data = self._extract(entry[1])
            if data is None:
                return
            del self._inflight[self._next_id]
            self._next_id = (self._next_id + 1) % MAX_MESSAGE_ID
            self._submit(data)

    @staticmethod
    def _extract(chunks: dict[int, bytes]) -> bytes | None:
        """凑齐返回整条消息，否则返回 None。片数由片 0 里的帧长度算出。"""
        head = chunks.get(0)
        if head is None or len(head) < 4:
            return None  # 片 0 没到，连帧多长都不知道
        total = 4 + int.from_bytes(head[:4], "big")
        size = len(head)
        count = (total + size - 1) // size
        if len(chunks) < count:
            return None
        try:
            data = b"".join(chunks[i] for i in range(count))
        except KeyError:
            return None
        return data[:total]


class Decoder:
    def __init__(self) -> None:
        self._buf = bytearray()

    def feed(self, chunk: bytes) -> list[str]:
        self._buf.extend(chunk)
        out: list[str] = []
        while len(self._buf) >= 4:
            (length,) = struct.unpack(">I", self._buf[:4])
            if length > MAX_FRAME_BYTES:
                raise FrameError(f"帧长度 {length} 超过上限 {MAX_FRAME_BYTES}")
            if len(self._buf) < 4 + length:
                break
            payload = self._buf[4:4 + length]
            try:
                text = payload.decode("utf-8")
            except UnicodeDecodeError as err:
                raise FrameError(f"载荷不是合法 UTF-8：{err}") from err
            del self._buf[:4 + length]
            out.append(text)
        return out

    def reset(self) -> None:
        self._buf.clear()
