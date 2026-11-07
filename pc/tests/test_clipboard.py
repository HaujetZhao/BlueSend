import clipboard


def test_open_failure_returns_none(monkeypatch):
    """打不开剪贴板是读取失败，必须返回 None，不能冒充空串。"""
    calls = 0

    def fake_open(_hwnd):
        nonlocal calls
        calls += 1
        return 0

    monkeypatch.setattr(clipboard._user32, "OpenClipboard", fake_open)

    assert clipboard.get_clipboard_text() is None
    assert calls == 3


def test_no_text_returns_empty_string(monkeypatch):
    """能打开但剪贴板里没有文本，是「内容为空」，返回空串。"""
    monkeypatch.setattr(clipboard._user32, "OpenClipboard", lambda _hwnd: 1)
    monkeypatch.setattr(clipboard._user32, "GetClipboardData", lambda _fmt: 0)

    assert clipboard.get_clipboard_text() == ""
