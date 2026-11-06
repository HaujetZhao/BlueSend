"""4 字节大端长度前缀 + UTF-8 载荷的帧编解码。"""

import struct


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
            if len(self._buf) < 4 + length:
                break
            out.append(bytes(self._buf[4:4 + length]).decode("utf-8"))
            del self._buf[:4 + length]
        return out

    def reset(self) -> None:
        self._buf.clear()
