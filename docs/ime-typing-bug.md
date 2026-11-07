# 中文输入法下上屏丢字（微信 / Telegram）

## 现象

在微信、Telegram 里通过本工具模拟输入中文时，全角中文标点后紧跟的第一个字会被替换成同一个标点：

| 期望 | 实际 |
|---|---|
| `测试，你好。世界` | `测试，，好。。界` |
| `测试甲，乙丙丁。戊己` | `测试甲，，丙丁。。己` |

受影响的是全角中文标点：`，。！？；：、（）「」—`。半角标点、`·`、`…`、空格都不受影响。100% 稳定复现。

## 复现方法

1. 电脑端启动 `server/main.py`，手机网页连上。
2. 焦点放在微信聊天框或 Telegram 搜索框（系统输入法为微软五笔）。
3. 发送 `测试，你好。世界`，观察落字。

## 影响范围

出问题的两个应用都是 Qt5：

| 应用 | 窗口类 |
|---|---|
| 微信 | `Qt51514QWindowIcon` |
| Telegram | `Qt51519QWindowIcon` |

记事本（原生 `EDIT`）、Edge 网页输入框不受影响——这也解释了为什么只有这两个应用会出问题。

## 根因

`server/core/server.py` 的 `text` 分支原来用 `keyboard.write`。Windows 上它把每个字符作为 `SendInput` + `KEYEVENTF_UNICODE`（VK_PACKET）的一对「按下 / 抬起」事件注入。

用 PyQt5（同为 Qt 5.15）自建窗口并挂上微软五笔，抓到的消息流如下：

```text
KEYDOWN 0xe7  CHAR 0x6d4b '测'  KEYUP 0xe7
KEYDOWN 0xe7  CHAR 0x8bd5 '试'  KEYUP 0xe7
KEYDOWN 0xe7  CHAR 0xff0c '，'
KEYDOWN 0xe7  CHAR 0x4f60 '你'  KEYUP 0xe7   ← 逗号的 KEYUP 被吞，之后事件流开始错乱
KEYDOWN 0xe7  CHAR 0x597d '好'  KEYUP 0xe7
...
```

即：**中文输入法（TSF）截获了注入的 VK_PACKET 事件，吞掉全角标点后的 KEYUP 并打乱后续事件流**；Qt5 应用会参考输入法状态提交文本，于是提交错位。

佐证：

- 同一份注入，把 Telegram 的输入语言切到「美式键盘英语」（HKL `0x4090409`），消息流完全规整、文本一字不差。
- 记事本在中文输入法下同样用 `keyboard.write`，文本也一字不差——原生控件只按 `WM_CHAR` 插入，不参与输入法状态机。

## 修复：默认 SendInput，兼容名单改用 WM_CHAR

两种上屏方式并存，由 `server/core/config.toml` 的前台进程名决定：

```toml
wm_char_apps = ["Weixin.exe", "Telegram.exe"]
```

- **默认**：`keyboard.write`（SendInput）。CMD、PowerShell、Windows Terminal、记事本、浏览器等都用这条。
- **命中名单**（不区分大小写）：向焦点窗口直接投递 `WM_CHAR`，绕开输入法与键盘事件队列。

`server/core/text_input.py` 的实现：

- 前台进程名：`win32gui.GetForegroundWindow` → `win32process.GetWindowThreadProcessId` → `psutil.Process(pid).name()`。
- 焦点窗口：`GetGUIThreadInfo` 的 `hwndFocus`，回落前台窗口（pywin32 没封装这个 API，仍用 ctypes 调用）。Qt 窗口没有原生子控件，`hwndFocus` 就是顶层窗口本身。
- 按 UTF-16 码元逐字 `PostMessage(WM_CHAR)`；非 BMP 字符（代理对）拆成两个码元。
- `\n`、`\b` 仍用 `keyboard.send("enter" / "backspace")`，保持原来的 `keyboard.write` 语义。
- `key` 消息（enter / backspace）不变，继续走 `keyboard.send`。

改完 `config.toml` 需要重启 `main.py` 生效。

### 验证记录

| 目标 | SendInput | WM_CHAR |
|---|---|---|
| Telegram | ✗ 吞字 | ✓ |
| 微信 | ✗ 吞字 | ✓ |
| 记事本 | ✓ | ✓ |
| Edge 网页输入框 | ✓ | ✓ |
| CMD / PowerShell | ✓ | ✓ |
| Windows Terminal | ✓ | ✗ 收不到文本 |

所以 Windows Terminal 这类只吃键盘事件的窗口继续走默认的 SendInput；微信、Telegram 这类 Qt5 应用走 WM_CHAR。

## 已知遗留

- Emoji（代理对）在 Telegram / 微信里目前本来就无法上屏：SendInput 下 Qt 只收到高位代理、低位丢失；WM_CHAR 下两个码元都能到，但 Qt 仍然丢弃。这不是本次改动引入的问题，后续可单独处理。
- `text` 中间夹 `\n` 时（例如粘贴多行文本），回车仍通过 `SendInput` 发送，与前后 `PostMessage` 属于两条队列，极端情况下顺序可能错开；末尾追加 `\n` 的常规发送不受影响。
