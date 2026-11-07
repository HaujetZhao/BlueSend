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

- 上行 `7d9f0002`：手机写、电脑收，声明 `WRITE | WRITE_WITHOUT_RESPONSE`。
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
│   ├── main.py                 入口：日志、单实例锁、启动
│   ├── bluetooth_input\        电脑端包
│   │   ├── server.py           GATT Server 主程序
│   │   ├── logging_setup.py    日志配置（控制台 rich 上色，文件精确到毫秒）
│   │   ├── single_instance.py  单实例锁（Windows 命名互斥体）
│   │   ├── protocol.py         UUID 与下行分片上限
│   │   ├── frame_codec.py      4 字节长度前缀帧编解码
│   │   ├── clipboard.py        Win32 剪贴板读写
│   │   ├── text_input.py       上屏：默认 SendInput，兼容名单改投 WM_CHAR
│   │   ├── upload_server.py    局域网文件上传服务（HTTP，后台线程）
│   │   ├── upload_page.html    上传页（自包含单文件，由上传服务返回）
│   │   ├── config.py           config.toml 读取
│   │   └── config.toml         上屏兼容名单、上传落点
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
uv run python main.py
```

看到 `广播状态：2`（Started）就是在等手机连接。同时会打印 `文件上传入口：http://<局域网IP>:<端口>/?t=…`（没有可用局域网地址时打印「没有可用的局域网地址」）。手机与电脑必须在同一局域网，且首次运行时 Windows 防火墙会弹窗询问是否允许 python 访问网络——拒绝的话上传页打不开，蓝牙不受影响。

日志同时写 `pc/logs/ble-<时间戳>.log`，网页端的连接探针（`已连接（第 N 次）`）也会通过 `log` 消息打进来；断开诊断（`第 N 次断开：…，上次连接存活 N 秒`）只送电脑端看不到的那几种原因——心跳超时、写入失败、接收解析失败，物理断开电脑端自己看得到（订阅清零＋链路状态已断开）。页面上的业务日志则只留在手机上。每次启动建一个日志文件，启动时只保留最近 30 个，更旧的自动清理。

手机端两种访问方式：

- **在线版**：`https://haujetzhao.github.io/Bluetooth-Input/`（由 `.github/workflows/deploy.yml` 在推送 `main` 后构建发布）
- **本地开发**：在 `web\` 下运行 `npm run dev`，手机打开 `https://<电脑局域网IP>:5173`，首次信任自签证书

