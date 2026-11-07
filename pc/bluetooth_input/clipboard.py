"""通过 pywin32 的 win32clipboard 读写系统剪贴板。

项目已经依赖 pywin32：win32clipboard 会替我们完成 CF_UNICODETEXT 的内存分配、
编码与解码，不必再手写 GlobalAlloc / GlobalLock / memmove 那套样板；失败也统一
以 pywintypes.error 异常表达，比逐个检查裸 Win32 返回值更不容易漏判。
"""

import time

import win32clipboard
import win32con

_OPEN_ATTEMPTS = 3
_OPEN_RETRY_INTERVAL = 0.02


def _close_clipboard() -> None:
    """收尾关闭剪贴板。

    打开成功后一定要走到这里。若剪贴板在持有期间已被别的程序关掉，
    CloseClipboard 会抛 error（1418）；此时已经没有需要释放的状态，忽略即可。
    """
    try:
        win32clipboard.CloseClipboard()
    except win32clipboard.error:
        pass


def get_clipboard_text() -> str | None:
    """读取剪贴板文本。

    返回 None 表示读取失败（剪贴板被别的程序占着、或取数据时出错）；
    返回空串表示读取成功、只是剪贴板里没有文本。调用方必须区分这两者，
    否则「读不到」会被当成「内容为空」推给手机，清掉对方的剪贴板。
    """
    for attempt in range(_OPEN_ATTEMPTS):
        try:
            win32clipboard.OpenClipboard()
            break
        except win32clipboard.error:
            # 剪贴板常被其他程序短暂占用，隔一会儿再试；最后一次失败就不再等。
            if attempt == _OPEN_ATTEMPTS - 1:
                return None
            time.sleep(_OPEN_RETRY_INTERVAL)

    try:
        return win32clipboard.GetClipboardData(win32con.CF_UNICODETEXT)
    except TypeError:
        # pywin32 在剪贴板没有该格式时抛 TypeError，这属于「内容为空」而非读取失败。
        return ""
    except win32clipboard.error:
        return None
    finally:
        _close_clipboard()


def set_clipboard_text(text: str) -> bool:
    try:
        win32clipboard.OpenClipboard()
    except win32clipboard.error:
        return False
    try:
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(win32con.CF_UNICODETEXT, text)
        return True
    except win32clipboard.error:
        return False
    finally:
        _close_clipboard()
