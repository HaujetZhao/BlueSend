"""读取 config.toml。"""

import tomllib
from pathlib import Path

CONFIG_PATH = Path(__file__).parent / "config.toml"


def load_wm_char_apps() -> set[str]:
    """返回需要用 WM_CHAR 上屏的进程名集合（小写）。"""
    with CONFIG_PATH.open("rb") as file:
        apps = tomllib.load(file)["wm_char_apps"]
    return {app.lower() for app in apps}


def load_upload_folder() -> str:
    """返回上传文件落点的子文件夹名。"""
    with CONFIG_PATH.open("rb") as file:
        return tomllib.load(file)["upload"]["folder"]
