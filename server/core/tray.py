"""系统托盘：显示/隐藏控制台窗口、复制上传地址、重启与退出。

pystray 的消息循环跑在独立线程（icon.run 阻塞），菜单回调也在这条线程上。
退出与重启只把请求回调给主线程，由 serve() 的 finally 统一收尾、main.py
决定是否重启；托盘自己不做清理。

控制台窗口按 HWND 操作：Windows Terminal 下 GetConsoleWindow 给的是内部
窗口，要取 GA_ROOT 才藏得掉整个终端窗口。
"""

import ctypes
import logging
import threading
from collections.abc import Callable
from ctypes import wintypes

import pystray
from PIL import Image
from pystray import MenuItem

from .clipboard import set_clipboard_text
from .paths import APP_DIR, FROZEN
from .version import app_version

logger = logging.getLogger("ble")

SW_HIDE = 0
SW_RESTORE = 9
SC_CLOSE = 0xF060
MF_BYCOMMAND = 0x0000
GA_ROOT = 3

_user32 = ctypes.WinDLL("user32")
_kernel32 = ctypes.WinDLL("kernel32")

_kernel32.GetConsoleWindow.restype = wintypes.HWND
_user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
_user32.GetAncestor.restype = wintypes.HWND
_user32.GetSystemMenu.argtypes = [wintypes.HWND, wintypes.BOOL]
_user32.GetSystemMenu.restype = wintypes.HMENU
_user32.DeleteMenu.argtypes = [wintypes.HMENU, wintypes.UINT, wintypes.UINT]
_user32.IsWindowVisible.argtypes = [wintypes.HWND]
_user32.IsWindowVisible.restype = wintypes.BOOL
_user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
_user32.SetForegroundWindow.argtypes = [wintypes.HWND]


def enable_dpi_awareness() -> None:
    """按显示器真实 DPI 绘制托盘菜单。

    进程默认是 DPI unaware：高分屏上 Windows 会把右键菜单当位图整体拉伸，
    字发糊。必须在创建任何窗口之前调用，所以放在 main() 的最前面。
    """
    _user32.SetProcessDpiAwarenessContext.argtypes = [wintypes.HANDLE]
    _user32.SetProcessDpiAwarenessContext.restype = wintypes.BOOL
    _user32.SetProcessDpiAwarenessContext(wintypes.HANDLE(-4))  # PER_MONITOR_AWARE_V2


def _console_window() -> int:
    window = _kernel32.GetConsoleWindow()
    return _user32.GetAncestor(window, GA_ROOT) or window


def _set_close_enabled(window: int, enabled: bool) -> None:
    """恢复或移除系统菜单里的「关闭」。"""
    if enabled:
        _user32.GetSystemMenu(window, True)
    else:
        menu = _user32.GetSystemMenu(window, False)
        _user32.DeleteMenu(menu, SC_CLOSE, MF_BYCOMMAND)


def _load_icon() -> Image.Image:
    # convert 会立即读盘，with 关闭文件后句柄不再依赖原始文件。
    with Image.open(APP_DIR / "assets" / "icon.ico") as image:
        return image.convert("RGBA").resize((64, 64), Image.Resampling.LANCZOS)


class Tray:
    def __init__(
        self,
        *,
        on_exit: Callable[[], None],
        on_restart: Callable[[], None],
        upload_urls: Callable[[], list[str]],
    ) -> None:
        self._window = _console_window()
        self._on_exit = on_exit
        self._on_restart = on_restart
        self._upload_urls = upload_urls
        self._icon = pystray.Icon(
            "BlueSend",
            _load_icon(),
            title=f"BlueSend {app_version()}",
            menu=(
                MenuItem("显示/隐藏窗口", self._toggle_window, default=True),
                MenuItem("复制上传地址", self._copy_upload_url),
                MenuItem("重启程序", self._restart),
                MenuItem("退出", self._exit),
            ),
        )
        self._thread = threading.Thread(target=self._icon.run, name="tray")

    def start(self) -> None:
        # 源码运行时保留终端窗口，方便看日志；打包后启动即隐藏。
        if FROZEN:
            _set_close_enabled(self._window, False)
            _user32.ShowWindow(self._window, SW_HIDE)
        self._thread.start()
        logger.info("托盘图标已启用：显示/隐藏窗口、复制上传地址、重启、退出")

    def stop(self) -> None:
        if FROZEN:
            _set_close_enabled(self._window, True)
            _user32.ShowWindow(self._window, SW_RESTORE)
        self._icon.stop()
        self._thread.join()

    def _toggle_window(self, icon, item) -> None:
        if _user32.IsWindowVisible(self._window):
            _user32.ShowWindow(self._window, SW_HIDE)
        else:
            _user32.ShowWindow(self._window, SW_RESTORE)
            _user32.SetForegroundWindow(self._window)

    def _copy_upload_url(self, icon, item) -> None:
        urls = self._upload_urls()
        if not urls:
            logger.warning("没有可用的局域网地址，无法复制上传入口")
            return
        if set_clipboard_text(urls[0]):
            logger.info("已复制上传地址：%s", urls[0])
        else:
            logger.warning("剪贴板被占用，复制上传地址失败")

    def _restart(self, icon, item) -> None:
        logger.info("托盘：重启程序")
        self._on_restart()

    def _exit(self, icon, item) -> None:
        logger.info("托盘：退出")
        self._on_exit()
