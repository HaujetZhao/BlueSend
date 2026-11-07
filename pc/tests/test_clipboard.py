import pytest

import clipboard


def _open_error(*_args):
    raise clipboard.win32clipboard.error(5, "OpenClipboard", "拒绝访问。")


def test_open_failure_returns_none(monkeypatch):
    """打不开剪贴板是读取失败，必须返回 None，不能冒充空串。"""
    calls = 0

    def fake_open():
        nonlocal calls
        calls += 1
        raise clipboard.win32clipboard.error(5, "OpenClipboard", "拒绝访问。")

    monkeypatch.setattr(clipboard.win32clipboard, "OpenClipboard", fake_open)
    monkeypatch.setattr(clipboard.win32clipboard, "CloseClipboard", pytest.fail)
    monkeypatch.setattr(clipboard.time, "sleep", lambda _seconds: None)

    assert clipboard.get_clipboard_text() is None
    assert calls == 3


def test_no_text_returns_empty_string(monkeypatch):
    """能打开但剪贴板里没有文本，是「内容为空」，返回空串。"""
    closed = 0

    def fake_close():
        nonlocal closed
        closed += 1

    def no_text(_fmt):
        # pywin32 312 的实际行为：格式不可用时抛 TypeError。
        raise TypeError("Specified clipboard format is not available")

    monkeypatch.setattr(clipboard.win32clipboard, "OpenClipboard", lambda: None)
    monkeypatch.setattr(clipboard.win32clipboard, "GetClipboardData", no_text)
    monkeypatch.setattr(clipboard.win32clipboard, "CloseClipboard", fake_close)

    assert clipboard.get_clipboard_text() == ""
    assert closed == 1


def test_get_returns_text(monkeypatch):
    """能打开且有文本时原样返回，并在 finally 里关闭剪贴板。"""
    closed = 0

    def fake_close():
        nonlocal closed
        closed += 1

    monkeypatch.setattr(clipboard.win32clipboard, "OpenClipboard", lambda: None)
    monkeypatch.setattr(
        clipboard.win32clipboard,
        "GetClipboardData",
        lambda fmt: "测试文本" if fmt == clipboard.win32con.CF_UNICODETEXT else None,
    )
    monkeypatch.setattr(clipboard.win32clipboard, "CloseClipboard", fake_close)

    assert clipboard.get_clipboard_text() == "测试文本"
    assert closed == 1


def test_get_data_error_returns_none(monkeypatch):
    """打开后取数据出错属于读取失败，仍然返回 None。"""
    monkeypatch.setattr(clipboard.win32clipboard, "OpenClipboard", lambda: None)
    monkeypatch.setattr(clipboard.win32clipboard, "GetClipboardData", _open_error)
    monkeypatch.setattr(clipboard.win32clipboard, "CloseClipboard", lambda: None)

    assert clipboard.get_clipboard_text() is None


def test_set_success(monkeypatch):
    """写入按 CF_UNICODETEXT 走 Empty + Set，成功返回 True 并关闭剪贴板。"""
    calls = []
    closed = 0

    def fake_close():
        nonlocal closed
        closed += 1

    monkeypatch.setattr(clipboard.win32clipboard, "OpenClipboard", lambda: None)
    monkeypatch.setattr(clipboard.win32clipboard, "EmptyClipboard", lambda: calls.append("empty"))
    monkeypatch.setattr(
        clipboard.win32clipboard,
        "SetClipboardData",
        lambda fmt, text: calls.append((fmt, text)),
    )
    monkeypatch.setattr(clipboard.win32clipboard, "CloseClipboard", fake_close)

    assert clipboard.set_clipboard_text("测试，你好。") is True
    assert calls == ["empty", (clipboard.win32con.CF_UNICODETEXT, "测试，你好。")]
    assert closed == 1


def test_set_open_failure_returns_false(monkeypatch):
    """打不开剪贴板时写入直接失败，返回 False，不碰后续接口。"""
    monkeypatch.setattr(clipboard.win32clipboard, "OpenClipboard", _open_error)
    monkeypatch.setattr(clipboard.win32clipboard, "CloseClipboard", pytest.fail)

    assert clipboard.set_clipboard_text("测试") is False
