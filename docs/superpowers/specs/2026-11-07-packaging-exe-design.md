# 电脑端打包 exe：PyInstaller + spec 驱动

## 目的

电脑端现在只能用 `uv run python main.py` 启动，要求用户装 Python 和 uv。打包成 exe 后，双击即可运行，分发只需要一个压缩包。

构建方式对齐已有项目 `E:\repos-tts\qwen3-tts`、`E:\repos-asr\CapsWriter-Offline`：**写 spec、改 spec、直接用 spec 打包**，不用散落的命令行参数。

## 产物形态

PyInstaller **onedir**（不用 onefile）：

```text
dist/BlueSend/
├── BlueSend.exe
├── internal/       第三方依赖、winrt 投影包与 Python 运行时（PyInstaller 生成）
├── core/           Python 源文件，含 config.toml、upload_page.html
└── logs/           首次运行自动生成
```

选 onedir 的理由：

- 与两个参考项目一致，构建与排查路径相同。
- 启动不用先解压，冷启动明显快。
- 依赖出问题时能直接看到是 `internal/` 里的哪个文件。

不用 onefile。以后若要单文件，只需改 spec 里 `EXE`／`COLLECT` 两处，代码不动。

## 为什么 `core/` 以源文件发布

`core/` 不进 PYZ，原样拷到 exe 旁边。好处：

- **改配置和代码不用重新打包。** `core/config.toml` 就在旁边，改完重启 exe 生效；临时调一行 Python 也是改完即生效。
- **路径解析不用特殊处理。** `core/config.py` 的 `Path(__file__).parent / "config.toml"`、`core/upload_server.py` 的 `Path(__file__).with_name("upload_page.html")` 在源码和打包两种形态下都指向真文件，一行不用改。
- 首次运行会在 `core/` 下生成 `__pycache__`，属正常。

代价：改坏 `core/` 后与 `internal/` 里的依赖版本不匹配，需要用户自己收拾。这是自用工具，接受。

## spec 的做法

`server/BlueSend.spec` 入库，结构照参考项目：

1. `Analysis(["main.py"], ...)` 正常分析。
2. 从 `a.pure` 中滤掉 `core` 及其全部子模块——`core` 不进 PYZ。
3. `EXE(..., exclude_binaries=True, console=True, contents_directory="internal")`。
4. `COLLECT(...)` 生成 `dist/BlueSend/`。
5. `COLLECT` 之后把 `server/core/` 拷到 `dist/BlueSend/core/`，排除 `__pycache__` 与 `*.pyc`。

不手写 winrt 的 hiddenimports：`winrt-runtime` 通过 entry point 自带 PyInstaller 钩子（`.venv` 中已确认 `winrt/__pyinstaller/hook-winrt.py`），会自动收集已安装投影包的 `_table.pywinrt` 与运行时按名导入的命名空间。

`upx=False`：本机未装 UPX，开着只会得到警告。

`console=True`：保留 rich 日志、上传入口 URL 与 Ctrl+C 退出，和现在源码运行一致。

## runtime hook

`server/build_hook.py`，在入口脚本执行前把 exe 所在目录插到 `sys.path` 最前面：

```python
sys.path.insert(0, os.path.dirname(sys.executable))
```

这是 `from core.server import serve` 在打包后能导入旁边源文件的关键。PyInstaller 冻结后 `sys.path` 默认只含 `internal`，不含 exe 目录。

## 路径解析

只改一处：`main.py` 的日志目录。打包后 `Path(__file__).parent` 会指进 `internal/`，日志会落到解压区或只读区。

新增 `server/core/paths.py`：

```python
FROZEN = getattr(sys, "frozen", False)
APP_DIR = Path(sys.executable).parent if FROZEN else Path(__file__).parent.parent
```

`main.py` 改用 `setup_logging(APP_DIR / "logs")`。源码运行时 `APP_DIR` 仍是 `server/`，与现在一致。

`core/config.py` 与 `core/upload_server.py` 不动。

## 图标与版本信息

- 图标：`web/public/icon-512.png` 转成 `server/assets/icon.ico`（多尺寸）后入库，spec 用 `icon=` 引用。
- 版本资源：spec 从 `server/pyproject.toml` 的 `version` 读取并生成版本信息文件，不另外维护一份版本号。

## 依赖与构建

`pyproject.toml` 的 dev 依赖组加 `pyinstaller>=6.22`。构建：

```powershell
cd server
uv run pyinstaller BlueSend.spec
```

`PyInstaller 6.22.3` 已在 Python 3.14.7 上验证可导入。

`.gitignore` 加 `build/`；`dist/` 已被覆盖。

## 单实例提示

`main.py` 抢不到命名互斥体时的提示语按 frozen／源码分开：

- 打包后：提示已有 `BlueSend.exe` 在运行，排查命令用 `Get-CimInstance ... "Name like 'BlueSend%'"`。
- 源码运行：保持现在的 `main.py` 与 `python%` 提示。

## 验收

- `uv run pyinstaller BlueSend.spec` 一次构建通过，产物在 `server/dist/BlueSend/`。
- 双击 `BlueSend.exe`，控制台出现「广播状态：2」与文件上传入口 URL。
- 首次运行后 `dist/BlueSend/logs/` 出现日志，`dist/BlueSend/core/__pycache__` 生成。
- `dist/BlueSend/core/config.toml` 存在且可编辑；改动是否生效由真机验证（例如改 `upload.folder` 后上传文件落在新目录）。
- `cd server && uv run pytest` 照常通过。
- 手机真机连接、上屏、剪贴板、传文件由用户本人验证。

## 不做

- GitHub Actions 发布工作流。
- 托盘图标、无控制台模式。
- 单文件 exe。
- 自动更新。
