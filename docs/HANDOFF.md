# 交接文档：手机与电脑的 BLE 通道

更新于 2026-11-07 深夜。明天（11-08）在这个仓库继续干，读完这份就能接上。

## 一、项目是什么

自用工具：**手机与电脑之间畅快传信息**（打字直接上屏、剪贴板互推）。

技术路线已定：**电脑做 BLE 外设，手机开网页连上去**。选 BLE 而不是 RFCOMM，唯一的理由是手机端能用网页——不用装 App、不用过应用商店；代价是 Windows 侧只能自己用 WinRT 写 GATT Server（没有成熟的高层库）。

**仓库现状**：`E:\repos\Bluetooth-Input`，前端已迁到 `refactor/vue` 分支（Vue 3 + Vite），`main` 仍是旧的原生 JS 前端。`origin` 指向 GitHub。

血缘：代码最初在 `E:\repos\ble` 里成形（那里还试过原生 Android App 路线，卡在「30 秒自动断开」），2026-11-07 合并进本仓库。`E:\repos\ble` 现在是冻结的旧副本，没有价值，可以随时丢弃；原生 App 源码未随本仓库保留（`.trash/` 中没有该目录）。

## 二、架构

| 角色 | 端 | 技术 |
|---|---|---|
| GATT Server（外设，广播） | Windows 电脑 | Python 3.14 + `winrt-Windows.Devices.Bluetooth.GenericAttributeProfile` |
| GATT Client（中心，主动连接） | 手机 | 网页 + Web Bluetooth（Android Chrome） |
| 网页承载 | GitHub Pages（`haujetzhao.github.io/Bluetooth-Input/`），或本地 `serve_web.py` | 静态 HTTPS 页面（Web Bluetooth 要求安全上下文） |

**不能用 bleak。** bleak 只支持 Windows 做中心，本项目角色反过来，必须直接用 WinRT 的 `GattServiceProvider`。

单一特征值双向通道，UUID 与帧格式见 [protocol.md](../protocol.md)。

## 三、代码地图

```text
E:\repos\Bluetooth-Input\
├── readme.md                   对外说明
├── protocol.md                 协议的唯一事实来源
├── index.html                  Vite 入口
├── src\
│   ├── App.vue                 手机端页面与输入交互
│   ├── styles.css
│   ├── logic\protocol.js       UUID 与链路参数
│   ├── logic\frame-codec.js    帧编解码
│   ├── logic\ble-client.js     连接、重连、心跳、写队列
│   └── composables\useBle.js   Vue 响应式封装
├── public\                     PWA 图标
├── certs\{cert,key}.pem        自签证书
├── .github\workflows\deploy.yml  GitHub Actions：构建 PWA 并发布到 Pages
├── serve_web.py                托管 dist/ 的 HTTPS 静态服务
├── pc\                         电脑端
└── .trash\                     废弃文件暂存区
```

## 四、怎么跑

先从 PowerShell 确认没有僵尸实例——**多实例会互相抢广播，症状极难认**：

```powershell
Get-CimInstance Win32_Process -Filter "Name like 'python%'" | Select-Object ProcessId,CommandLine
```

再启动电脑端：

```powershell
cd E:\repos\Bluetooth-Input\pc
uv run python server.py
```

看到 `广播状态：Started`（数值 2）就是在等手机连接。日志同时写 `pc/logs/ble-<时间戳>.log`，网页端日志也会通过 `log` 消息打进来。

手机端三种访问方式：

- **在线版**：`https://haujetzhao.github.io/Bluetooth-Input/`（由 `.github/workflows/deploy.yml` 在推送 `main` 后构建发布）
- **本地开发**：电脑运行 `npm run dev`，手机打开 `https://<电脑局域网IP>:5173`，首次信任自签证书
- **单文件本地托管**：`npm run build` 后运行 `uv run --project pc python serve_web.py`，手机打开 `https://<电脑局域网IP>:8443`

连上后点「扫描连接」→ 选中电脑。页面状态栏下面那行小字会写「已连接（第 N 段）」，断开时写原因和上一段存活时长。

前端命令：

```powershell
npm install
npm run dev        # HTTPS 开发服务器，手机可访问
npm test           # 帧编解码单测
npm run build      # 单文件产物 dist/index.html
npm run build:pwa  # PWA 产物，供 GitHub Pages 部署
```

## 五、踩过的坑

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

修法：手机端改用 `writeValueWithResponse`，由 ATT 层保证先后顺序。旧代码用 `writeValueWithoutResponse` 抢速度，代价就是没有顺序语义。

### 5. 广播状态不能读一次了事

`start_advertising()` 异步生效，紧接着读 `provider.advertisement_status` 拿到的是 `ABORTED`（3），日志里全是假警报。要监听 `add_advertisement_status_changed`，事件里是 `STARTED`（2）。

### 6. 服务端进程死后，手机不会感知

Windows 继续在链路层维持连接，浏览器 `gattserverdisconnected` 永远不触发。靠心跳解决：电脑每 3 秒发 `{"t":"hb"}`，网页 9 秒没收到任何消息就判定链路已死并重连。

### 7. 上一次连接没清干净会 `status=133`

