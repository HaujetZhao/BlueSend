# BlueSend

通过低功耗蓝牙（BLE），把手机变成电脑的无线输入、剪贴板与文件通道。

**手机不用装 App**：用浏览器打开网页即可连接，电脑端运行一个绿色小程序。

> [!NOTE]
> 打字与剪贴板**不需要在同一网络下**，数据通过蓝牙直传。传文件走局域网，手机与电脑需要连同一个 Wi-Fi。

## 功能

- **即时输入**：手机打字实时出现在电脑光标处，就像用物理键盘一样
- **经典发送**：输入整段文字后一次性发送
- **剪贴板同步**：手机与电脑之间双向推送、拉取剪贴板内容
- **局域网传文件**：蓝牙把入口地址送到手机，点一下打开电脑托管的上传页，多选文件存到电脑上选定的位置
- **自动重连**：蓝牙断开后后台静默重连，无需手动干预
- **链路自检**：电脑每 3 秒发一次心跳，网页 9 秒收不到就判定断链并自动重连
- **托盘常驻**：电脑端启动后收进系统托盘，不占任务栏

## 安装使用

### 1. 运行电脑端

要求：Windows 10／11，蓝牙适配器支持 BLE 外设角色（绝大多数笔记本内置蓝牙都支持）。

1. 打开 [Releases](https://github.com/HaujetZhao/BlueSend/releases/latest)，下载最新的 `BlueSend-<版本>-win64.zip`。
2. 解压后双击 `BlueSend.exe`，程序会自动隐藏到系统托盘。托盘图标悬停可看到版本号；右键菜单可显示／隐藏窗口、复制上传地址、重启或退出，双击图标也能切换窗口。

不需要安装 Python，删除程序目录即卸载。

### 2. 手机连接

1. 手机打开 **https://haujetzhao.github.io/BlueSend/**。
2. 打开蓝牙，点左上角的连接状态药丸，在列表里选中你的电脑。
3. 底部状态栏显示「已连接（第 N 次）」即成功。之后打字、推剪贴板都会显示在这一行。

浏览器要求：

- **Android**：Chrome、Edge 等 Chromium 内核浏览器
- **iOS**：用 [Bluefy](https://apps.apple.com/cn/app/bluefy-web-ble-browser/id1492828568) 等支持 Web Bluetooth 的浏览器打开上面的地址

> [!IMPORTANT]
> 同一个页面只开一个标签页。多个标签页会各自建立一路蓝牙客户端去抢同一台设备，表现为连不上或刚连就断。电脑端也只能运行一个实例，重复启动时新进程会提示后直接退出。

### 3. 日常使用

- **打字**：把手机当键盘用，「即时输入」边打边出现在电脑上；「经典发送」适合先写完一段再一次性发。
- **剪贴板**：在手机与电脑之间互相推送、拉取。电脑剪贴板被其他程序占用时会提示而不是清空手机剪贴板。
- **传文件**：手机与电脑连同一个局域网，点「发送文件」。首次会请求「本地网络」权限，允许后才会探测电脑。文件保存到「下载」或「桌面」下的 `手机传输` 文件夹（上传页可切换，默认「下载」）。
- **离开再回来**：信号断开后网页会在后台自动重连，不用手动操作。

### 常见问题

- **手机列表里找不到电脑**：确认电脑端在运行（程序目录 `logs\` 下最新日志里有「广播状态：2」）、手机蓝牙已打开、电脑端没有重复运行。
- **电脑端重启后手机连不上**：Chrome 会缓存旧的蓝牙服务句柄，网页会一直后台重试。刷新手机页面，或点状态药丸重新扫描即可恢复。
- **传文件页打不开**：确认手机与电脑在同一局域网、Windows 防火墙放行了程序；蓝牙功能与传文件互不影响。
- **想在别的电脑上用**：整个程序目录复制过去即可，配置在 `core\config.toml`，日志在 `logs\`。

## 开发

### 环境

- Python 3.12+，依赖用 [uv](https://docs.astral.sh/uv/) 管理
- Node.js 22+

### 跑源码

```powershell
cd server
uv run python main.py
```

看到「广播状态：2（Started）」就是在等手机连接。源码运行时控制台窗口保持可见，方便看日志。

手机端有两种访问方式：

- **在线版**：`https://haujetzhao.github.io/BlueSend/`（推送 `main` 后由 GitHub Actions 构建发布）
- **本地开发**：在 `web\` 下运行 `npm run dev`，手机打开 `https://<电脑局域网IP>:5173`，首次信任自签证书

换网络导致局域网 IP 变化、证书不匹配时，在 `web` 目录重签一次：

```bash
openssl req -x509 -newkey rsa:2048 -nodes \
  -keyout certs/key.pem -out certs/cert.pem -days 3650 \
  -subj "/CN=ble-local" \
  -addext "subjectAltName=DNS:localhost,IP:127.0.0.1,IP:<当前局域网IP>"
```

### 前端命令

都在 `web\` 目录下执行：

```powershell
npm install
npm run dev        # HTTPS 开发服务器，手机可访问
npm test           # 帧编解码单测
npm run build      # 单文件产物 dist/index.html
npm run build:pwa  # PWA 产物，供 GitHub Pages 部署
```

### 电脑端单测

```powershell
cd server
uv run pytest
```

### 目录结构

```text
├── web/                    手机端网页（Vue 3 + Vite）
│   ├── src/                App.vue、styles.css、logic/、composables/
│   ├── public/             PWA 图标
│   ├── certs/              自签证书，dev server 用
│   └── vite.config*.js     开发／单文件／PWA 三套构建
├── server/                 电脑端，WinRT GATT Server
│   ├── main.py             入口：日志、单实例锁、启动与重启
│   ├── BlueSend.spec       PyInstaller 打包配置
│   ├── core/               协议、编解码、剪贴板、上屏、上传服务、托盘
│   └── tests/              pytest
├── .github/workflows/      GitHub Actions：构建 PWA 并发布到 Pages
├── protocol.md             协议：UUID、帧格式、消息类型
├── AGENTS.md               项目说明与开发约定
└── readme.md
```

### 打包 exe

```powershell
cd server
uv run pyinstaller BlueSend.spec
```

产物在 `server\dist\BlueSend\`，整个目录压缩后即可分发，目标机器不需要装 Python。`core\` 以源文件形式随包发布，改配置或代码后重启 exe 即生效，不用重新打包。

### 发布

版本号的唯一来源是 [server/pyproject.toml](server/pyproject.toml)；网页的 [web/package.json](web/package.json) 保持同一个版本。打包时版本会写进 exe，启动横幅和托盘提示显示的就是它。

1. 改版本号：`server/pyproject.toml` 与 `web/package.json` 同步。
2. 提交并打 tag：`git tag v<版本>`，推送 `main` 与 tag。
3. 推 `main` 会触发 GitHub Actions 构建并发布手机端网页（工作流在 `web/` 下依次跑 `npm ci`、`npm test`、`npm run build:pwa`）。仓库 Settings → Pages 的 Source 必须选 **GitHub Actions**。
4. 打包电脑端，把 `server\dist\BlueSend\` 压缩成 `BlueSend-<版本>-win64.zip`，作为附件上传到对应的 GitHub Release。

改协议时，`protocol.md`、`server/core/server.py`、`server/core/protocol.py`、`web/src/logic/protocol.js`、`web/src/logic/frame-codec.js` 必须同步。
