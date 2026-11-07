"""运行期的应用根目录：日志等可写文件都放在它下面。

源码运行时是 `server/`，打包后是 exe 所在目录。`core/` 在两种形态下都位于
应用根目录的一级子目录里，所以 core 内部用 `__file__` 定位的配置与页面不用
关心是否 frozen；只有打包进 PYZ 的 `main.py` 需要这个模块。
"""

import sys
from pathlib import Path

FROZEN = getattr(sys, "frozen", False)

APP_DIR = Path(sys.executable).parent if FROZEN else Path(__file__).parent.parent