连上后点左上角的状态药丸 → 选中电脑。卡片最底下那条状态栏会显示「已连接（第 N 次）」（N 是这条链路第几次连上），同一句话也会作为探针写进电脑端日志；断线时显示「连接已断开，正在自动重连…」，断开原因与存活时长写进手机控制台，其中电脑端看不到的几种还会随重连补发进电脑端日志。剪贴板拉取、推送的结果也报在这一行（带字符数）。

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
- 手机 → 电脑：每片 4 字节大端序号前缀（体 508＋头 4＝线包 512），中间分片无响应写连续入队（约 63 KB/s），最后一片带响应写——应答到达即前面分片已排空，它同时是送达确认、下一条消息的栅栏和测速真实终点。电脑端 `UplinkAssembler` 按序号重排（写回调线程池并发会投递乱序）。序号是连接作用域的连续计数，跨消息不归零。单片线包上限由电脑端 `mtu` 消息下发（`min(MTU − 3, 512)`，订阅变化与 MTU 变化时各发一次）；收到之前手机按 LE 默认 ATT_MTU 23 算成 20 字节，任何链路上都写得出去，最坏只是慢。上限不会超过 512：ATT 属性值上限即 512，Chrome 硬拒更长的写——MTU 是外部事实，两边不能各写死一个数。
- **单条消息的 30 秒天花板**：最后一片的写请求排在所有无响应片之后，ATT 事务超时（30 秒）从写请求交给协议栈起算——它等的不是整条消息，而是提交那一刻还堆在协议栈里的积压。2026-11-07 用探针实测（517 / 1033 / 1969 片、508 字节载荷）：无响应写的 resolve 间隔从头到尾恒定约 3.7 毫秒，空口每片约 5.9 毫秒，差出来的 2～2.5 毫秒/片就是积压的增长速度；收尾等待（最后一片带响应写从提交到 ATT 应答）依次是 1.27 / 2.52 / 3.85 秒，与「片数 × 差值」吻合。结论：**队列在 1 MB 以内没有上限**（resolve 间隔不随积压上涨），积压随片数线性增长。按 2 毫秒/片算，30 秒约合 15000 片，512 B 分片下是 7.6 MB——远大于 PC 的 1 MiB 解码上限（对应约 4 秒），所以当前没有风险。片变小则同样秒数对应的字节数等比缩小（20 B/片约 240 KB），低 MTU 下传大消息仍要拆成多条帧；超时的后果按坑 12 处理（丢这条、断开重连，不失步）。
- 电脑 → 手机：分片取 `min(GattSubscribedClient.max_notification_size, 512)`。
- 文件上传不走 BLE：电脑在局域网托管 HTTP 上传页，`net` 消息下发带 token 的候选入口 URL（每次订阅变化时发，连接作用域）；手机用 `/ping` 探测、取第一个可达的，再用 `window.open` 以顶层导航打开（探测依赖本地网络权限，见坑 15）。
- 心跳：电脑每 3 秒发 `{"t":"hb"}`；网页 9 秒没收到任何字节就判定链路已死。
- 一条消息的字节流必须原子发送，中途不能插入别的帧（插了会把载荷拆坏），所以大消息传输期间心跳发不出来。网页看门狗因此按「收到任意字节」计时，不等整条消息拼齐。
- 网页对每次写加上限：基础 2 秒（`WRITE_ACK_TIMEOUT_MS`）＋每片 25 毫秒的排空余量——最后一片的应答要等前面无响应分片在空中排空（实测约 8 毫秒/片），固定 2 秒会把大消息的收尾误杀成断链。超时即认定链路不可用，主动断开重连，不补发（见坑 12）。
- 重连期间网页把消息压进有界待发队列（100 条），宣布连接后按顺序补发；溢出丢最旧的一条。这只针对还没交给写链的消息，和「不做应用层重传」不冲突。
- 电脑读不到剪贴板（被占用）时发 `notice` 而不是空 `clip`，避免清空手机端剪贴板。
- 下行测速载荷每次随机（base64），`benchend` 带 `sha256`，手机重算比对。固定载荷换两片照样是合法 JSON、长度也对，速率看不出问题，只有内容哈希能证明「收到的就是发出的」。
- 改协议时 `protocol.md`、`pc/bluetooth_input/server.py`、`pc/bluetooth_input/protocol.py`、`web/src/logic/protocol.js`、`web/src/logic/frame-codec.js` 必须同步。

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

修法（当时）：手机端改用 `writeValueWithResponse`，由 ATT 层保证先后顺序；上行特征值只声明 `WRITE`。2026-11-07 上行切回无响应写时先赌「逐片 `await` 的提交纪律」能保序——探针 517 片零乱序，转正后第三次测速就抓到乱序（`json.loads` 报 `Extra data`：帧边界完好、内容等长错位），且乱序源大概率不在手机侧而在电脑侧：手机逐片 `await` 串行提交，电脑的 `WriteRequested` 回调却跑在 WinRT 线程池上，并发回调投递 `call_soon_threadsafe` 的顺序会颠倒。现行修法：每片 4 字节序号前缀，电脑端 `UplinkAssembler` 按序重排（连接边界归零，重复片丢弃），乱序跳变记 warning——它与测速哈希金丝雀互补：这里频发即电脑回调乱序，这里安静但哈希失败即手机侧协议栈乱序。

### 5. 广播状态不能读一次了事

`start_advertising()` 异步生效，紧接着读 `provider.advertisement_status` 拿到的是 `ABORTED`（3），日志里全是假警报。要监听 `add_advertisement_status_changed`，事件里是 `STARTED`（2）。

### 6. 服务端进程死后，手机不会感知

Windows 继续在链路层维持连接，浏览器 `gattserverdisconnected` 永远不触发。靠心跳解决：电脑每 3 秒发 `{"t":"hb"}`，网页 9 秒没收到任何消息就判定链路已死并重连。

### 7. 上一次连接没清干净会 `status=133`

原生 App 时代的坑。网页侧现在靠「断开即重连 + `writeChain` 串行化 + 重连前清空接收缓冲」规避。

### 8. 多个 `main.py` 进程同时跑会抢广播

`uv run` 外面包了一层，停后台任务只杀到包装进程，真正的 python 子进程还活着。两个进程用同一个 Service UUID 各自注册、各自广播，症状是 `GATT Error Unknown`、刚连就断。

