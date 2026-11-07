import struct

import pytest

from core.frame_codec import (
    MAX_FRAME_BYTES,
    Decoder,
    FrameError,
    UplinkAssembler,
    encode,
)


def test_encode_prefixes_length():
    assert encode("你好") == b"\x00\x00\x00\x06" + "你好".encode()


def test_single_frame():
    assert Decoder().feed(encode("hello")) == ["hello"]


def test_frame_split_across_chunks():
    d = Decoder()
    frame = encode("跨包消息")
    assert d.feed(frame[:3]) == []
    assert d.feed(frame[3:7]) == []
    assert d.feed(frame[7:]) == ["跨包消息"]


def test_multiple_frames_in_one_chunk():
    d = Decoder()
    assert d.feed(encode("a") + encode("bb") + encode("ccc")) == ["a", "bb", "ccc"]


def test_frame_boundary_between_messages():
    d = Decoder()
    data = encode("第一") + encode("第二")
    assert d.feed(data[:10]) == ["第一"]
    assert d.feed(data[10:]) == ["第二"]


def test_empty_and_multiline():
    d = Decoder()
    assert d.feed(encode("") + encode("第一行\n第二行")) == ["", "第一行\n第二行"]


def test_long_utf8_message():
    text = "长" * 1000
    frame = encode(text)
    d = Decoder()
    out = []
    for i in range(0, len(frame), 20):
        out += d.feed(frame[i:i + 20])
    assert out == [text]


def test_invalid_utf8_payload_is_rejected():
    d = Decoder()
    with pytest.raises(FrameError):
        d.feed(b"\x00\x00\x00\x02\xff\xfe")


def test_oversized_length_is_rejected():
    d = Decoder()
    with pytest.raises(FrameError):
        d.feed(struct.pack(">I", MAX_FRAME_BYTES + 1))


def test_reset_recovers_from_half_frame():
    d = Decoder()
    half = encode("旧连接的半帧")[:7]
    assert d.feed(half) == []
    d.reset()
    assert d.feed(encode("新连接")) == ["新连接"]


def _chunk(seq: int, body: bytes) -> bytes:
    return seq.to_bytes(4, "big") + body


def test_assembler_orders_swapped_chunks():
    out = []
    a = UplinkAssembler(out.append)
    # 回调线程并发投递：1 先到、0 补洞，还原后顺序不能反。
    a.feed(_chunk(1, b"world"))
    a.feed(_chunk(0, b"hello"))
    a.feed(_chunk(2, b"!"))
    assert out == [b"hello", b"world", b"!"]


def test_assembler_holds_gap_until_filled():
    out = []
    a = UplinkAssembler(out.append)
    a.feed(_chunk(0, b"a"))
    a.feed(_chunk(2, b"c"))
    assert out == [b"a"]
    a.feed(_chunk(1, b"b"))
    assert out == [b"a", b"b", b"c"]


def test_assembler_drops_duplicate():
    out = []
    a = UplinkAssembler(out.append)
    a.feed(_chunk(0, b"a"))
    a.feed(_chunk(0, b"a"))
    assert out == [b"a"]


def test_assembler_reset_discards_pending():
    out = []
    a = UplinkAssembler(out.append)
    a.feed(_chunk(1, b"stale"))
    a.reset()
    a.feed(_chunk(0, b"fresh"))
    assert out == [b"fresh"]


def test_assembler_rejects_short_chunk():
    a = UplinkAssembler(lambda _: None)
    with pytest.raises(FrameError):
        a.feed(b"\x01")
