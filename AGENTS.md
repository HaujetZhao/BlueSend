# AGENTS.md：手机 ↔ 电脑 BLE 通道

面向在本仓库工作的 AI 代理与开发者。产品说明见 [readme.md](readme.md)，协议的唯一事实来源是 [protocol.md](protocol.md)。

## 一、项目是什么

自用工具：**手机与电脑之间畅快传信息**（打字直接上屏、剪贴板互推）。

技术路线：**电脑做 BLE 外设，手机开网页连上去**。选 BLE 而不是 RFCOMM，唯一的理由是手机端能用网页——不用装 App、不用过应用商店；代价是 Windows 侧只能自己用 WinRT 写 GATT Server（没有成熟的高层库）。

代码最初在 `E:\repos\ble` 里成形（那里还试过原生 Android App 路线，卡在「30 秒自动断开」），2026-11-07 合并进本仓库。`E:\repos\ble` 是冻结的旧副本；原生 App 源码未随本仓库保留。

## 二、架构

| 角色 | 端 | 技术 |
|---|---|---|
| GATT Server（外设，广播） | Windows 电脑 | Python 3.14 + `winrt-Windows.Devices.Bluetooth.GenericAttributeProfile` |
| GATT Client（中心，主动连接） | 手机 | 网页 + Web Bluetooth（Android Chrome） |
| 网页承载 | GitHub Pages（`haujetzhao.github.io/Bluetooth-Input/`），或本地 Vite dev server | 静态 HTTPS 页面（Web Bluetooth 要求安全上下文） |

**不能用 bleak。** bleak 只支持 Windows 做中心，本项目角色反过来，必须直接用 WinRT 的 `GattServiceProvider`。

双特征值，布局照搬 Nordic UART Service：

- 上行 `7d9f0002`：手机写、电脑收，只声明 `WRITE`。
- 下行 `7d9f0003`：电脑通知、手机收，只声明 `NOTIFY`。

## 三、代码地图

```text
E:\repos\Bluetooth-Input\
├── AGENTS.md                   本文件：给代理与开发者的项目说明
├── readme.md                   对外说明
├── protocol.md                 协议的唯一事实来源
├── .github/workflows/deploy.yml  GitHub Actions：构建 PWA 并发布到 Pages
├── web\                        手机端网页（Vue 3 + Vite）
│   ├── index.html              Vite 入口
│   ├── src\App.vue             手机端页面与输入交互
│   ├── src\styles.css
│   ├── src\logic\protocol.js   UUID 与链路参数
│   ├── src\logic\frame-codec.js 帧编解码
│   ├── src\logic\ble-client.js 连接、重连、心跳、写队列
│   ├── src\composables\useBle.js Vue 响应式封装
│   ├── public\                 PWA 图标
│   ├── certs\{cert,key}.pem    自签证书，dev server 用
│   └── vite.config{,.pwa}.js   三套构建配置
├── pc\                         电脑端
│   ├── server.py               GATT Server 主程序
│   ├── logging_setup.py        日志配置（控制台 rich 上色，文件精确到毫秒）
│   ├── single_instance.py      单实例锁（Windows 命名互斥体）
│   ├── protocol.py             UUID 与下行分片上限
│   ├── frame_codec.py          4 字节长度前缀帧编解码
│   ├── clipboard.py            Win32 剪贴板读写
│   ├── tests\                  pytest
│   └── logs\                   服务端日志（gitignore）
├── docs\superpowers\           历史设计与计划文档（保留原貌）
└── .trash\                     废弃文件暂存区（gitignore）
```

## 四、怎么跑

启动时会自动检查有没有别的实例（命名互斥体），有就打印提示后直接退出。仍建议从 PowerShell 看一眼——**多实例会互相抢广播，症状极难认**，而锁只认带锁的实例：

```powershell
Get-CimInstance Win32_Process -Filter "Name like 'python%'" | Select-Object ProcessId,CommandLine
```

再启动电脑端：

```powershell
cd E:\repos\Bluetooth-Input\pc
uv run python server.py
```

