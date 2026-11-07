from bluetooth_input import text_input

WM_CHAR = 0x0102


def _capture(monkeypatch, process_name):
    events = []

    def fake_post_message(hwnd, message, wparam, lparam):
        events.append(("char", hwnd, message, wparam))

    monkeypatch.setattr(text_input.win32gui, "PostMessage", fake_post_message)
    monkeypatch.setattr(text_input.win32gui, "GetForegroundWindow", lambda: 0x1234)
    monkeypatch.setattr(text_input, "_focused_window", lambda: 0x1234)
    monkeypatch.setattr(text_input, "_process_name", lambda _hwnd: process_name)
    monkeypatch.setattr(text_input.keyboard, "send", lambda name: events.append(("key", name)))
    monkeypatch.setattr(text_input.keyboard, "write", lambda text: events.append(("write", text)))
    return events


def test_unlisted_app_keeps_keyboard_write(monkeypatch):
    events = _capture(monkeypatch, "Code.exe")

    text_input.type_text("你好，世界", {"weixin.exe", "telegram.exe"})

    assert events == [("write", "你好，世界")]


def test_listed_app_posts_each_character_as_wm_char(monkeypatch):
    events = _capture(monkeypatch, "Weixin.exe")

    text_input.type_text("你好，世界", {"weixin.exe"})

    assert events == [
        ("char", 0x1234, WM_CHAR, ord(char)) for char in "你好，世界"
    ]


def test_process_match_is_case_insensitive(monkeypatch):
    events = _capture(monkeypatch, "TELEGRAM.EXE")

    text_input.type_text("a", {"telegram.exe"})

    assert events == [("char", 0x1234, WM_CHAR, ord("a"))]


def test_newline_and_backspace_stay_keyboard_keys(monkeypatch):
    events = _capture(monkeypatch, "Weixin.exe")

    text_input.type_text("a\nb\b", {"weixin.exe"})

    assert events == [
        ("char", 0x1234, WM_CHAR, ord("a")),
        ("key", "enter"),
        ("char", 0x1234, WM_CHAR, ord("b")),
        ("key", "backspace"),
    ]


def test_non_bmp_character_posts_two_utf16_units(monkeypatch):
    events = _capture(monkeypatch, "Weixin.exe")

    text_input.type_text("😀", {"weixin.exe"})

    assert events == [
        ("char", 0x1234, WM_CHAR, 0xD83D),
        ("char", 0x1234, WM_CHAR, 0xDE00),
    ]
