"""单实例锁：Windows 命名互斥体。

两个 server.py 同时跑时，BLE 层不会报任何错：各自注册同一个 Service UUID、
各自广播，然后互相把对方的广播挤掉（见 AGENTS.md 坑 8）。所以在创建服务
之前先抢一个命名互斥体，抢不到就直接退出。

互斥体由系统在进程退出时自动释放，不需要清理，也不会留下僵尸锁。
"""

import ctypes
from ctypes import wintypes

_ERROR_ALREADY_EXISTS = 183

# 锁靠句柄存活，句柄不能被回收，所以一直持有到进程结束。
_handle = None


def acquire(name: str) -> bool:
    """抢到锁返回 True；已有进程持有同名锁返回 False。"""
    global _handle
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
    kernel32.CreateMutexW.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL

    handle = kernel32.CreateMutexW(None, False, name)
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    if ctypes.get_last_error() == _ERROR_ALREADY_EXISTS:
        kernel32.CloseHandle(handle)
        return False
    _handle = handle
    return True
