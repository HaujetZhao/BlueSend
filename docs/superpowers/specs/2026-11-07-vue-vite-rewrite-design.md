# 前端 Vue + Vite 重写设计

日期：2026-11-07
分支：`refactor/vue`

## 一、背景与目标

手机端页面目前是 `index.html` + `static/app.js`（约 370 行原生 JS）+ `static/style.css`，连接管理、帧编解码、看门狗、写队列、输入法与剪贴板逻辑混在一个全局脚本里；状态通过直接操作 DOM 同步，新增行为时容易互相牵连。

本次用 Vue 3 + Vite 重写前端，工程组织参考 SubTap：

- **界面与交互保持不变**：不重新设计，重写前后可逐项对照。
- **传输层与界面分离**：BLE 连接、帧编解码、重连与心跳从 UI 中抽出，成为不依赖 Vue 的纯逻辑模块。
- **三种运行形态**：日常开发用 Vite dev server；单文件产物配自签证书本地托管；PWA 产物用于 GitHub Pages。
- **协议不动**：UUID、帧格式、消息类型维持 `protocol.md` 现状。

非目标：

- 不加新功能，不改文案与布局。
- 不改电脑端 `pc/`。
- 本次不接 GitHub Pages 的 Action 工作流，只把构建脚本准备好。（同日收尾后已补上 `.github/workflows/deploy.yml`，发布方式见 `readme.md` 的「发布」一节。）

## 二、构建与运行

| 场景 | 命令 | 配置 | 产物 | 说明 |
|---|---|---|---|---|
| 日常开发 | `npm run dev` | `vite.config.js` | 内存中 | dev server 开 `host: true`，加载 `certs/` 下的自签证书走 HTTPS；手机访问 `https://<电脑局域网 IP>:5173`，HMR 可用 |
| 单文件 | `npm run build` | `vite.config.js` | 单个 `dist/index.html` | Vue + `vite-plugin-singlefile`，JS/CSS 全内联；由 `serve_web.py` 用同一套证书托管 |
| PWA | `npm run build:pwa` | `vite.config.pwa.js` | `dist/` 多文件 | Vue + `vite-plugin-pwa`，产出外链 JS/CSS、manifest、service worker；供 GitHub Pages 部署 |

约定：

- 两套构建配置分开写，不参数化；Vite 构建时默认清空 `dist`，一次只跑一种。
- 两种构建都保持 `base: './'`，部署在子路径下可直接工作。
- 开发、单文件、PWA 三种形态使用同一份 `src/`，协议与 UI 行为完全一致。
- PWA 的 service worker 与 manifest 必须是独立文件，无法内联，因此单文件构建必须是另一套配置。
- `dist/`、`node_modules/` 加入 `.gitignore`。

依赖与版本对齐 SubTap：`vue ^3.4.0`、`vite ^5.0.0`、`@vitejs/plugin-vue ^5.0.0`、`vite-plugin-singlefile ^2.0.0`、`vite-plugin-pwa ^0.20.0`；包管理器用 npm。构建脚本不再引入 `rimraf`，由 Vite 的 `emptyOutDir` 负责清空产物。

## 三、目录结构

```text
Bluetooth-Input/
├── index.html                 Vite 入口，挂载 #app
├── package.json
├── vite.config.js             开发 + 单文件构建（HTTPS dev server、singlefile）
├── vite.config.pwa.js         PWA 构建（manifest、service worker）
├── public/
│   ├── icon-192.png           PWA 图标
│   └── icon-512.png
├── assets/icon.svg            图标源文件，用于重新生成 PNG
├── src/
│   ├── main.js
│   ├── App.vue
│   ├── styles.css
│   ├── logic/
│   │   ├── protocol.js        UUID 与链路参数常量
│   │   ├── frame-codec.js     帧编码与流式解码
│   │   └── ble-client.js      连接、重连、心跳、写队列
│   └── composables/
│       └── useBle.js          BleClient 的 Vue 响应式封装
├── certs/
│   ├── cert.pem               自签证书（从 static/ 移入）
│   └── key.pem
├── serve_web.py               托管 dist/ 的本地 HTTPS 静态服务
├── pc/                        电脑端，不改
└── .trash/pre-vue-2026-11-07/ 旧 index.html、static/app.js、static/style.css
```

## 四、代码结构与职责

### `src/logic/protocol.js`

只放常量，不做逻辑：

- `SERVICE_UUID`、`CHAR_UUID`
- `HEARTBEAT_TIMEOUT_MS = 9000`
- `FALLBACK_WRITE_CHUNK = 180`
- `RECONNECT_INTERVAL_MS = 2000`

### `src/logic/frame-codec.js`

帧格式为 `[4 字节大端长度][UTF-8 JSON]`，与 `pc/frame_codec.py` 对齐。

