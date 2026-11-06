# 交接文档：手机与电脑的 BLE 通道

更新于 2026-11-07。这份文档给下一个上下文窗口用，读完就能接着干。

## 一、项目是什么

自用工具：**手机与电脑之间畅快传信息**（打字直接上屏、剪贴板互推）。

技术路线已定：**电脑做 BLE 外设，手机开网页连上去**。选 BLE 而不是 RFCOMM，唯一的理由是手机端能用网页——不用装 App、不用过应用商店；代价是 Windows 侧只能自己用 WinRT 写 GATT Server（没有成熟的高层库）。

血缘：代码最早在 `E:\repos\ble` 里成形（原生 Android App 与 Web Bluetooth 网页两条路都试过，原生 App 那条卡在「30 秒自动断开」），2026-11-07 合并回本仓库；原生 App 的代码留在这个仓库的 `.trash/android-legacy-2026-11-07/`，`.trash/` 不入库。

## 二、架构

| 角色 | 端 | 技术 |
|---|---|---|
| GATT Server（外设，广播） | Windows 电脑 | Python 3.14 + `winrt-Windows.Devices.Bluetooth.GenericAttributeProfile` |
| GATT Client（中心，主动连接） | 手机 | 网页 + Web Bluetooth（Android Chrome） |
| 网页承载 | GitHub Pages（`haujetzhao.github.io/Bluetooth-Input/`），或本地 `serve_web.py` | 静态 HTTPS 页面（Web Bluetooth 要求安全上下文） |

**不能用 bleak。** bleak 只支持 Windows 做中心，本项目角色反过来，必须直接用 WinRT 的 `GattServiceProvider`。

单一特征值双向通道，UUID 与帧格式见 [protocol.md](../protocol.md)。

## 三、代码地图

```
E:\repos\Bluetooth-Input\
├── readme.md                   对外说明
├── protocol.md                 协议的唯一事实来源（UUID、帧格式、消息类型）
├── index.html                  手机端页面
├── static\app.js               网页逻辑：连接、帧编解码、MTU 切片、即时输入、剪贴板
├── static\style.css
├── static\{cert,key}.pem       自签证书，手机需信任一次
├── serve_web.py                HTTPS 静态服务（纯标准库）
├── pc\
│   ├── server.py               WinRT GATT Server：广播、写请求同步应答、JSON 分发、按 MTU 分片通知
│   ├── frame_codec.py          帧编解码（4 字节长度 + UTF-8）
│   ├── protocol.py             UUID 常量
│   ├── clipboard.py            Win32 剪贴板读写（ctypes，零依赖）
│   ├── pyproject.toml          uv 依赖（winrt-*、keyboard）
│   └── tests\test_frame_codec.py
└── .trash\                     废弃文件的暂存区，可随时手动清掉
```

## 四、怎么跑

```bash
# 电脑端（一个终端）
cd pc && uv run python server.py

# 网页服务（另一个终端，只在本地托管时需要；日常用 GitHub Pages 就够）
uv run python serve_web.py   # 会打印手机访问用的 https://<局域网IP>:8443
```

手机上打开该地址（首次要信任自签证书）→ 点「扫描连接」→ 选中电脑。之后打字、点剪贴板按钮即可。

日志在 `pc/logs/ble-<时间戳>.log`，网页端日志也会通过 `log` 消息打进来。

## 五、踩过的坑

### 1. WinRT 事件处理器不接受 async 函数

```text
TypeError: 'Windows.Foundation.TypedEventHandler' cannot take ... an async def function,
because WinRT does not await what it returns
```

必须传普通函数。

### 2. `deferral` / `respond` 有线程亲和性——这就是「30 秒断开」的根因

上一代代码在 WinRT 回调里 `get_deferral()`，把活儿丢回 asyncio 线程，再在那边 `complete()`。跨线程完成会抛异常，而异常被吞在 `finally` 里，于是 Windows 永远在等那次写请求——ATT 事务 30 秒超时，整条链路断开。

现在的写法：写请求在回调线程上同步 `get_request_async().get()` 取到值、同步 `respond()`，只把字节投递给 asyncio 队列，业务处理才回到 asyncio 线程。

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

调试中遇到过：残留进程让新进程广播失败。测试前先确认没有僵尸进程。

## 六、环境事实

| 项 | 值 |
|---|---|
| 手机 | vivo V2352A，Android 16（SDK 36），配对的电脑是 `DESKTOP-2QELB5P` |
| Python | 3.14.7，uv 管理，`pc/.venv` |
| 电脑蓝牙 | Intel Wi-Fi 7 BE200，外设角色可用 |
| 浏览器 | Android Chrome（Web Bluetooth 支持 `writeValueWithResponse`；`maxWriteWithoutResponseSize` 要到 Chrome 157） |

## 七、状态与待办

**已实测通过（2026-11-07）：**

- 网页经 HTTPS 打开、扫描到电脑并连上
- 长中文文本完整上屏，未复现 `UnicodeDecodeError`
- 连接持续数分钟不中断，心跳按 3 秒稳定投递，通知按 514 字节分片送达
- 即时输入（逐字上屏、退格、回车）与剪贴板推送、拉取两个方向
- 原「30 秒断开」未复现（那套 deferral 跨线程写法已从流程里彻底移除）

**已定位的环境型故障（不是协议问题）：**

- 同一页面开多个标签页 + 残留多个 `server.py` 实例 → 多路客户端抢同一台设备，表现为 `GATT Error Unknown`、刚连就断、心跳被跳过、9 秒看门狗误杀。现在网页端开第二份页面会直接提示，电脑端启动前也应确认没有僵尸实例

**待办：**

1. 长时间挂机测试（十几分钟以上、跨锁屏）
2. 断开后的自动重连实测（杀掉电脑端进程验证）
3. 后续演进再议：GUI、多条历史、文件传输

**已知取舍：**

- 网页在后台会被 Chrome 挂起，蓝牙可能被掐；回到前台会自动重连
- 剪贴板读写在浏览器里受权限限制，`navigator.clipboard.writeText` 失败时内容会留在输入框里，不影响使用

## 八、给下一个上下文窗口的提醒

- 改协议时 `protocol.md`、`pc/server.py`、`static/app.js` 三处必须同步
- 用户偏好中文、全角标点；提交信息不加 `Co-Authored-By`
- 界面观感由用户本人判断，我只负责客观日志与编译验证
- 不要直接删文件，要删就移到项目内 `.trash/`
