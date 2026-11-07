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

### 1. 安装依赖

```powershell
npm install
```

### 2. 电脑端启动服务

需要 Python 3.12+，依赖用 [uv](https://docs.astral.sh/uv/) 管理：

```powershell
cd pc
uv run python server.py
```

看到「广播状态：Started」就已经在等手机连接了。

### 3. 手机端连接

**在线版**：手机浏览器打开 **https://haujetzhao.github.io/Bluetooth-Input/** ，点「扫描连接」选中你的电脑即可。

**本地开发**：电脑运行 `npm run dev`，手机打开 `https://<电脑局域网IP>:5173`，首次信任自签证书。

**单文件本地托管**：

以下命令在仓库根目录执行：

```powershell
npm run build
uv run --project pc python serve_web.py
# 手机访问 https://<电脑局域网 IP>:8443
```

换网络导致局域网 IP 变化、证书不匹配时，重签一次：

```bash
openssl req -x509 -newkey rsa:2048 -nodes \
  -keyout certs/key.pem -out certs/cert.pem -days 3650 \
  -subj "/CN=ble-local" \
  -addext "subjectAltName=DNS:localhost,IP:127.0.0.1,IP:<当前局域网IP>"
```

## 手机浏览器要求

- **Android**：Chrome、Edge 等 Chromium 内核浏览器
- **iOS**：需使用 [Bluefy](https://apps.apple.com/cn/app/bluefy-web-ble-browser/id1492828568) 等支持 Web Bluetooth 的浏览器

> 同一个页面只开一个标签页。多个标签页会各自建立一路蓝牙客户端去抢同一台设备，表现为 `GATT Error Unknown` 或刚连就断。

## 目录结构

```text
├── index.html              Vite 入口
├── src/                    Vue 源码
│   ├── App.vue             页面与输入交互
│   ├── styles.css          样式
│   ├── logic/              帧编解码、协议常量、BLE 客户端
│   └── composables/        useBle 响应式封装
├── public/                 PWA 图标
├── certs/                  自签证书
├── serve_web.py            本地 HTTPS 静态服务，托管 dist/
├── protocol.md             协议：UUID、帧格式、消息类型
├── pc/                     电脑端
├── docs/HANDOFF.md         开发交接文档
└── bt_serial_receiver.py   早期 RFCOMM 串口方案，保留备用
```

## 开发

```powershell
npm run dev        # HTTPS 开发服务器，手机可访问
npm test           # 帧编解码单测
npm run build      # 单文件产物 dist/index.html（`public/` 下的 PWA 图标也会一并复制到 dist/）
npm run build:pwa  # PWA 产物，供 GitHub Pages 部署
```

改协议时，`protocol.md`、`pc/server.py`、`src/logic/protocol.js`、`src/logic/frame-codec.js` 必须同步。