BLE 接口本身给不出「这个 Service UUID 已被占用」的信号：实测两个进程各自 `create_async` 都返回 `error: 0`，广播状态也各说各话，唯一的痕迹是互相把对方的广播挤成 3（Aborted）再恢复 2。`BluetoothLEAdvertisementWatcher` 也不行——本机适配器收不到自己发出的广播（监听 6 秒收到 44 个包，来自本机地址的 0 个，而当时广播状态是 Started），WinRT 也没有枚举本机 GATT 注册的接口。所以走进程层——启动时先抢命名互斥体 `BluetoothInput.GattServer`，抢不到就打印提示并退出，不碰 BLE（`pc/bluetooth_input/single_instance.py`）。互斥体随进程退出由系统释放，不会留僵尸锁。

它只识别同样带这把锁的实例；`E:\repos\ble` 里的旧副本和其他程序不受约束，那种情况仍要按第四节的命令人工查。

### 9. 同一页面开多个标签页也会互抢

每个标签页是一路独立的 Web Bluetooth 客户端，会各自去抢同一台设备。页面加载时会通过 `BroadcastChannel` 探测同伴并提示「请只保留一个」。

第 8、9 条合起来造成过一次很迷惑的「9 秒断一次」：电脑端以为没人订阅 → 心跳被跳过 → 网页看门狗到点判死。看上去像协议 bug，实际是抢连接的连锁反应。

### 10. 下行通知超过 512 字节会被 Android 栈静默丢弃

Windows 报给 `GattSubscribedClient.max_notification_size` 的是 MTU-3，实测为 514 字节；但 Android 蓝牙栈在 `gatt_cl.cc:688 gatt_process_notification` 里会静默丢弃 `value.len > GATT_MAX_ATTR_LEN`（512）的通知，logcat 原话是 `value.len larger than GATT_MAX_ATTR_LEN, discard`。

症状：长剪贴板消息的整分片全被丢掉，只有末尾那个小于 512 字节的短分片能到手机，长度前缀解码器永远拼不完整；后续心跳也被吞，9 秒看门狗判死重连。短消息（小于 512 字节）不受影响。

修法：下行分片夹到 512，即 `min(GattSubscribedClient.max_notification_size, 512)`，代码在 `pc/bluetooth_input/protocol.py` 的 `downlink_chunk_size`。

### 11. 电脑端重启后网页自动重连无法真正恢复

Chrome 把 GATT 服务/特征值句柄和通知注册状态缓存到页面生命周期结束。电脑端进程重启后属性表换了，但自动重连仍然用旧句柄，也不会重新做服务发现：Android logcat 里每次重连只有 `BTA_GATTC_RegisterForNotifications: notification already registered`，没有 `GATTC_Discover`。

结果：CCCD 没写进新服务端，服务端认为没人订阅、不发心跳；紧接着第一条上行写报 `NotSupportedError: GATT Error Unknown.`。

信号断开但电脑端进程没换时不触发这个问题：句柄仍然有效，重连后 `stopNotifications()` / `startNotifications()` 会把 CCCD 重新写一遍，所以走远再回来能自动连上。

网页的处理：自动重连不限次数，全部在后台进行；前台只在真正连上时更新。「已连接（第 N 次）」这条消息兼作探针——先作为 `log` 写进电脑端日志，写成功才对外宣布连上（状态栏显示同一句话），写失败就静默丢弃这次连接继续重试。服务端重启后它会安静地无限重试，只有刷新页面或点状态药丸重新扫描才能重建 GATT 缓存、真正恢复。

### 12. 半帧必须随连接一起丢弃

上行字节流是**连接作用域**的。一次多分片写入中途失败（信号差、链路半断），电脑端解码器里会留下半帧；连不清理就重连，新连接的字节会接在半帧后面，长度前缀被读成任意值——可能是上 GB，解码器从此永远凑不齐。表现极隐蔽：ATT 层写仍有响应、探针写成功、网页显示「已连接」，但键盘和剪贴板全部石沉大海，只能重启电脑端。半帧的载荷如果不巧不是合法 UTF-8，还会让解码时抛异常。

原则是**连接边界 = 帧边界**，两侧都按这个来：

