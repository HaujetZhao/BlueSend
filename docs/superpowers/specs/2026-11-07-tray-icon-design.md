# 系统托盘与启动引导

## 目的

打包后的 exe 双击启动会留一个控制台窗口。加托盘让它能安静地待在后台：窗口默认藏起来，需要看日志时再调出来；退出、重启不再依赖任务管理器。同时在控制台打印一段启动引导，告诉用户手机端该打开哪个页面、怎么连。

## 交互

- 打包运行时，启动后立即隐藏控制台窗口并禁用系统菜单里的「关闭」；源码运行（`uv run python main.py`）保持窗口可见、关闭按钮可用，方便开发。
- 托盘菜单四项：
  - **显示/隐藏窗口**：切换控制台窗口可见性，同时是双击托盘图标的默认项。
  - **复制上传地址**：把默认路由网卡上的上传入口 URL（带 token）写入系统剪贴板。
  - **重启程序**：退出当前进程后拉起新进程。
  - **退出**：正常收尾后退出。
- 托盘图标取 `APP_DIR/assets/icon.ico`，缩放到 64×64。

## 启动引导

`main.py` 抢到单实例锁之后、启动服务之前，用 rich 打印：

```text
──────────────────────── BlueSend 电脑端 ────────────────────────

手机浏览器打开：https://haujetzhao.github.io/BlueSend/

  1. 点左上角的连接状态药丸，选中本机
  2. 同一页面只开一个标签页，多开会互抢设备

日志目录：<APP_DIR>/logs
```

上传入口 URL 仍由服务启动时的日志输出，不重复进引导。

## 线程模型

- pystray 的 `icon.run()` 阻塞，放在名为 `tray` 的非守护线程里；菜单回调也在这条线程上。
- 退出与重启不直接操作 asyncio：`serve()` 里创建 `asyncio.Event` 与 `restart_requested` 标记，托盘回调通过 `loop.call_soon_threadsafe` 投递设置操作——与现有 WinRT 回调跨线程投递的写法一致。
- 事件循环已关闭时的投递会抛 `RuntimeError`，直接忽略：那是退出流程正在收尾。
- `serve()` 用 `asyncio.wait(..., FIRST_COMPLETED)` 让读循环与退出事件竞速；退出时取消读循环，`finally` 里依次 `tray.stop()`、取消心跳、停广播、停上传服务。`tray.stop()` 会 `icon.stop()` 并 join 托盘线程。

## 退出与重启

- 退出：`serve()` 返回 `False`，进程正常结束，命名互斥体由系统释放。
- 重启：`serve()` 返回 `True`。`main.py` **先** `single_instance.release()` 关闭互斥体句柄，**再** `Popen` 新进程。顺序不能反：互斥体是存在性锁，旧进程没放锁时新进程会直接退出。
- 重启命令行：打包后 `[sys.executable, *sys.argv[1:]]`（`argv[0]` 就是 exe，不能重复传）；源码运行 `[sys.executable, *sys.argv]`。

## Windows Terminal 的代价

隐藏操作作用于控制台的顶层窗口（`GetConsoleWindow` 后取 `GetAncestor(GA_ROOT)`）。在 Windows Terminal 里运行时，被隐藏的是整个终端窗口（所有标签页），不只是本程序；双击 exe 时是普通 conhost，只影响本窗口。这与参考实现 CapsWriter-Offline 的行为一致。

## 打包

- 依赖加 `pystray` 与 `pillow`；`pyinstaller-hooks-contrib` 自带两者的钩子，spec 不用手写 hiddenimports。
- spec 在 `COLLECT` 之后把 `server/assets/` 拷到 `dist/BlueSend/assets/`，托盘运行期按 `APP_DIR` 读图标。
- 产物目录变为 `BlueSend.exe / internal / core / assets / logs`；Pillow 让产物增加约 14 MB。

## 验收

客观部分：

- 构建通过；源码运行与打包运行都能打印引导并输出「托盘图标已启用」。
- 打包运行时进程的 `MainWindowHandle` 为 0（控制台已隐藏），服务与心跳照常。
- `uv run pytest` 通过。

交互部分由用户本人验证：托盘图标是否出现、四项菜单是否按预期工作、显示/隐藏切换与退出/重启的实际手感。
