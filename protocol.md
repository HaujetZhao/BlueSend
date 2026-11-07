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

电脑发往手机：

| `t` | `v` | 含义 |
|---|---|---|
| `hb` | — | 心跳，每 3 秒一次 |
| `pong` | — | 对 `ping` 的回应 |
| `clip` | 字符串 | 电脑剪贴板内容 |
| `notice` | 字符串 | 需要显示给用户的通知（如读取剪贴板失败） |

心跳兼作链路存活判定：网页端 9 秒内没收到任何消息就判定链路已死，断开重连。
