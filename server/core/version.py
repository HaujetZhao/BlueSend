"""运行期版本号。

唯一来源是 `pyproject.toml`：源码运行时直接读它，打包时由 `BlueSend.spec`
写进 exe 的版本资源，运行时再从 exe 读回来。不在源码里另存一个常量，
免得发版时漏改一处。
"""

import sys
import tomllib

import win32api

from .paths import APP_DIR, FROZEN


def app_version() -> str:
    if not FROZEN:
        project = tomllib.loads(
            (APP_DIR / "pyproject.toml").read_text(encoding="utf-8")
        )
        return project["project"]["version"]

    info = win32api.GetFileVersionInfo(sys.executable, "\\")
    major, minor = divmod(info["FileVersionMS"], 0x10000)
    patch = info["FileVersionLS"] // 0x10000
    return f"{major}.{minor}.{patch}"
