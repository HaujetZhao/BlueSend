"""4 字节大端长度前缀 + UTF-8 载荷的帧编解码。"""

import logging
import struct
import threading

# 单帧上限。失步的字节流会把任意 4 个字节读成长度，不设上限就可能一直等
# 一个永远凑不齐的帧，缓冲反而越积越大。
MAX_FRAME_BYTES = 1 << 20


class FrameError(Exception):
    """字节流不符合帧格式。抛出后解码器内容不可信，调用方应 reset()。"""


def encode(text: str) -> bytes:
    payload = text.encode("utf-8")
    return struct.pack(">I", len(payload)) + payload


class UplinkAssembler:
    """上行分片重组：每片 4 字节大端序号前缀，按序号还原字节流再交给解码器。

    乱序不出在空中（链路层按序可靠），出在电脑侧——WinRT 写回调跑在线程池上，
    并发回调投递的字节顺序会颠倒（实测 517 片三轮坏一次，等长交换、帧边界
    完好、内容错位）。跳变时记 warning，与测速哈希金丝雀互补：这里频发说明
    乱序源在电脑回调；这里安静但哈希仍失败，说明乱序源在手机侧协议栈。
    """

    def __init__(self, submit) -> None:
        self._submit = submit
        self._lock = threading.Lock()
        self._next = 0
        self._pending: dict[int, bytes] = {}

    def reset(self) -> None:
        # 连接边界＝帧边界：旧连接的半帧与乱序片都不能带进新连接。
        with self._lock:
            self._next = 0
            self._pending.clear()

    def feed(self, chunk: bytes) -> None:
        if len(chunk) < 4:
            raise FrameError(f"上行分片只有 {len(chunk)} 字节，容不下序号前缀")
        seq = int.from_bytes(chunk[:4], "big")
        with self._lock:
            if seq < self._next:
                return  # 重复投递，丢
            if seq > self._next:
                logging.getLogger("ble").warning(
                    "上行分片乱序：期望 %d 收到 %d，等待补洞", self._next, seq,
                )
            self._pending[seq] = chunk[4:]
            while self._next in self._pending:
                self._submit(self._pending.pop(self._next))
                self._next += 1


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
