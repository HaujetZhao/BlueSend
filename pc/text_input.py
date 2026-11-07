"""把文本键入当前焦点窗口。

默认仍用 keyboard.write（SendInput + KEYEVENTF_UNICODE）。但中文输入法会
截获并打乱这串键盘事件，Qt5 应用（微信、Telegram）里全角中文标点后紧跟的
字会被替换成同一个标点。config.toml 的 wm_char_apps 命中的进程改投 WM_CHAR，
绕开输入法与键盘事件队列。

回车、退格仍用 keyboard 发送按键，保持 keyboard.write 原来的语义。
"""

import ctypes
from ctypes import wintypes

import keyboard
import psutil
import win32con
import win32gui
import win32process


class _GuiThreadInfo(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("hwndActive", wintypes.HWND),
        ("hwndFocus", wintypes.HWND),
        ("hwndCapture", wintypes.HWND),
        ("hwndMenuOwner", wintypes.HWND),
        ("hwndMoveSize", wintypes.HWND),
        ("hwndCaret", wintypes.HWND),
        ("rcCaret", wintypes.RECT),
    ]


# pywin32 没有封装 GetGUIThreadInfo，只剩这一个 API 直接调 Win32。
# 返回值不查：取不到焦点时 hwndFocus 为 0，_focused_window 会回落到前台窗口。
_user32 = ctypes.WinDLL("user32")
_user32.GetGUIThreadInfo.argtypes = [wintypes.DWORD, ctypes.POINTER(_GuiThreadInfo)]
_user32.GetGUIThreadInfo.restype = wintypes.BOOL


def _process_name(window: int) -> str:
    _, pid = win32process.GetWindowThreadProcessId(window)
    try:
        return psutil.Process(pid).name()
    except psutil.Error:
        return ""


def _focused_window() -> int:
    """取前台窗口所属线程的焦点控件。

    Qt 窗口没有原生子控件，hwndFocus 就是顶层窗口本身，WM_CHAR 照样能到。
    """
    window = win32gui.GetForegroundWindow()
    thread_id = win32process.GetWindowThreadProcessId(window)[0]
    info = _GuiThreadInfo()
    info.cbSize = ctypes.sizeof(_GuiThreadInfo)
    _user32.GetGUIThreadInfo(thread_id, ctypes.byref(info))
    return info.hwndFocus or window


def _utf16_units(char: str) -> list[int]:
    encoded = char.encode("utf-16-le")
    return [
        int.from_bytes(encoded[i:i + 2], "little")
        for i in range(0, len(encoded), 2)
    ]


def _post_wm_char(text: str) -> None:
    window = _focused_window()
    for char in text:
        if char == "\n":
            keyboard.send("enter")
        elif char == "\b":
            keyboard.send("backspace")
        else:
            for unit in _utf16_units(char):
                win32gui.PostMessage(window, win32con.WM_CHAR, unit, 1)


def type_text(text: str, wm_char_apps: set[str]) -> None:
    """按前台进程选择上屏方式。

    wm_char_apps 是 config.toml 里配置的进程名（小写）。
    """
    process_name = _process_name(win32gui.GetForegroundWindow())
    if process_name.lower() in wm_char_apps:
        _post_wm_char(text)
    else:
        keyboard.write(text)
