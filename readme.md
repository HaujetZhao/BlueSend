# Bluetooth Input

通过低功耗蓝牙 (BLE)，用手机给电脑打字。

**无需安装任何手机 App** — 手机浏览器打开网页即可连接，电脑端运行一个小服务即可。

> [!NOTE]
> 手机和电脑**不需要在同一网络下**，所有数据通过 BLE 蓝牙物理通道直传。

## 功能

- **即时输入** — 手机打字实时出现在电脑光标处，就像用物理键盘一样
- **经典发送** — 输入整段文字后一次性发送
- **剪贴板同步** — 手机与电脑之间双向推送/拉取剪贴板内容
- **自动重连** — 蓝牙断开后后台静默重连，无需手动干预
- **链路自检** — 电脑每 3 秒发一次心跳，网页端 9 秒收不到就判定断链并自动重连

## 使用方法

### 1. 电脑端启动服务

需要 Python 3.12+，依赖用 [uv](https://docs.astral.sh/uv/) 管理：

```powershell
cd pc
uv run python server.py
```

看到「广播状态：Started」就已经在等手机连接了。

### 2. 手机端连接

手机浏览器打开 **https://haujetzhao.github.io/Bluetooth-Input/** ，点「扫描连接」选中你的电脑即可。

如果不想走 GitHub Pages，也可以在本地起 HTTPS 服务（Web Bluetooth 要求安全上下文）：

```powershell
uv run --project pc python serve_web.py
# 手机访问 https://<电脑局域网IP>:8443 ，需要信任一次自签证书
```

## 手机浏览器要求

- **Android**：Chrome、Edge 等 Chromium 内核浏览器
- **iOS**：需使用 [Bluefy](https://apps.apple.com/cn/app/bluefy-web-ble-browser/id1492828568) 等支持 Web Bluetooth 的浏览器

> 同一个页面只开一个标签页。多个标签页会各自建立一路蓝牙客户端去抢同一台设备，表现为 `GATT Error Unknown` 或刚连就断。

## 目录结构

```
├── index.html              手机端页面
├── static/                 页面脚本、样式与自签证书
├── serve_web.py            本地 HTTPS 静态服务（纯标准库）
├── protocol.md             协议：UUID、帧格式、消息类型
├── pc/                     电脑端
│   ├── server.py           WinRT GATT Server：广播、写请求应答、JSON 分发、心跳
│   ├── frame_codec.py      帧编解码
│   ├── clipboard.py        Win32 剪贴板读写
│   └── tests/              帧编解码单测
├── docs/HANDOFF.md         开发交接文档（架构、踩过的坑、环境事实）
└── bt_serial_receiver.py   早期 RFCOMM 串口方案，保留备用，未接入当前架构
```

## 开发

```powershell
cd pc
uv run pytest          # 帧编解码单测
```

改协议时，`protocol.md`、`pc/server.py`、`static/app.js` 三处必须同步。