- 网页：每次带响应写加 2 秒上限；超时或失败就认定整条流不可信，代际加一、丢弃写队列、主动 `gatt.disconnect()`（不然电脑端看不到会话结束），2 秒后重连。不做应用层重传——「已送达但 ACK 丢失」时重发会造成重复输入，`key` 尤其致命。
- 电脑端：订阅变化（连接边界）时复位解码器；帧长上限 1 MiB；坏 UTF-8 丢弃并复位缓冲；通知分片失败时中止本条消息剩余分片。

代价是失败的那条消息会丢，最坏情况是一次发送没成功加几秒重连，不会失步，也不会崩进程。

### 13. 中文输入法会打乱 SendInput 的 Unicode 注入

`text` 消息默认用 `keyboard.write`（SendInput + `KEYEVENTF_UNICODE`）。焦点应用挂着中文输入法时，全角中文标点后的 `KEYUP` 会被输入法吞掉，Qt5 应用（微信、Telegram）按错乱的输入法状态提交，表现为标点后第一个字被替换成同一个标点。原生控件（记事本）、CMD、PowerShell、Windows Terminal 不受影响。

修法：`pc/bluetooth_input/config.toml` 的 `wm_char_apps` 列出进程名（`Weixin.exe`、`Telegram.exe`），命中的改投 `WM_CHAR`（`pc/bluetooth_input/text_input.py`）。不能全局替换——Windows Terminal 收不到 `WM_CHAR`。完整复现与证据见 [docs/ime-typing-bug.md](docs/ime-typing-bug.md)。

### 14. 上行比下行慢一个数量级：带响应写是停等协议

真机测速（页面「测上行」「测下行」两颗按钮，各 256 KB）：下行约 3.3 秒（≈78 KB/s），上行约 33 秒（≈8 KB/s）。

- **上行**用 `writeValueWithResponse`，每片必须等到 ATT 应答才能发下一片，等于链路里永远只有一个包在途。实测每片 512 字节耗时约 64 毫秒，正好是两个连接间隔（约 30 毫秒），所以吞吐 ≈ 512 B ÷ 64 ms。这是协议节奏，不是 bug。
- **下行**用通知，没有应用层应答：Windows 把分片塞进控制器队列后连续发送，一个连接间隔能塞好几包，快了近十倍。
- **顺序性两边都有**：带响应写由 ATT 保证——ATT 规定一个连接上同时只能有一个未完成的请求，客户端协议栈自己不会并发发第二个（我们逐片 `await` 只是执行方式，恰好与这条规则重合）。通知尽管没有应用层应答，但 BLE 链路层对每个链路层包按序可靠确认并重传，GATT Server 又按调用顺序入队（`send_lock` 保证一条消息整条入队后才发下一条）。坑 4 里的乱序只发生在**无响应写**，那是 ATT 命令写不保证顺序。
- **顺序保证不贵，同步确认才贵**：链路层是双向对称的，上行方向的 LL 包本来就按序可靠到达——「用链路层保证顺序」我们一直在用。带响应写慢的不是它保证了顺序，而是它把确认做成了同步往返，每 512 字节一次。链路层的 ACK 在双方控制器里就完成了，不暴露给应用，所以它替代不了 ATT 应答，也带不来背压。
- **下行的发送耗时要不到**：`notify_value_async` 返回时数据只是进了 Windows 的发送队列（256 KB 入队 0.4 秒，手机真收完 2.7 秒），所以在电脑端计时会得到一个假数，只能在手机端按收到的字节算。
- 要提高上行吞吐只能改用无响应写、自己在应用层做序号和窗口，代价是协议复杂度和坑 4 的乱序风险。**2026-11-07 已做**：探针实测无响应写 517 片零缺失，4.09 秒 256 KB（63 KB/s，停等的 8 倍）；先省掉序号直接转正，第三次测速即被乱序打脸（见坑 4），补上 4 字节序号＋电脑端重排后才算成。最终形态：中间分片无响应写＋序号前缀、最后一片带响应写（应答到达即前面分片已排空，兼作送达确认与测速真实终点）、`UplinkAssembler` 按序重排。两个连带教训：①**入队 ≠ 空口**：手机端无响应写全部 resolve 只要 2.0 秒，空口要 4.09 秒，积压约 2 秒躺在手机侧协议栈里——本地任何「写完」回调都量不到真实速率，终点必须锚定对端（最后一片的 ATT 应答）；②那次积压把随后的带响应写应答压过 2 秒超时线，造成一次假断链，所以写超时按片数放宽（基础 2 秒＋每片 25 毫秒）。
- **生态对照**（2026-11-07 调查 web-bluetooth-dfu、Web-Bluetooth-Terminal、muse-js）：主流 Web BLE 库无一使用无响应写，分片全部写死 20 字节（wb-dfu 实测 0.7 KB/s，作者称加大包「会莫名失稳」）；可靠性全是「链路层保单包＋应用层消息/对象级校验」，无逐包应用层重传——与本项目的校验结构同宗，差别只在传输端更保守。真正的吞吐天花板在连接间隔，两端（Web Bluetooth 与 WinRT）都无 API 可调，无响应写已把网页端能吃的吃满。

