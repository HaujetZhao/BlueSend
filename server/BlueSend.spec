# -*- mode: python ; coding: utf-8 -*-
"""BlueSend 电脑端打包配置。

用法（在 server/ 下）：

    uv run pyinstaller BlueSend.spec

产物：

    dist/BlueSend/
    ├── BlueSend.exe
    ├── internal/   第三方依赖与 Python 运行时
    ├── core/       Python 源文件（含 config.toml、upload_page.html）
    ├── assets/     托盘图标
    └── logs/       首次运行生成

core/ 不进 PYZ，打包后仍是可编辑的源文件：改配置或代码后重启 exe 即生效，
不用重新打包。代价是 core/ 与 internal/ 里的依赖版本不匹配时得自己收拾。
"""

import shutil
import tomllib
from pathlib import Path

from PyInstaller.utils.win32.versioninfo import (
    FixedFileInfo,
    StringFileInfo,
    StringStruct,
    StringTable,
    VarFileInfo,
    VarStruct,
    VSVersionInfo,
)

APP_NAME = "BlueSend"
ROOT = Path(SPECPATH)

version = tomllib.loads(
    (ROOT / "pyproject.toml").read_text(encoding="utf-8")
)["project"]["version"]
file_version = tuple(int(part) for part in version.split(".")) + (0,)

version_info = VSVersionInfo(
    ffi=FixedFileInfo(filevers=file_version, prodvers=file_version),
    kids=[
        StringFileInfo(
            [
                StringTable(
                    "080404B0",
                    [
                        StringStruct("CompanyName", APP_NAME),
                        StringStruct("FileDescription", "BlueSend 电脑端"),
                        StringStruct("FileVersion", version),
                        StringStruct("InternalName", APP_NAME),
                        StringStruct("OriginalFilename", f"{APP_NAME}.exe"),
                        StringStruct("ProductName", APP_NAME),
                        StringStruct("ProductVersion", version),
                    ],
                )
            ]
        ),
        VarFileInfo([VarStruct("Translation", [0x0804, 1200])]),
    ],
)

a = Analysis(
    [str(ROOT / "main.py")],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[str(ROOT / "build_hook.py")],
    excludes=[],
    noarchive=False,
)

# core/ 以源文件形式随包发布，不进 PYZ。
a.pure = [
    entry
    for entry in a.pure
    if entry[0] != "core" and not entry[0].startswith("core.")
]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ROOT / "assets" / "icon.ico"),
    version=version_info,
    contents_directory="internal",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name=APP_NAME,
)

# 把源码形式的 core/ 放到 exe 旁边。runtime hook 会把该目录加进 sys.path。
shutil.copytree(
    ROOT / "core",
    Path(DISTPATH) / APP_NAME / "core",
    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    dirs_exist_ok=True,
)

# 托盘运行期按 APP_DIR/assets/icon.ico 读图标；exe 图标虽然嵌进去了，
# 托盘仍需要一份可读的文件。
shutil.copytree(
    ROOT / "assets",
    Path(DISTPATH) / APP_NAME / "assets",
    dirs_exist_ok=True,
)
