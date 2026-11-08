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


def _chunk(msg_id: int, frag: int, body: bytes) -> bytes:
    return msg_id.to_bytes(2, "big") + frag.to_bytes(2, "big") + body


def _fragments(msg_id: int, text: str, size: int = 512) -> list[bytes]:
    """把一条消息切成真实格式的分片，片头带消息 ID 与片序号。"""
    frame = encode(text)
    return [
        _chunk(msg_id, frag, frame[i:i + size])
        for frag, i in enumerate(range(0, len(frame), size))
    ]


def test_message_reassembles_in_fragment_order():
    out = []
    a = UplinkAssembler(out.append)
    frags = _fragments(0, "hello world", size=4)
    # 回调线程并发投递：片序颠倒，还原后内容不能错位。
    for f in (frags[1], frags[0], *frags[2:]):
        a.feed(f)
    assert out == [encode("hello world")]


def test_messages_commit_in_id_order():
    out = []
    a = UplinkAssembler(out.append)
    # 后一条先收齐也要等前一条：上屏顺序不能乱。
    for f in _fragments(1, "second"):
        a.feed(f)
    assert out == []
    for f in _fragments(0, "first"):
        a.feed(f)
    assert out == [encode("first"), encode("second")]


def test_expire_drops_message_with_missing_fragment():
    out = []
    a = UplinkAssembler(out.append)
    frags = _fragments(0, "x" * 20, size=4)
    a.feed(frags[0])
    a.feed(frags[2])  # 中间缺一片
    for f in _fragments(1, "next"):
        a.feed(f)
    assert out == []
    a.expire(0)  # 超时：丢掉缺片的消息，后面的继续提交
    assert out == [encode("next")]


def test_expire_skips_never_seen_message():
    out = []
    a = UplinkAssembler(out.append)
    for f in _fragments(1, "next"):
        a.feed(f)
    assert out == []
    a.expire(0)  # 消息 0 一片都没到，直接跳过
    assert out == [encode("next")]


def test_message_drops_duplicate_fragment():
    # 消息 0 只用来推进 ID；重复片的检查放在消息 1 上（ID 0 重复会被当成新流）。
    out = []
    a = UplinkAssembler(out.append)
    for f in _fragments(0, "hello"):
        a.feed(f)
    for f in _fragments(1, "world", size=4):
        a.feed(f)
        a.feed(f)  # 同一片重复投递
    assert out == [encode("hello"), encode("world")]


def test_assembler_reset_discards_inflight():
    out = []
    a = UplinkAssembler(out.append)
    a.feed(_chunk(0, 1, b"stale"))
    a.reset()
    for f in _fragments(0, "fresh"):
        a.feed(f)
    assert out == [encode("fresh")]


def test_assembler_rejects_short_chunk():
    a = UplinkAssembler(lambda _: None)
    with pytest.raises(FrameError):
        a.feed(b"\x01")


def test_stream_restart_on_message_id_zero():
    """手机端每条连接从消息 0 开始。收到 0 而已经在等更大的 ID，说明换了流。"""
    out = []
    a = UplinkAssembler(out.append)
    for f in _fragments(0, "old"):
        a.feed(f)
    for f in _fragments(1, "old2"):
        a.feed(f)
    for f in _fragments(0, "new"):
        a.feed(f)
    assert out == [encode("old"), encode("old2"), None, encode("new")]
