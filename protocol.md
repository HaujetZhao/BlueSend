# BLE 通信协议

## 角色

- 电脑：GATT Server（外设），持续广播自定义 Service
- 手机：GATT Client（中心），用网页（Web Bluetooth）连接

网页需要安全上下文：在线版直接跑在 GitHub Pages 的 HTTPS 下；本地则用 Vite dev server（`web/` 目录下的 `npm run dev`），手机信任一次自签证书即可打开页面，不需要装 App。

## UUID

| 用途 | UUID |
|---|---|
| Service | `7d9f0001-3c4e-4b6a-9f2e-1a2b3c4d5e6f` |
| 上行 Characteristic（手机写 → 电脑收） | `7d9f0002-3c4e-4b6a-9f2e-1a2b3c4d5e6f` |
| 下行 Characteristic（电脑发 → 手机收） | `7d9f0003-3c4e-4b6a-9f2e-1a2b3c4d5e6f` |
| CCCD（标准，只挂在下行） | `00002902-0000-1000-8000-00805f9b34fb` |

上下行各有自己的特征值，属性即契约：上行只声明 `WRITE`，下行只声明 `NOTIFY`，保护级别都是 `PLAIN`。手机在向上行特征值写之前不需要订阅任何东西，订阅状态只影响下行。

## 帧格式

| 字段 | 长度 | 说明 |
|---|---|---|
| payload length | 4 字节，大端无符号 | JSON 字节数 |
| payload | N 字节 | UTF-8 编码的 JSON 对象 |

一条消息可以横跨多次写入或通知，接收端累积字节流，凑满 `4 + length` 才产出一条消息。

## 切片

- **手机 → 电脑**：用 `writeValueWithResponse`。ATT 保证有响应写的先后顺序，这是长文本不乱序的关键；无响应写没有顺序保证，曾导致第 10、11 分片颠倒、UTF-8 解码报错。上行特征值只声明 `WRITE`，无响应写在属性层就没有，客户端想用也无从下手。单包大小取 `maxWriteWithResponseSize`，拿不到就用 180 字节。
- **电脑 → 手机**：取 `min(GattSubscribedClient.max_notification_size, 512)` 切片。`max_notification_size` 是 MTU-3（实测 514），但 Android 的 GATT 栈会静默丢弃超过 512 字节的通知（`GATT_MAX_ATTR_LEN`），必须夹到 512。

## 消息

手机发往电脑：

| `t` | `v` | 含义 |
|---|---|---|
| `text` | 字符串 | 直接键入文本 |
| `key` | `enter` / `backspace` | 敲一个键 |
| `clip` | 字符串 | 覆盖电脑剪贴板 |
| `pull` | — | 请求电脑剪贴板，电脑回 `clip` |
| `ping` | — | 探测，电脑回 `pong` |
| `log` | 字符串 | 网页日志，落到电脑端日志文件 |
| `benchup` | 字符串（256 KB） | 上行测速载荷，电脑只计数 |
| `benchdown` | — | 请求下行测速 |

电脑发往手机：

| `t` | `v` | 含义 |
|---|---|---|
| `hb` | — | 心跳，每 3 秒一次 |
| `pong` | — | 对 `ping` 的回应 |
| `clip` | 字符串 | 电脑剪贴板内容 |
| `notice` | 字符串 | 需要显示给用户的通知（如读取剪贴板失败） |
| `benchdata` | 字符串（256 KB） | 下行测速载荷，手机收到即丢 |
| `benchend` | 见下 | 下行测速结果：`bytes` 字节数、`ms` 电脑侧发送耗时、`chunk` 实际单包大小 |

## 测速

一次测速传一条 256 KB 的消息，载荷是重复的可打印 ASCII（JSON 编码不产生转义，字符数与字节数一致）。这个尺寸来自 `BENCH_BYTES`，两端必须一致。

- **上行**：手机发一条 `benchup`，从调用写链开始计时，到最后一片收到 ATT 应答结束。速率 = 256 KB ÷ 耗时。
- **下行**：手机发 `benchdown`，电脑发一条 `benchdata` 并从进入通知循环计时到最后一片发完，再把 `ms` 放进 `benchend` 回报。

以发送方的耗时为口径，因为它包含 ATT 往返，正是链路吞吐的决定因素。

一条消息的字节流必须在链路上原子发送，中途插入别的帧会把载荷拆坏。所以 256 KB 传输期间心跳发不出来，网页端的看门狗改成**收到任何字节就重新计时**，不再等整条消息拼齐。

心跳兼作链路存活判定：网页端 9 秒内没收到任何字节就判定链路已死，断开重连。