- `encodeFrame(message)`：序列化为 JSON，前置 4 字节长度，返回 `Uint8Array`。
- `FrameDecoder`：持有内部字节缓冲；`push(chunk)` 返回本次凑满的完整消息数组。不足一帧时返回空数组，剩余字节留在缓冲里。

### `src/logic/ble-client.js`

框架无关的连接管理器，构造时注入回调：

```js
new BleClient({
  onState(state),      // 'disconnected' | 'connecting' | 'connected'
  onEvent(text),       // 链路事件，用于页面事件行与电脑端日志
  onClipboard(text),   // 收到电脑端剪贴板
})
```

职责：

- `requestDevice()`：先弹出设备选择，选中后才拆除旧链路并绑定新设备；用户取消时保留原连接。
- `connect()`：单飞，同一时刻只允许一个在途连接；取 GATT server、Service、Characteristic，开启通知，重置缓冲与写链，启动心跳看门狗。重连是否成功以实际拿到 characteristic 为准。
- 代际校验：重新扫描、断链都会推进代际；在途连接与旧写队列的分片在代际变化后不再生效，避免迟到的失败或写入击穿新链路。
- 写队列：所有写入串到同一条 Promise 链上；单帧按 `characteristic.maxWriteWithResponseSize || 180` 切片，逐片 `writeValueWithResponse`。
- 收包：通知分片进入 `FrameDecoder`，凑满即分发；任何收到消息都刷新心跳超时。
- 心跳看门狗：9 秒没有任何消息判定断链。
- 断链处理：只记一笔；清空 characteristic、接收缓冲、写链；记录存活时长与累计断开次数；按 2 秒间隔重连；重连失败只记第一次和之后每 10 次。
- 断线期间的事件先入待补发队列，重连成功后按序补发 `log` 消息。
- 页面回到前台且当前无连接时主动重连。
- `dispose()`：移除监听、清理定时器。

### `src/composables/useBle.js`

`useBle({ onClipboard })` 返回：

- `status`：`ref`，三态。
- `lastEvent`：`ref`，最近一条链路事件文本。
- `connected`：`computed`，`status === 'connected'`。
- `connect()`、`send(message)`、`note(text)`。
- 内部创建并持有 `BleClient`，在组件卸载时释放。

`note(text)` 的语义与现在一致：写控制台、更新事件行；已连接则发 `log` 消息，未连接则入补发队列。

### `src/App.vue`

页面结构、状态展示与输入交互：

- 顶部状态徽章、扫描/重新连接按钮、即时发送开关。
- 事件行。
- 文本输入区。
- 经典模式的「发送」「清空」按钮组。
- 剪贴板「拉取」「推送」按钮组。
- 中文输入法 `composition` 状态、即时输入、粘贴拦截、快捷键处理。输入区用 `:value` + 单一 `@input` 管理，不依赖 `v-model` 指令与模板监听器的注册顺序。
- 多标签页检测（`BroadcastChannel`）。
- 拉取到的剪贴板文本写回输入框并聚焦，同时尽力写入手机剪贴板（失败只告警，不影响输入框内容）。

组件不再细分。当前页面只有一个卡片，拆成多个子组件只会增加传参噪音；BLE 的复杂度已经由 `logic/` 承担，UI 保持一个组件更容易对照现有行为。

## 五、数据流

```text
用户操作（按钮 / 输入）
        │
        ▼
     App.vue ──send(message)──▶ useBle ──▶ BleClient ──▶ writeValueWithResponse 分片
        ▲                        │
        │ status / lastEvent     │ 通知分片
        └────────────────────────┘
                                 │
                          FrameDecoder 凑帧 → 消息分发
                                 │
                    hb / pong    │    clip
                       刷新看门狗 │     onClipboard(text) → App.vue 写回输入框
```

## 六、行为对齐清单

重写后逐项核对，任何一项与现版本不一致都算缺陷：

1. 状态徽章三态：未连接（红点）、连接中（黄点闪烁）、已连接（绿点）。
2. 连接按钮：未连接时「扫描连接」；连接中禁用；已连接后变「重新连接」。
3. 事件行文本：连接段数、断开原因、上一段存活秒数、重连失败次数、多标签页提示。
4. 断线期间的事件缓存，重连成功后补发到电脑端日志。
5. 即时发送开关默认开启；切换时清空输入框、调整输入框高度与占位文案；经典模式显示发送/清空按钮组。
6. 输入框始终可用，不因连接状态禁用；发送后与拉取剪贴板后保持焦点，避免软键盘收起。
7. 即时模式下：中文输入法组合期间不发送；组合结束发送组合文本；`insertText` 发送文本；`deleteContentBackward` 发送退格；回车发送 `key:enter`；空输入框退格发送 `key:backspace`；粘贴拦截并直接发送全文。
8. 经典模式下：`Ctrl+Enter` 发送，内容追加换行；按钮发送同样追加换行；发送后清空并聚焦。
9. 剪贴板拉取发 `pull`；推送读取手机剪贴板后发 `clip`；未连接、读取被拒、剪贴板为空时给出对应提示。
10. 多标签页检测：新标签页打开时提示只保留一个，并回应其他标签页的探测。
11. 页面回到前台且无连接时主动重连。
12. 所有链路事件写浏览器控制台。

