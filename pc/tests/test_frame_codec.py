from frame_codec import Decoder, encode


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