看到 `广播状态：2`（Started）就是在等手机连接。日志同时写 `pc/logs/ble-<时间戳>.log`，网页端日志也会通过 `log` 消息打进来。

手机端两种访问方式：

- **在线版**：`https://haujetzhao.github.io/Bluetooth-Input/`（由 `.github/workflows/deploy.yml` 在推送 `main` 后构建发布）
- **本地开发**：在 `web\` 下运行 `npm run dev`，手机打开 `https://<电脑局域网IP>:5173`，首次信任自签证书

连上后点「扫描连接」→ 选中电脑。状态栏下面那行小字会写「已连接（第 N 段）」，断开时写原因和上一段存活时长。

前端命令，都在 `web\` 目录下执行：

```powershell
npm install
npm run dev        # HTTPS 开发服务器，手机可访问
npm test           # 帧编解码单测
npm run build      # 单文件产物 dist/index.html
npm run build:pwa  # PWA 产物，供 GitHub Pages 部署
```

电脑端单测：`cd pc && uv run pytest`。

## 五、协议速查

完整定义以 [protocol.md](protocol.md) 为准，这里只记最容易踩的约束：

- 帧格式：4 字节大端长度 + UTF-8 JSON；一条消息可以横跨多次写入或通知。
- 手机 → 电脑：`writeValueWithResponse`，单包取 `maxWriteWithResponseSize`，拿不到用 180 字节。
- 电脑 → 手机：分片取 `min(GattSubscribedClient.max_notification_size, 512)`。
- 心跳：电脑每 3 秒发 `{"t":"hb"}`；网页 9 秒没收到任何消息就判定链路已死。
- 改协议时 `protocol.md`、`pc/server.py`、`pc/protocol.py`、`web/src/logic/protocol.js`、`web/src/logic/frame-codec.js` 必须同步。

## 六、已知约束与踩过的坑

### 1. WinRT 事件处理器不接受 async 函数

```text
TypeError: 'Windows.Foundation.TypedEventHandler' cannot take ... an async def function,
because WinRT does not await what it returns
```

必须传普通函数。

### 2. `deferral` / `respond` 有线程亲和性——这就是「30 秒断开」的根因

上一代代码在 WinRT 回调里 `get_deferral()`，把活儿丢回 asyncio 线程，再在那边 `complete()`。跨线程完成会抛异常，而异常被吞在 `finally` 里，于是 Windows 永远在等那次写请求——ATT 事务 30 秒超时，整条链路断开。

现在的写法：写请求在回调线程上同步 `get_request_async().get()` 取到值、同步 `respond()`，只把字节投递给 asyncio 队列，业务处理才回到 asyncio 线程。原则是**跨线程只传数据，不传控制权**。

（诚实备注：这条根因是「最强嫌疑 + 移除后不复现」，没有逐帧证明过。旧仓库的异常被吞了，没留现场。）

### 3. `get_request_async()` 不能直接 `get_results()`

```text
OSError: [WinError -2147483634] 在意外的时间调用了方法
```

操作还没完成，要用 `.get()`（阻塞等待，会泵消息）。

### 4. 无响应写没有顺序保证，长文本会乱序

长中文文本（556 字节，28 个分片）在电脑端 `UnicodeDecodeError: 0xe8 in position 195`，字节总数完全对得上，说明不是丢包而是**分片顺序被调换**（第 196 字节正好是第 10 分片的首字节）。

修法：手机端改用 `writeValueWithResponse`，由 ATT 层保证先后顺序。上行特征值只声明 `WRITE` 之后，无响应写在属性层就不存在了。

### 5. 广播状态不能读一次了事

`start_advertising()` 异步生效，紧接着读 `provider.advertisement_status` 拿到的是 `ABORTED`（3），日志里全是假警报。要监听 `add_advertisement_status_changed`，事件里是 `STARTED`（2）。

### 6. 服务端进程死后，手机不会感知

Windows 继续在链路层维持连接，浏览器 `gattserverdisconnected` 永远不触发。靠心跳解决：电脑每 3 秒发 `{"t":"hb"}`，网页 9 秒没收到任何消息就判定链路已死并重连。

### 7. 上一次连接没清干净会 `status=133`

原生 App 时代的坑。网页侧现在靠「断开即重连 + `writeChain` 串行化 + 重连前清空接收缓冲」规避。

### 8. 多个 `server.py` 进程同时跑会抢广播

`uv run` 外面包了一层，停后台任务只杀到包装进程，真正的 python 子进程还活着。两个进程用同一个 Service UUID 各自注册、各自广播，症状是 `GATT Error Unknown`、刚连就断。

BLE 接口本身给不出「这个 Service UUID 已被占用」的信号：实测两个进程各自 `create_async` 都返回 `error: 0`，广播状态也各说各话，唯一的痕迹是互相把对方的广播挤成 3（Aborted）再恢复 2。`BluetoothLEAdvertisementWatcher` 也不行——本机适配器收不到自己发出的广播（监听 6 秒收到 44 个包，来自本机地址的 0 个，而当时广播状态是 Started），WinRT 也没有枚举本机 GATT 注册的接口。所以走进程层——启动时先抢命名互斥体 `BluetoothInput.GattServer`，抢不到就打印提示并退出，不碰 BLE（`pc/single_instance.py`）。互斥体随进程退出由系统释放，不会留僵尸锁。

它只识别同样带这把锁的实例；`E:\repos\ble` 里的旧副本和其他程序不受约束，那种情况仍要按第四节的命令人工查。

### 9. 同一页面开多个标签页也会互抢

每个标签页是一路独立的 Web Bluetooth 客户端，会各自去抢同一台设备。页面加载时会通过 `BroadcastChannel` 探测同伴并提示「请只保留一个」。

第 8、9 条合起来造成过一次很迷惑的「9 秒断一次」：电脑端以为没人订阅 → 心跳被跳过 → 网页看门狗到点判死。看上去像协议 bug，实际是抢连接的连锁反应。

### 10. 下行通知超过 512 字节会被 Android 栈静默丢弃

Windows 报给 `GattSubscribedClient.max_notification_size` 的是 MTU-3，实测为 514 字节；但 Android 蓝牙栈在 `gatt_cl.cc:688 gatt_process_notification` 里会静默丢弃 `value.len > GATT_MAX_ATTR_LEN`（512）的通知，logcat 原话是 `value.len larger than GATT_MAX_ATTR_LEN, discard`。

症状：长剪贴板消息的整分片全被丢掉，只有末尾那个小于 512 字节的短分片能到手机，长度前缀解码器永远拼不完整；后续心跳也被吞，9 秒看门狗判死重连。短消息（小于 512 字节）不受影响。

修法：下行分片夹到 512，即 `min(GattSubscribedClient.max_notification_size, 512)`，代码在 `pc/protocol.py` 的 `downlink_chunk_size`。

### 11. 电脑端重启后网页自动重连无法真正恢复

Chrome 把 GATT 服务/特征值句柄和通知注册状态缓存到页面生命周期结束。电脑端进程重启后属性表换了，但自动重连仍然用旧句柄，也不会重新做服务发现：Android logcat 里每次重连只有 `BTA_GATTC_RegisterForNotifications: notification already registered`，没有 `GATTC_Discover`。

结果：CCCD 没写进新服务端，服务端认为没人订阅、不发心跳；紧接着第一条上行写报 `NotSupportedError: GATT Error Unknown.`。

信号断开但电脑端进程没换时不触发这个问题：句柄仍然有效，重连后 `stopNotifications()` / `startNotifications()` 会把 CCCD 重新写一遍，所以走远再回来能自动连上。

网页的处理：自动重连不限次数，全部在后台进行；前台只在真正连上时更新。「已连接（第 N 段）」这条日志兼作探针，写成功才对外宣布连上，写失败就静默丢弃这次连接继续重试。服务端重启后它会安静地无限重试，只有刷新页面或点「重新连接」重新扫描才能重建 GATT 缓存、真正恢复。

## 七、当前状态与已知限制

**已实测通过：**

- 连接、双特征值订阅、心跳按 3 秒稳定投递。
- 长中文文本上行（有响应写，未复现 `UnicodeDecodeError`）。
- 长剪贴板拉取：660 字全文到达，手机剪贴板写入一致；Android logcat 无 `GATT_MAX_ATTR_LEN` 丢弃。
- 剪贴板推送（手机 → 电脑）。
- 信号断开后自动重连（电脑端进程不变）：服务端日志观察到断开 5 秒后重新订阅成功。

**仍需真机验证：**

- 静默重连：走远断开期间前台不反复刷新，回来后自动恢复。
- IME 组合输入、手势退格/回车、粘贴。
- 切后台 / 锁屏回来后的重连。
- 长时间挂机（十几分钟以上、跨锁屏）的稳定性。
- 多标签页提示。

**已知限制：**

- 电脑端进程重启后，Chrome 的 GATT 缓存会失效；网页会安静地后台重试但无法真正恢复，需刷新或点「重新连接」重新扫描（见坑 11）。
- 网页在后台会被 Chrome 挂起，蓝牙可能被掐；回到前台会自动重连。
- 剪贴板读写在浏览器里受权限限制，`navigator.clipboard.writeText` 失败时内容会留在输入框里，不影响使用。
- 多实例、多标签页会互抢同一台设备（见坑 8、9）。

## 八、调试手法

**看服务端日志**：`pc/logs/ble-<时间戳>.log`。健康状态下应该只有零星三行：

```text
订阅变化：当前 1 个订阅客户端
通知分片上限：512 字节
[网页] 已连接（第 1 段）
```

心跳正常情况下**不刷日志**，只在投递状态变化时记一行 `心跳投递：正常 / 没有订阅客户端`。

**看手机页面的控制台**（比让用户口述强得多，省来回）：

```bash
ADB="$LOCALAPPDATA/Android/Sdk/platform-tools/adb.exe"
MSYS_NO_PATHCONV=1 "$ADB" devices -l          # 可能有 USB 和 Wi-Fi 两路，必要时用 -s 指定
MSYS_NO_PATHCONV=1 "$ADB" -s <serial> forward tcp:9222 localabstract:chrome_devtools_remote
curl -s http://127.0.0.1:9222/json            # 列出标签页，拿 webSocketDebuggerUrl
```

然后用 `uv run --with websocket-client python` 连上去发 `Runtime.enable` + `Runtime.evaluate`，就能读到页面里的 `status`、`event-log` 文本和 console 输出。连 websocket 时记得 `suppress_origin=True`，否则被 403。用完 `adb forward --remove-all` 收尾。

**看 Android 蓝牙栈**：`adb logcat -d -v time | grep -iE "gatt|btgatt|write|notif"`。下行丢包看 `GATT_MAX_ATTR_LEN`；订阅状态看 `RegisterForNotifications`；有没有重新做服务发现看 `GATTC_Discover`。

## 九、环境事实

| 项 | 值 |
|---|---|
| 手机 | vivo V2352A，Android 16（SDK 36），配对的电脑是 `DESKTOP-2QELB5P` |
| Python | 3.14.7，uv 管理，`pc/.venv` |
| 电脑蓝牙 | Intel Wi-Fi 7 BE200，外设角色可用 |
| 浏览器 | Android Chrome（支持 `writeValueWithResponse`；`maxWriteWithoutResponseSize` 要到 Chrome 157） |
| adb | SDK 里的 37.0.0：`"$LOCALAPPDATA/Android/Sdk/platform-tools/adb.exe"`，Git Bash 下加 `MSYS_NO_PATHCONV=1` 前缀 |

## 十、协作约定

- 中文、全角标点；代码块与行内代码内保持原样。
- 提交信息不加 `Co-Authored-By` 署名。
- 不直接删文件，要删就移到项目内 `.trash/`。
- 界面观感由用户本人判断（过渡顺不顺、布局观感、互斥体感）；代理只负责客观断言：日志、编译、DOM/样式读数、控制台报错。
- 独立的搜索、多文件改动、机械核对优先派 subagent；主会话做编排与审阅。
- 改协议时同步上节列出的五个文件。