原生 App 时代的坑。网页侧现在靠「断开即重连 + `writeChain` 串行化 + 重连前清空接收缓冲」规避。

### 8. 多个 `server.py` 进程同时跑会抢广播

`uv run` 外面包了一层，停后台任务只杀到包装进程，真正的 python 子进程还活着。两个进程用同一个 Service UUID 各自注册、各自广播，症状是 `GATT Error Unknown`、刚连就断。启动前先按第四节的命令查一遍。

### 9. 同一页面开多个标签页也会互抢

每个标签页是一路独立的 Web Bluetooth 客户端，会各自去抢同一台设备。现在页面加载时会通过 `BroadcastChannel` 探测同伴并提示「请只保留一个」。

第 8、9 条合起来造成过一次很迷惑的「9 秒断一次」：电脑端以为没人订阅 → 心跳被跳过 → 网页看门狗到点判死。看上去像协议 bug，实际是抢连接的连锁反应。

## 六、环境事实

| 项 | 值 |
|---|---|
| 手机 | vivo V2352A，Android 16（SDK 36），配对的电脑是 `DESKTOP-2QELB5P` |
| Python | 3.14.7，uv 管理，`pc/.venv` |
| 电脑蓝牙 | Intel Wi-Fi 7 BE200，外设角色可用 |
| 浏览器 | Android Chrome（支持 `writeValueWithResponse`；`maxWriteWithoutResponseSize` 要到 Chrome 157） |
| adb | SDK 里的 37.0.0：`"$LOCALAPPDATA/Android/Sdk/platform-tools/adb.exe"`，Git Bash 下加 `MSYS_NO_PATHCONV=1` 前缀 |

## 七、仓库状态与待办

**已验证通过（旧原生 JS 前端，2026-11-07 实测）：**

- 网页经 HTTPS 打开、扫描到电脑并连上
- 长中文文本完整上屏，未复现 `UnicodeDecodeError`
- 连接持续数分钟不中断，心跳按 3 秒稳定投递，通知按 514 字节分片送达
- 即时输入（逐字上屏、退格、回车）与剪贴板推送、拉取两个方向
- 原「30 秒断开」未复现
- `cd pc && uv run pytest` → 7 passed

**Vue 重写后尚未真机验收：**

- 本机已通过：`npm test` 8 项、`npm run build`（单文件）、`npm run build:pwa`、HTTPS dev server 返回 200
- 待手机实测：连接与长中文文本、IME 组合输入、手势退格/回车、粘贴、剪贴板双向、杀掉电脑端进程后 9 秒判死并自动接回、切后台/锁屏回来后的重连、多标签页提示

**接下来的优先级：**

1. 上线顺序不能颠倒：先合并 `refactor/vue` 到 `main` 并推送（工作流文件随之上线），再把仓库 Settings → Pages 的 Source 从「Deploy from a branch（`main:/`）」改成「GitHub Actions」，最后手动触发一次 `Deploy to GitHub Pages`。顺序反了会白屏——根目录的 `index.html` 是 Vite 入口，不是可直接分发的页面
2. 手机真机验收上面的 Vue 版本
3. 长时间挂机（十几分钟以上、跨锁屏）看是否稳
4. 之后才谈演进：GUI、历史记录、文件传输

**已知取舍：**

- 网页在后台会被 Chrome 挂起，蓝牙可能被掐；回到前台会自动重连
- 剪贴板读写在浏览器里受权限限制，`navigator.clipboard.writeText` 失败时内容会留在输入框里，不影响使用

## 八、调试手法

**看服务端日志**：`pc/logs/ble-<时间戳>.log`。健康状态下应该只有零星三行：

```
订阅变化：当前 1 个订阅客户端
通知分片上限：514 字节
[网页] 已连接（第 1 段）
```

心跳正常情况下**不刷日志**，只在投递状态变化时记一行 `心跳投递：正常 / 没有订阅客户端`。

**看手机页面的控制台**（比让用户口述强得多，省来回）：

```bash
ADB="$LOCALAPPDATA/Android/Sdk/platform-tools/adb.exe"
MSYS_NO_PATHCONV=1 "$ADB" forward tcp:9222 localabstract:chrome_devtools_remote
curl -s http://127.0.0.1:9222/json      # 列出标签页，拿 webSocketDebuggerUrl
```

然后用 `uv run --with websocket-client python` 连上去发 `Runtime.enable` + `Runtime.evaluate`，就能读到页面里的 `status`、`event-log` 文本和 console 输出。连 websocket 时记得 `suppress_origin=True`，否则被 403。用完 `adb forward --remove-all` 收尾。

## 九、协作约定

- 中文、全角标点；代码块与行内代码内保持原样
- 提交信息不加 `Co-Authored-By`
- 不直接删文件，要删就移到项目内 `.trash/`
- 界面观感由用户本人判断（过渡顺不顺、布局观感），我只负责客观断言：日志、编译、DOM/样式读数
- 改协议时 `protocol.md`、`pc/server.py`、`src/logic/protocol.js`、`src/logic/frame-codec.js` 必须同步
- 独立的搜索、多文件改动、机械核对优先派 subagent，主会话做编排与审阅