### 15. HTTPS 页面直连局域网 HTTP：混合内容与本地网络权限

在线版跑在 GitHub Pages 的 HTTPS 下，浏览器把「HTTPS 页面里的 fetch/XHR/WebSocket 去连 HTTP 地址」当作混合内容拦截，局域网 IP 也不在 localhost 白名单里。但 Chrome 的本地网络访问（LNA，约 141 起默认启用）给了一条正路：`fetch` 带 `targetAddressSpace: 'local'`，用户授权「本地网络」权限后，这类请求豁免混合内容。权限按站点持久化，首次必须由用户手势触发——不能在收到 `net` 后静默探测。

现在的做法：手机主页面用 `fetch('/ping', { mode: 'no-cors', targetAddressSpace: 'local' })` 探测候选地址；已授权时自动探测、探不到就禁用「发送文件」，未授权时按钮可点、点击即触发授权提示。真正传文件仍由电脑托管上传页、手机用**顶层导航**打开——上传页与电脑服务同源，传文件不涉及 CORS 与混合内容。

必须守住的点：① 探测请求要显式声明 `targetAddressSpace`，否则混合内容检查在 DNS 之前就把请求拦了；② 权限还是 prompt 时不要自动探测，浏览器会静默拒绝；③ 不要把上传逻辑搬回主页面用 fetch 直传——要处理 CORS 与预检，首次仍要授权，没有收益。也别让电脑跑自签 HTTPS：手机要装一次 CA，证书还绑局域网 IP，换网络就失效。

## 七、当前状态与已知限制

**已实测通过：**

- 连接、双特征值订阅、心跳按 3 秒稳定投递。
- 长中文文本上行（有响应写，未复现 `UnicodeDecodeError`）。
- 长剪贴板拉取：660 字全文到达，手机剪贴板写入一致；Android logcat 无 `GATT_MAX_ATTR_LEN` 丢弃。
- 剪贴板推送（手机 → 电脑）。
- 信号断开后自动重连（电脑端进程不变）：服务端日志观察到断开 5 秒后重新订阅成功。
- 局域网传文件：手机打开上传页、多选按序上传、桌面／下载两个落点切换，均真机验证通过。

**仍需真机验证：**

- 静默重连：走远断开期间前台不反复刷新，回来后自动恢复。
- IME 组合输入、手势退格/回车、粘贴。
- 切后台 / 锁屏回来后的重连。
- 长时间挂机（十几分钟以上、跨锁屏）的稳定性。
- 多标签页提示。

**已知限制：**

- 电脑端进程重启后，Chrome 的 GATT 缓存会失效；网页会安静地后台重试但无法真正恢复，需刷新或点状态药丸重新扫描（见坑 11）。
- 网页在后台会被 Chrome 挂起，蓝牙可能被掐；回到前台会自动重连。
- 剪贴板读写在浏览器里受权限限制，`navigator.clipboard.writeText` 失败时内容会留在输入框里，不影响使用。
- PWA 有新版本时不自动刷新：事件行会出现「有新版本，点击刷新」，点击后重载生效。
- 多实例、多标签页会互抢同一台设备（见坑 8、9）。
- 文件上传要求手机与电脑在同一局域网；Windows 防火墙首次需放行 python 入站，否则上传页打不开（蓝牙不受影响）。
- 文件上传结果不回流蓝牙：进度只在上传页显示，主页面不感知。
- 传输途中强制关闭电脑端（Ctrl+C）时，目标目录可能残留隐藏的 `.bt-upload-*.part`，手动删除即可。

## 八、调试手法

**看服务端日志**：`pc/logs/ble-<时间戳>.log`。健康状态下应该只有零星三行：

```text
订阅变化：当前 1 个订阅客户端
通知分片上限：512 字节
[网页] 已连接（第 1 次）
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