## 七、协议约束

以下约束由现有实现与 `protocol.md` 决定，重写不得改变：

- 单一特征值双向通道，属性 `WRITE | WRITE_WITHOUT_RESPONSE | NOTIFY`。
- 手机 → 电脑只用 `writeValueWithResponse`；ATT 层保证分片顺序。
- 电脑 → 手机按协商后的通知大小分片；接收端按字节流累积。
- 心跳每 3 秒一次；网页端 9 秒收不到任何消息即判死。
- 消息类型：`text`、`key`、`clip`、`pull`、`ping`、`log`（手机 → 电脑）；`hb`、`pong`、`clip`（电脑 → 手机）。

## 八、PWA 配置

`vite.config.pwa.js`：

- `registerType: 'prompt'`：新版只在后台预缓存，不做 `skipWaiting` 强制刷新。
- manifest：
  - `name`: 「手机 ↔ 电脑 蓝牙通道」
  - `short_name`: 「蓝牙输入」
  - `display`: `standalone`
  - `start_url`: `./`
  - `theme_color` / `background_color`: `#0f0f13`
  - 图标：`icon-192.png`、`icon-512.png`，`purpose: 'any maskable'`
- Workbox：预缓存 `js/css/html/svg/png/json`；本应用无外部资源，不配置运行时缓存。

图标从 `assets/icon.svg` 用本机 ImageMagick 生成，源文件保留以便重做。

## 九、测试与验证

- `src/logic/frame-codec.test.js` 使用 Node 内置 `node:test`，不增加测试依赖。用例：
  - 单帧编解码往返；
  - 一帧拆成多次 `push`；
  - 一次 `push` 含多帧；
  - 含中文的 UTF-8 负载；
  - 空对象；
  - 与 `pc/frame_codec.py` 对齐的固定字节夹具；
  - 长度字段跨多个字节（载荷 300 字节）；
  - 分片边界落在 UTF-8 多字节字符中间。
- `npm test` 执行 `node --test src/logic/*.test.js`，共 8 个用例；要求 Node 22+。
- 构建验证：`npm run build`、`npm run build:pwa` 均成功且产物符合预期；单文件构建的 `dist/index.html` 会连同 `public/` 下的两张 PWA 图标一起复制，但 JS/CSS 已全部内联。
- 开发验证：`npm run dev` 启动 HTTPS 服务，局域网内手机可打开页面。
- 蓝牙真机验收（连接、长文本、即时输入、剪贴板双向）由用户本人完成。

## 十、文档同步

- `readme.md`：更新目录结构、开发与构建命令、单文件托管方式。
- `docs/HANDOFF.md`：更新代码地图、启动方式、协议同步位置。
- 协议改动时的同步位置改为：`protocol.md`、`pc/server.py`、`src/logic/protocol.js`、`src/logic/frame-codec.js`。

## 十一、迁移步骤

1. 新建 `.trash/pre-vue-2026-11-07/`，把旧 `index.html`、`static/app.js`、`static/style.css` 移入。
2. 把 `static/cert.pem`、`static/key.pem` 移到 `certs/`。
3. 新建 `package.json`、`vite.config.js`、`vite.config.pwa.js`、`index.html`、`src/`、`public/`、`assets/icon.svg`。
4. 重写 `serve_web.py`：静态根目录改为 `dist/`，证书路径改为 `certs/`。
5. 更新 `.gitignore`、`readme.md`、`docs/HANDOFF.md`。
6. 跑测试与三种构建，提交到 `refactor/vue`。

## 十二、风险与取舍

- **自签证书绑定局域网 IP**：证书 SAN 当前为 `localhost`、`127.0.0.1`、`10.117.208.175`。换网络导致 IP 变化时，手机访问 dev server 或 `serve_web.py` 会证书不匹配，需要重签；重签命令写进 readme。
- **Vite dev server 用 HTTPS**：手机信任证书后 HMR 正常；证书不被信任时页面无法打开，这属于 Web Bluetooth 的硬性要求，无法绕过。
- **PWA 离线缓存**：service worker 会预缓存旧版本；用 `prompt` 模式避免自动刷新，冷启动后生效。
- **PWA 内 Web Bluetooth**：Android Chrome 安装后的 PWA 仍可使用 Web Bluetooth；iOS 仍只支持 Bluefy 一类浏览器，维持现状。
- **单文件构建体积**：内联后的 HTML 略大于多文件总和，但本应用体量很小，换取分发与本地托管的最简路径。
