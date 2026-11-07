"""4 字节大端长度前缀 + UTF-8 载荷的帧编解码。"""

import struct

# 单帧上限。失步的字节流会把任意 4 个字节读成长度，不设上限就可能一直等
# 一个永远凑不齐的帧，缓冲反而越积越大。
MAX_FRAME_BYTES = 1 << 20


class FrameError(Exception):
    """字节流不符合帧格式。抛出后解码器内容不可信，调用方应 reset()。"""


def encode(text: str) -> bytes:
    payload = text.encode("utf-8")
    return struct.pack(">I", len(payload)) + payload


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
