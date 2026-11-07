# Bluetooth Input

通过低功耗蓝牙 (BLE)，用手机给电脑打字。

**无需安装任何手机 App** — 手机浏览器打开网页即可连接，电脑端运行一个小服务即可。

> [!NOTE]
> 打字与剪贴板**不需要在同一网络下**，数据通过 BLE 蓝牙物理通道直传。传文件走局域网 HTTP，手机与电脑需要在同一局域网。

## 功能

- **即时输入** — 手机打字实时出现在电脑光标处，就像用物理键盘一样
- **经典发送** — 输入整段文字后一次性发送
- **剪贴板同步** — 手机与电脑之间双向推送/拉取剪贴板内容
- **局域网传文件** — 蓝牙把入口地址送到手机，点一下打开电脑托管的上传页，多选文件存到电脑上选定的位置（「下载」或「桌面」下的 `手机传输` 文件夹，默认「下载」；首次使用需在浏览器里允许一次「本地网络」权限）
- **自动重连** — 蓝牙断开后后台静默重连，无需手动干预
- **链路自检** — 电脑每 3 秒发一次心跳，网页端 9 秒收不到就判定断链并自动重连

## 使用方法

### 1. 安装依赖

```powershell
cd web
npm install
```

### 2. 电脑端启动服务

需要 Python 3.12+，依赖用 [uv](https://docs.astral.sh/uv/) 管理：

```powershell
cd pc
uv run python main.py
```

看到「广播状态：Started」就已经在等手机连接了。

### 3. 手机端连接

**在线版**：手机浏览器打开 **https://haujetzhao.github.io/Bluetooth-Input/** ，点左上角的连接状态药丸选中你的电脑即可。

**本地开发**：在 `web` 目录运行 `npm run dev`，手机打开 `https://<电脑局域网IP>:5173`，首次信任自签证书。dev server 走的是 `web/certs/` 下的自签证书。

换网络导致局域网 IP 变化、证书不匹配时，在 `web` 目录重签一次：

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
├── web/                    手机端网页（Vue 3 + Vite）
│   ├── index.html          Vite 入口
│   ├── src/                App.vue、styles.css、logic/、composables/
│   ├── public/             PWA 图标
│   ├── certs/              自签证书，dev server 用
│   └── vite.config*.js     开发 / 单文件 / PWA 三套构建
├── pc/                     电脑端，WinRT GATT Server
├── .github/workflows/      GitHub Actions：构建 PWA 并发布到 Pages
├── protocol.md             协议：UUID、帧格式、消息类型
├── AGENTS.md               项目说明与开发约定
└── readme.md
```

## 开发

前端命令都在 `web/` 目录下执行：

```powershell
npm run dev        # HTTPS 开发服务器，手机可访问
npm test           # 帧编解码单测
npm run build      # 单文件产物 dist/index.html，交给任意 HTTPS 托管
npm run build:pwa  # PWA 产物，供 GitHub Pages 部署
```

改协议时，`protocol.md`、`pc/bluetooth_input/server.py`、`web/src/logic/protocol.js`、`web/src/logic/frame-codec.js` 必须同步。

## 发布

在线版由 GitHub Actions 构建：推送到 `main`，或在 Actions 页面手动触发 `Deploy to GitHub Pages`。工作流在 `web/` 目录下依次跑 `npm ci`、`npm test`、`npm run build:pwa`，再把 `web/dist/` 发布出去。

仓库 Settings → Pages 的 Source 必须选 **GitHub Actions**。
