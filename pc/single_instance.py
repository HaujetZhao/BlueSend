"""单实例锁：Windows 命名互斥体。

两个 server.py 同时跑时，BLE 层不会报任何错：各自注册同一个 Service UUID、
各自广播，然后互相把对方的广播挤掉（见 AGENTS.md 坑 8）。所以在创建服务
之前先抢一个命名互斥体，抢不到就直接退出。

互斥体由系统在进程退出时自动释放，不需要清理，也不会留下僵尸锁。
"""

import win32api
import win32event

_ERROR_ALREADY_EXISTS = 183

# 锁靠句柄存活，句柄不能被回收，所以一直持有到进程结束。
_handle = None


def acquire(name: str) -> bool:
    """抢到锁返回 True；已有进程持有同名锁返回 False。"""
    global _handle
    handle = win32event.CreateMutex(None, False, name)
    # 互斥体已存在不是失败：CreateMutex 照样返回有效句柄，靠 last error 区分。
    if win32api.GetLastError() == _ERROR_ALREADY_EXISTS:
        handle.Close()
        return False
    _handle = handle
    return True
