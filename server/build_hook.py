"""PyInstaller runtime hook：让冻结后的程序能导入 exe 旁边的 core/ 源码。

core/ 不进 PYZ，原样拷在 exe 旁边；而 PyInstaller 冻结后 sys.path 只有
internal/，这里补上 exe 所在目录，`from core.server import serve` 才会落到
源文件上。
"""

import os
import sys

sys.path.insert(0, os.path.dirname(sys.executable))
