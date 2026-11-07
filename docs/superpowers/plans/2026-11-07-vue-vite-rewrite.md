# 前端 Vue + Vite 重写实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把手机端页面从原生 JS 重写为 Vue 3 + Vite 工程，界面与行为保持不变，支持开发、单文件、PWA 三种运行形态。

**Architecture:** BLE 传输逻辑放进不依赖 Vue 的 `src/logic/`：`frame-codec.js` 负责帧编解码，`ble-client.js` 负责连接、重连、心跳与写队列；`src/composables/useBle.js` 做响应式封装；`src/App.vue` 只负责界面与输入交互。两套 Vite 配置分别产出单文件与 PWA 产物。

**Tech Stack:** Vue 3、Vite 5、`@vitejs/plugin-vue`、`vite-plugin-singlefile`、`vite-plugin-pwa`、Node 内置 `node:test`。

---

## 文件结构

| 文件 | 职责 |
|---|---|
| `index.html` | Vite 入口，挂载 `#app` |
| `package.json` | 依赖与 `dev` / `build` / `build:pwa` / `test` 脚本 |
| `vite.config.js` | 开发服务器（HTTPS + `host`）与单文件构建 |
| `vite.config.pwa.js` | PWA 构建（manifest、service worker） |
| `src/main.js` | 创建并挂载 Vue 应用 |
| `src/App.vue` | 页面结构与全部输入交互 |
| `src/styles.css` | 沿用现有视觉样式 |
| `src/logic/protocol.js` | UUID、心跳、分片、重连常量 |
| `src/logic/frame-codec.js` | `encodeFrame`、`FrameDecoder` |
| `src/logic/frame-codec.test.js` | 帧编解码单测 |
| `src/logic/ble-client.js` | BLE 连接生命周期 |
| `src/composables/useBle.js` | BLE 的 Vue 响应式封装 |
| `public/icon-192.png`、`public/icon-512.png` | PWA 图标 |
| `assets/icon.svg` | 图标源文件 |
| `certs/cert.pem`、`certs/key.pem` | 自签证书 |
| `serve_web.py` | 托管 `dist/` 的本地 HTTPS 服务 |

---

### Task 1: 迁移旧前端与证书

**Files:**
- Move: `index.html` → `.trash/pre-vue-2026-11-07/index.html`
- Move: `static/app.js` → `.trash/pre-vue-2026-11-07/app.js`
- Move: `static/style.css` → `.trash/pre-vue-2026-11-07/style.css`
- Move: `static/cert.pem` → `certs/cert.pem`
- Move: `static/key.pem` → `certs/key.pem`
- Modify: `.gitignore`

- [ ] **Step 1: 建目录并移动旧文件**

```bash
mkdir -p .trash/pre-vue-2026-11-07 certs
mv index.html static/app.js static/style.css .trash/pre-vue-2026-11-07/
mv static/cert.pem static/key.pem certs/
```

- [ ] **Step 2: 确认移动结果**

Run:

```bash
ls -la certs .trash/pre-vue-2026-11-07
ls static
```

Expected：`certs/` 有 `cert.pem`、`key.pem`；`.trash/pre-vue-2026-11-07/` 有三个旧文件；`static/` 为空。

- [ ] **Step 3: 更新 `.gitignore`**

把 `.gitignore` 改为：

```text
__pycache__/
.venv/
.pytest_cache/
.trash/
pc/logs/
node_modules/
dist/
.idea/
.DS_Store
```

- [ ] **Step 4: 提交**

```bash
git add -A
git commit -m "chore: 旧前端移入 .trash，证书移入 certs/"
```

---

### Task 2: 工程骨架与依赖

**Files:**
- Create: `package.json`
- Create: `vite.config.js`
- Create: `vite.config.pwa.js`
- Create: `index.html`
- Create: `src/main.js`

- [ ] **Step 1: 创建 `package.json`**

```json
{
  "name": "bluetooth-input",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite --host",
    "build": "rimraf dist && vite build",
    "build:pwa": "rimraf dist && vite build --config vite.config.pwa.js",
    "preview": "vite preview",
    "test": "node --test src/logic"
  },
  "dependencies": {
    "vue": "^3.4.0"
  },
  "devDependencies": {
    "@vitejs/plugin-vue": "^5.0.0",
    "rimraf": "^6.1.3",
    "vite": "^5.0.0",
    "vite-plugin-pwa": "^0.20.0",
    "vite-plugin-singlefile": "^2.0.0"
  }
}
```

- [ ] **Step 2: 创建 `vite.config.js`**

```js
import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';
import { viteSingleFile } from 'vite-plugin-singlefile';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

// 开发服务器与单文件构建共用一份配置。
// HTTPS 是 Web Bluetooth 的硬性要求：手机必须通过安全上下文打开页面。
const root = fileURLToPath(new URL('.', import.meta.url));
const https = {
  key: fs.readFileSync(path.join(root, 'certs/key.pem')),
  cert: fs.readFileSync(path.join(root, 'certs/cert.pem')),
};

export default defineConfig({
  plugins: [vue(), viteSingleFile()],
  base: './',
  server: {
    host: true,
    https,
  },
});
```

- [ ] **Step 3: 创建 `vite.config.pwa.js`**

```js
import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';
import { VitePWA } from 'vite-plugin-pwa';

// PWA 构建配置：用于 GitHub Pages 在线版。
// 与 vite.config.js（单文件构建，给本地 HTTPS 托管）分开，
// 因为 service worker 和 manifest 必须是独立外链文件，无法内联进单 HTML。
export default defineConfig({
  plugins: [
    vue(),
    VitePWA({
      // prompt 而非 autoUpdate：新版只在后台预缓存，不强制刷新页面。
      registerType: 'prompt',
      manifest: {
        name: '手机 ↔ 电脑 蓝牙通道',
        short_name: '蓝牙输入',
        description: '通过 BLE 用手机给电脑打字、同步剪贴板。',
        theme_color: '#0f0f13',
        background_color: '#0f0f13',
        display: 'standalone',
        start_url: './',
        icons: [
          { src: 'icon-192.png', sizes: '192x192', type: 'image/png', purpose: 'any maskable' },
          { src: 'icon-512.png', sizes: '512x512', type: 'image/png', purpose: 'any maskable' },
        ],
      },
      workbox: {
        globPatterns: ['**/*.{js,css,html,svg,png,json}'],
      },
    }),
  ],
  base: './',
});
```

- [ ] **Step 4: 创建 `index.html`**

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="theme-color" content="#0f0f13">
  <link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' rx='7' fill='%230f0f13'/%3E%3Cpath d='M16 6l6 4.8-8 5.2 8 5.2-6 4.8M16 6v20' fill='none' stroke='%236366f1' stroke-width='2.2' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E">
  <title>手机 ↔ 电脑 蓝牙通道</title>
</head>
<body>
  <div id="app"></div>
  <script type="module" src="/src/main.js"></script>
</body>
</html>
```

- [ ] **Step 5: 创建 `src/main.js`**

```js
import { createApp } from 'vue';
import App from './App.vue';
import './styles.css';

createApp(App).mount('#app');
```

- [ ] **Step 6: 安装依赖**

Run:

```bash
npm install
```

Expected：生成 `node_modules/` 与 `package-lock.json`，无报错。

- [ ] **Step 7: 提交**

```bash
git add package.json package-lock.json vite.config.js vite.config.pwa.js index.html src/main.js .gitignore
git commit -m "build: 搭建 Vue + Vite 工程骨架"
```

---

### Task 3: 帧编解码（TDD）

**Files:**
- Create: `src/logic/frame-codec.test.js`
- Create: `src/logic/frame-codec.js`

- [ ] **Step 1: 写失败测试**

创建 `src/logic/frame-codec.test.js`：

```js
import test from 'node:test';
import assert from 'node:assert/strict';
import { encodeFrame, FrameDecoder } from './frame-codec.js';

test('单帧编解码往返', () => {
  const frame = encodeFrame({ t: 'text', v: '你好' });
  assert.deepEqual(new FrameDecoder().push(frame), [{ t: 'text', v: '你好' }]);
});

test('一帧分多次推送', () => {
  const frame = encodeFrame({ t: 'clip', v: '分片' });
  const decoder = new FrameDecoder();
  assert.deepEqual(decoder.push(frame.subarray(0, 3)), []);
  assert.deepEqual(decoder.push(frame.subarray(3, 6)), []);
  assert.deepEqual(decoder.push(frame.subarray(6)), [{ t: 'clip', v: '分片' }]);
});

test('一次推送含多帧', () => {
  const first = encodeFrame({ t: 'hb' });
  const second = encodeFrame({ t: 'pong' });
  const merged = new Uint8Array(first.length + second.length);
  merged.set(first);
  merged.set(second, first.length);
  assert.deepEqual(new FrameDecoder().push(merged), [{ t: 'hb' }, { t: 'pong' }]);
});

test('中文按 UTF-8 字节计长度', () => {
  const payload = { t: 'text', v: '中文🙂' };
  const frame = encodeFrame(payload);
  assert.equal(frame.length, 4 + new TextEncoder().encode(JSON.stringify(payload)).length);
  assert.deepEqual(new FrameDecoder().push(frame), [payload]);
});

test('空对象', () => {
  assert.deepEqual(new FrameDecoder().push(encodeFrame({})), [{}]);
});
```

- [ ] **Step 2: 运行测试，确认失败**

Run:

```bash
npm test
```

Expected：FAIL，报错指出找不到 `./frame-codec.js` 或 `encodeFrame` 未定义。

- [ ] **Step 3: 写最小实现**

创建 `src/logic/frame-codec.js`：

```js
// 帧格式：[4 字节大端长度][UTF-8 JSON]，与 pc/frame_codec.py 对齐。
export function encodeFrame(message) {
  const body = new TextEncoder().encode(JSON.stringify(message));
  const frame = new Uint8Array(4 + body.length);
  new DataView(frame.buffer).setUint32(0, body.length, false);
  frame.set(body, 4);
  return frame;
}

export class FrameDecoder {
  #buffer = new Uint8Array(0);

  push(chunk) {
    const merged = new Uint8Array(this.#buffer.length + chunk.length);
    merged.set(this.#buffer);
    merged.set(chunk, this.#buffer.length);
    this.#buffer = merged;

    const messages = [];
    for (;;) {
      if (this.#buffer.length < 4) break;
      const length = new DataView(
        this.#buffer.buffer,
        this.#buffer.byteOffset,
        4,
      ).getUint32(0, false);
      if (this.#buffer.length < 4 + length) break;
      const body = new TextDecoder().decode(this.#buffer.subarray(4, 4 + length));
      this.#buffer = this.#buffer.slice(4 + length);
      messages.push(JSON.parse(body));
    }
    return messages;
  }

  reset() {
    this.#buffer = new Uint8Array(0);
  }
}
```

- [ ] **Step 4: 运行测试，确认通过**

Run:

```bash
npm test
```

Expected：5 个测试全部 PASS。

- [ ] **Step 5: 提交**

```bash
git add src/logic/frame-codec.js src/logic/frame-codec.test.js
git commit -m "feat: 帧编解码与流式解码器"
```

---

### Task 4: 协议常量与 BLE 客户端

**Files:**
- Create: `src/logic/protocol.js`
- Create: `src/logic/ble-client.js`

- [ ] **Step 1: 创建 `src/logic/protocol.js`**

```js
export const SERVICE_UUID = '7d9f0001-3c4e-4b6a-9f2e-1a2b3c4d5e6f';
export const CHAR_UUID = '7d9f0002-3c4e-4b6a-9f2e-1a2b3c4d5e6f';

// 电脑每 3 秒一次心跳，三个周期没动静就判定链路已死。
export const HEARTBEAT_TIMEOUT_MS = 9000;
// 拿不到协商后的写入上限时使用，覆盖 4.2 默认 MTU。
export const FALLBACK_WRITE_CHUNK = 180;
export const RECONNECT_INTERVAL_MS = 2000;
```

- [ ] **Step 2: 创建 `src/logic/ble-client.js`**

```js
import {
  SERVICE_UUID,
  CHAR_UUID,
  HEARTBEAT_TIMEOUT_MS,
  FALLBACK_WRITE_CHUNK,
  RECONNECT_INTERVAL_MS,
} from './protocol.js';
import { encodeFrame, FrameDecoder } from './frame-codec.js';

export class BleClient {
  #onState;
  #onEvent;
  #onClipboard;

  #device = null;
  #characteristic = null;
  #decoder = new FrameDecoder();
  #writeChain = Promise.resolve();
  #heartbeatTimer = null;
  #reconnectTimer = null;
  #connectedAt = 0;
  #dropCount = 0;
  #reconnectFailures = 0;
  #pendingLogs = [];
  #disposed = false;

  constructor({ onState, onEvent, onClipboard }) {
    this.#onState = onState;
    this.#onEvent = onEvent;
    this.#onClipboard = onClipboard;
    document.addEventListener('visibilitychange', this.#onVisibilityChange);
  }

  get connected() {
    return this.#characteristic !== null;
  }

  note(text) {
    this.#note(text);
  }

  async requestDevice() {
    if (!navigator.bluetooth) {
      alert('浏览器不支持 Web Bluetooth，或页面不在 HTTPS 下打开。');
      return;
    }
    this.#stopReconnect();
    this.#device = null;
    this.#onState('connecting');
    try {
      this.#device = await navigator.bluetooth.requestDevice({
        filters: [{ services: [SERVICE_UUID] }],
        optionalServices: [SERVICE_UUID],
      });
      this.#device.addEventListener('gattserverdisconnected', () =>
        this.#handleDrop('物理断开'),
      );
      await this.connect();
    } catch (err) {
      console.warn('选择设备失败', err);
      this.#onState('disconnected');
    }
  }

  async connect() {
    try {
      this.#onState('connecting');
      const server = await this.#device.gatt.connect();
      const service = await server.getPrimaryService(SERVICE_UUID);
      this.#characteristic = await service.getCharacteristic(CHAR_UUID);
      await this.#characteristic.startNotifications();
      this.#characteristic.addEventListener(
        'characteristicvaluechanged',
        this.#onNotify,
      );
      this.#decoder.reset();
      this.#writeChain = Promise.resolve();
      this.#noteAlive();
      this.#stopReconnect();
      this.#connectedAt = Date.now();
      this.#note(`已连接（第 ${this.#dropCount + 1} 段）`);
      this.#flushPendingLogs();
      this.#onState('connected');
    } catch (err) {
      console.warn('连接失败', err);
      this.#characteristic = null;
      this.#onState('disconnected');
      throw err;
    }
  }

  send(message) {
    if (!this.#characteristic) return false;
    const frame = encodeFrame(message);
    this.#writeChain = this.#writeChain
      .then(() => this.#writeFrame(frame))
      .catch((err) => {
        console.error('发送失败', message.t, err);
        this.#handleDrop('写入失败：' + err.message);
      });
    return true;
  }

  dispose() {
    this.#disposed = true;
    document.removeEventListener('visibilitychange', this.#onVisibilityChange);
    this.#stopReconnect();
    clearTimeout(this.#heartbeatTimer);
    this.#device?.gatt?.disconnect();
    this.#device = null;
    this.#characteristic = null;
  }

  #note(text) {
    console.info(text);
    this.#onEvent(text);
    if (this.#characteristic) {
      this.send({ t: 'log', v: text });
    } else {
      this.#pendingLogs.push(text);
    }
  }

  #flushPendingLogs() {
    for (const text of this.#pendingLogs.splice(0)) {
      this.send({ t: 'log', v: text });
    }
  }

  async #writeFrame(frame) {
    const size = this.#characteristic.maxWriteWithResponseSize || FALLBACK_WRITE_CHUNK;
    for (let i = 0; i < frame.length; i += size) {
      // 有响应写由 ATT 保证先后顺序，这正是无响应写分片乱序的根源。
      await this.#characteristic.writeValueWithResponse(frame.subarray(i, i + size));
    }
  }

  #onNotify = (event) => {
    const view = event.target.value;
    const chunk = new Uint8Array(view.buffer, view.byteOffset, view.byteLength);
    for (const message of this.#decoder.push(chunk)) {
      this.#dispatch(message);
    }
  };

  #dispatch(message) {
    console.debug('收到', message.t);
    this.#noteAlive();
    switch (message.t) {
      case 'hb':
      case 'pong':
        break;
      case 'clip':
        this.#onClipboard(message.v);
        break;
      default:
        console.warn('未知消息', message);
    }
  }

  #noteAlive() {
    clearTimeout(this.#heartbeatTimer);
    this.#heartbeatTimer = setTimeout(
      () => this.#handleDrop('心跳超时'),
      HEARTBEAT_TIMEOUT_MS,
    );
  }

  #handleDrop = (reason) => {
    if (this.#disposed || !this.#characteristic) return;
    const lasted = this.#connectedAt
      ? ((Date.now() - this.#connectedAt) / 1000).toFixed(1)
      : '未知';
    this.#connectedAt = 0;
    this.#dropCount += 1;
    clearTimeout(this.#heartbeatTimer);
    this.#characteristic = null;
    this.#decoder.reset();
    this.#writeChain = Promise.resolve();
    this.#note(`第 ${this.#dropCount} 次断开：${reason}，上一段连接存活 ${lasted} 秒`);
    this.#onState('disconnected');
    this.#scheduleReconnect();
  };

  #scheduleReconnect() {
    if (!this.#device || this.#reconnectTimer) return;
    this.#reconnectTimer = setInterval(() => {
      if (!this.#device) {
        this.#stopReconnect();
        return;
      }
      this.connect()
        .then(() => {
          this.#reconnectFailures = 0;
        })
        .catch((err) => {
          this.#reconnectFailures += 1;
          // 每 2 秒试一次，全记会刷屏，只记第一次和之后每 10 次。
          if (this.#reconnectFailures === 1 || this.#reconnectFailures % 10 === 0) {
            this.#note(`重连失败 ${this.#reconnectFailures} 次：${err.message}`);
          }
        });
    }, RECONNECT_INTERVAL_MS);
  }

  #stopReconnect() {
    clearInterval(this.#reconnectTimer);
    this.#reconnectTimer = null;
  }

  #onVisibilityChange = () => {
    // 页面回到前台时蓝牙可能已经被系统掐掉，主动检查一次。
    if (document.visibilityState === 'visible' && this.#device && !this.#characteristic) {
      this.connect().catch(() => {});
    }
  };
}
```

- [ ] **Step 3: 语法检查**

Run:

```bash
node --check src/logic/protocol.js
node --check src/logic/ble-client.js
```

Expected：两条命令无输出、退出码 0。

- [ ] **Step 4: 提交**

```bash
git add src/logic/protocol.js src/logic/ble-client.js
git commit -m "feat: BLE 连接管理与协议常量"
```

---

### Task 5: useBle 响应式封装

**Files:**
- Create: `src/composables/useBle.js`

- [ ] **Step 1: 创建 `src/composables/useBle.js`**

```js
import { ref, computed, onUnmounted } from 'vue';
import { BleClient } from '../logic/ble-client.js';

export function useBle({ onClipboard }) {
  const status = ref('disconnected');
  const lastEvent = ref('尚未连接');

  const connected = computed(() => status.value === 'connected');

  const client = new BleClient({
    onState: (state) => {
      status.value = state;
    },
    onEvent: (text) => {
      lastEvent.value = text;
    },
    onClipboard,
  });

  onUnmounted(() => client.dispose());

  return {
    status,
    lastEvent,
    connected,
    connect: () => client.requestDevice(),
    send: (message) => client.send(message),
    note: (text) => client.note(text),
  };
}
```

- [ ] **Step 2: 语法检查**

Run:

```bash
node --check src/composables/useBle.js
```

Expected：无输出、退出码 0。

- [ ] **Step 3: 提交**

```bash
git add src/composables/useBle.js
git commit -m "feat: BLE 的 Vue 响应式封装"
```

---

### Task 6: 页面与样式

**Files:**
- Create: `src/App.vue`
- Create: `src/styles.css`

- [ ] **Step 1: 创建 `src/App.vue`**

```vue
<script setup>
import { computed, onUnmounted, ref, watch } from 'vue';
import { useBle } from './composables/useBle.js';

const instantMode = ref(true);
const text = ref('');
const inputEl = ref(null);
const composing = ref(false);
const hasEverConnected = ref(false);
const hasTriedConnect = ref(false);

const {
  status,
  lastEvent,
  connected,
  connect: connectBle,
  send,
  note,
} = useBle({
  onClipboard: applyPulledClipboard,
});

const statusLabel = computed(
  () => ({ disconnected: '未连接', connecting: '连接中', connected: '已连接' })[status.value],
);
const connectLabel = computed(() =>
  connected.value || hasEverConnected.value ? '重新连接' : '扫描连接',
);
const placeholder = computed(() => {
  if (status.value === 'connecting') return '正在重新连接，请稍候…';
  if (status.value === 'connected') {
    return instantMode.value
      ? '已启用即时输入，打字实时发到电脑…'
      : '输入完毕后，点击发送按钮投递…';
  }
  return hasTriedConnect.value
    ? '蓝牙已断开，正在后台重连，可以继续在此处打字…'
    : '连接蓝牙后可开始输入...';
});

watch(status, (state) => {
  if (state !== 'connected') return;
  hasEverConnected.value = true;
  focusInput();
});

function connect() {
  hasTriedConnect.value = true;
  connectBle();
}

function focusInput() {
  inputEl.value?.focus();
}

function toggleInstant() {
  text.value = '';
  focusInput();
}

function sendText() {
  if (!text.value.trim()) return;
  send({ t: 'text', v: text.value + '\n' });
  text.value = '';
  focusInput();
}

function clearInput() {
  text.value = '';
  focusInput();
}

function onCompositionEnd(event) {
  composing.value = false;
  if (!instantMode.value) return;
  if (event.data) send({ t: 'text', v: event.data });
  text.value = '';
  focusInput();
}

function onInput(event) {
  if (!instantMode.value || composing.value) return;
  if (event.inputType === 'insertText') {
    if (event.data) send({ t: 'text', v: event.data });
    text.value = '';
  } else if (event.inputType === 'deleteContentBackward') {
    send({ t: 'key', v: 'backspace' });
    text.value = '';
  }
}

function onPaste(event) {
  if (!instantMode.value) return;
  event.preventDefault();
  const pasted = event.clipboardData.getData('text');
  if (pasted) send({ t: 'text', v: pasted });
  text.value = '';
  focusInput();
}

function onKeydown(event) {
  if (!instantMode.value) {
    if (event.ctrlKey && event.key === 'Enter') {
      event.preventDefault();
      sendText();
    }
    return;
  }
  if (event.key === 'Enter') {
    event.preventDefault();
    send({ t: 'key', v: 'enter' });
    text.value = '';
    focusInput();
  } else if (event.key === 'Backspace' && text.value === '') {
    event.preventDefault();
    send({ t: 'key', v: 'backspace' });
  }
}

function pullClipboard() {
  if (!send({ t: 'pull' })) alert('蓝牙未连接！');
}

async function pushClipboard() {
  if (!connected.value) {
    alert('蓝牙未连接！');
    return;
  }
  let content;
  try {
    content = await navigator.clipboard.readText();
  } catch (err) {
    alert('读取手机剪贴板被浏览器拒绝：' + err.message);
    return;
  }
  if (!content) {
    alert('手机剪贴板为空！');
    return;
  }
  send({ t: 'clip', v: content });
}

function applyPulledClipboard(content) {
  text.value = content;
  focusInput();
  // 浏览器权限限制下写入可能失败；内容已经显示在输入框里，不影响使用。
  navigator.clipboard.writeText(content).catch((err) => {
    console.warn('写入手机剪贴板失败', err);
  });
}

// 同一个页面开多个标签页时，每个标签页都是一路独立的 Web Bluetooth 客户端，
// 会互相抢同一台设备。开页时就探测并提醒。
const tabChannel = new BroadcastChannel('ble-tab');
tabChannel.onmessage = (event) => {
  if (event.data === 'ping') {
    tabChannel.postMessage('here');
  } else {
    note('检测到另一个标签页也开着本页面，请只保留一个再连接');
  }
};
tabChannel.postMessage('ping');

onUnmounted(() => tabChannel.close());
</script>

<template>
  <div class="card">
    <div class="top-bar">
      <div class="left-controls">
        <span class="status-badge" :class="status">{{ statusLabel }}</span>
        <button
          class="btn-connect"
          :disabled="status === 'connecting'"
          @click="connect"
        >
          {{ connectLabel }}
        </button>
      </div>

      <div class="switch-container">
        <span>即时发送</span>
        <label class="switch">
          <input v-model="instantMode" type="checkbox" @change="toggleInstant">
          <span class="slider"></span>
        </label>
      </div>
    </div>

    <div class="event-log">{{ lastEvent }}</div>

    <textarea
      ref="inputEl"
      v-model="text"
      :style="{ height: instantMode ? '80px' : '120px' }"
      :placeholder="placeholder"
      @compositionstart="composing = true"
      @compositionend="onCompositionEnd"
      @input="onInput"
      @paste="onPaste"
      @keydown="onKeydown"
    ></textarea>

    <div v-if="!instantMode" class="button-group">
      <button class="btn btn-send" :disabled="!connected" @click="sendText">
        发送 (Ctrl+Enter)
      </button>
      <button class="btn btn-clear" @click="clearInput">清空</button>
    </div>

    <div class="clipboard-group">
      <button class="btn btn-pull" @click="pullClipboard">拉取剪贴板</button>
      <button class="btn btn-push" @click="pushClipboard">推送剪贴板</button>
    </div>
  </div>
</template>
```

- [ ] **Step 2: 创建 `src/styles.css`**

```css
:root {
  --bg-color: #0f0f13;
  --card-bg: rgba(25, 25, 35, 0.75);
  --card-border: rgba(255, 255, 255, 0.08);
  --text-color: #f3f4f6;
  --text-muted: #9ca3af;
  --primary-color: #6366f1;
  --primary-hover: #4f46e5;
  --secondary-color: #a855f7;
  --success-color: #10b981;
  --error-color: #ef4444;
}

* {
  box-sizing: border-box;
  margin: 0;
  padding: 0;
}

body {
  font-family: 'Outfit', -apple-system, BlinkMacSystemFont, sans-serif;
  background: radial-gradient(circle at 50% 50%, #1a183a 0%, var(--bg-color) 100%);
  color: var(--text-color);
  min-height: 100vh;
  display: flex;
  justify-content: center;
  align-items: flex-start; /* 靠顶端放置，避开手机键盘 */
  padding: 10px;
  overflow-x: hidden;
}

#app {
  width: 100%;
  display: flex;
  justify-content: center;
  align-items: flex-start;
}

/* 高扁平化卡片，节省高度 */
.card {
  background: var(--card-bg);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  border: 1px solid var(--card-border);
  border-radius: 16px;
  padding: 16px;
  width: 100%;
  max-width: 460px;
  box-shadow: 0 15px 35px rgba(0, 0, 0, 0.4);
  margin-top: 10px;
}

/* 顶部紧凑控制栏 */
.top-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
}

/* 链路事件行：小字、低调，但断连时有据可查 */
.event-log {
  font-size: 11px;
  color: var(--text-muted);
  margin-bottom: 8px;
  min-height: 14px;
  line-height: 1.4;
  word-break: break-all;
}

/* 左侧状态与扫描连接 */
.left-controls {
  display: flex;
  align-items: center;
  gap: 8px;
}

.status-badge {
  font-size: 11px;
  font-weight: 600;
  padding: 4px 8px;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.05);
  color: var(--text-muted);
  display: flex;
  align-items: center;
  gap: 4px;
}

.status-badge::before {
  content: '';
  display: inline-block;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--text-muted);
}

.status-badge.disconnected::before { background: var(--error-color); }
.status-badge.connecting::before {
  background: #f59e0b;
  animation: pulse 1s infinite alternate;
}
.status-badge.connected {
  color: var(--success-color);
  background: rgba(16, 185, 129, 0.1);
}
.status-badge.connected::before { background: var(--success-color); }

@keyframes pulse {
  from { opacity: 0.4; }
  to { opacity: 1; }
}

.btn-connect {
  padding: 5px 10px;
  font-size: 11px;
  font-weight: 600;
  border-radius: 8px;
  border: none;
  background: linear-gradient(135deg, var(--primary-color) 0%, var(--secondary-color) 100%);
  color: white;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 4px;
  transition: opacity 0.15s ease;
}

.btn-connect:hover {
  opacity: 0.9;
}

.btn-connect:disabled {
  opacity: 0.5;
  cursor: default;
}

/* 右侧即时输入 Switch 开关 */
.switch-container {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--text-muted);
}

.switch {
  position: relative;
  display: inline-block;
  width: 36px;
  height: 20px;
}

.switch input {
  opacity: 0;
  width: 0;
  height: 0;
}

.slider {
  position: absolute;
  cursor: pointer;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: #374151;
  transition: .3s;
  border-radius: 20px;
}

.slider:before {
  position: absolute;
  content: "";
  height: 14px;
  width: 14px;
  left: 3px;
  bottom: 3px;
  background-color: white;
  transition: .3s;
  border-radius: 50%;
}

input:checked + .slider {
  background-color: var(--primary-color);
}

input:checked + .slider:before {
  transform: translateX(16px);
}

/* 输入区域 */
textarea {
  width: 100%;
  height: 80px;
  background: rgba(0, 0, 0, 0.25);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 10px;
  padding: 10px;
  font-family: inherit;
  font-size: 14px;
  color: white;
  resize: none;
  outline: none;
  transition: all 0.2s ease;
}

textarea:focus {
  border-color: var(--primary-color);
  background: rgba(0, 0, 0, 0.35);
}

/* 经典模式按钮组 */
.button-group {
  margin-top: 10px;
  display: flex;
  gap: 8px;
}

.btn {
  flex: 1;
  padding: 10px;
  border-radius: 8px;
  border: none;
  font-family: inherit;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s ease;
}

.btn-send {
  background: var(--primary-color);
  color: white;
}

.btn-send:disabled {
  background: #374151;
  color: #9ca3af;
  cursor: not-allowed;
}

.btn-clear {
  background: rgba(255, 255, 255, 0.05);
  color: var(--text-muted);
  border: 1px solid rgba(255, 255, 255, 0.05);
}

/* 剪贴板同步按钮组 */
.clipboard-group {
  margin-top: 14px;
  border-top: 1px solid rgba(255, 255, 255, 0.04);
  padding-top: 12px;
  display: flex;
  gap: 8px;
}

.btn-pull {
  background: rgba(168, 85, 247, 0.1);
  color: #c084fc;
  border: 1px solid rgba(168, 85, 247, 0.2);
}

.btn-pull:hover {
  background: rgba(168, 85, 247, 0.2);
  border-color: rgba(168, 85, 247, 0.4);
}

.btn-push {
  background: rgba(99, 102, 241, 0.1);
  color: #818cf8;
  border: 1px solid rgba(99, 102, 241, 0.2);
}

.btn-push:hover {
  background: rgba(99, 102, 241, 0.2);
  border-color: rgba(99, 102, 241, 0.4);
}
```

- [ ] **Step 3: 构建单文件**

Run:

```bash
npm run build
```

Expected：构建成功，生成 `dist/index.html`。

- [ ] **Step 4: 确认产物**

Run:

```bash
ls -la dist
```

Expected：只有 `index.html`（`vite-plugin-singlefile` 已把 JS/CSS 内联）。

- [ ] **Step 5: 提交**

```bash
git add src/App.vue src/styles.css
git commit -m "feat: 用 Vue 重写页面与输入交互"
```

---

### Task 7: 图标与 PWA 构建

**Files:**
- Create: `assets/icon.svg`
- Create: `public/icon-192.png`
- Create: `public/icon-512.png`

- [ ] **Step 1: 创建 `assets/icon.svg`**

```svg
<svg xmlns="http://www.w3.org/2000/svg" width="512" height="512" viewBox="0 0 512 512">
  <defs>
    <linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#6366f1"/>
      <stop offset="1" stop-color="#a855f7"/>
    </linearGradient>
  </defs>
  <rect width="512" height="512" rx="112" fill="#0f0f13"/>
  <g fill="none" stroke="url(#g)" stroke-width="28" stroke-linecap="round" stroke-linejoin="round">
    <path d="M256 128 L336 192 L176 256 L336 320 L256 384"/>
    <path d="M256 128 L256 384"/>
  </g>
</svg>
```

- [ ] **Step 2: 生成 PNG**

```bash
mkdir -p public
magick -background none assets/icon.svg -resize 192x192 public/icon-192.png
magick -background none assets/icon.svg -resize 512x512 public/icon-512.png
```

Expected：两张 PNG 生成成功。

- [ ] **Step 3: 构建 PWA**

Run:

```bash
npm run build:pwa
```

Expected：构建成功，`dist/` 中包含 `index.html`、`assets/`、`manifest.webmanifest`、`sw.js`、`registerSW.js`、两张图标。

- [ ] **Step 4: 确认 PWA 产物**

Run:

```bash
ls dist && ls dist/assets
```

Expected：能看到 `manifest.webmanifest` 与 `sw.js`；`assets/` 下有带 hash 的 JS/CSS。

- [ ] **Step 5: 提交**

```bash
git add assets/icon.svg public/icon-192.png public/icon-512.png
git commit -m "feat: PWA 图标与在线构建产物"
```

---

### Task 8: 本地 HTTPS 服务与文档

**Files:**
- Modify: `serve_web.py`
- Modify: `readme.md`
- Modify: `docs/HANDOFF.md`

- [ ] **Step 1: 重写 `serve_web.py`**

```python
"""给手机加载网页用的极简 HTTPS 静态服务。

Web Bluetooth 要求安全上下文，所以必须走 HTTPS；自签证书需要在手机上手动信任一次。
只负责把构建产物 dist/ 交出去，通信全部走蓝牙通道。

用法：
    npm run build
    uv run --project pc python serve_web.py
"""

import http.server
import logging
import socket
import ssl
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist"
CERTS = ROOT / "certs"
PORT = 8443

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger("web")


def local_ip() -> str:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0]
    finally:
        sock.close()


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(DIST), **kwargs)

    def log_message(self, format, *args) -> None:
        pass


def main() -> None:
    if not DIST.is_dir():
        raise SystemExit("dist/ 不存在，请先运行 npm run build")

    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(CERTS / "cert.pem", CERTS / "key.pem")

    httpd = http.server.HTTPServer(("0.0.0.0", PORT), Handler)
    httpd.socket = context.wrap_socket(httpd.socket, server_side=True)

    logger.info("手机访问：https://%s:%d", local_ip(), PORT)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 语法检查**

Run:

```bash
uv run --project pc python -m py_compile serve_web.py
```

Expected：无输出、退出码 0。

- [ ] **Step 3: 更新 `readme.md`**

把「使用方法」「目录结构」「开发」三节改为：

````markdown
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
npm run build      # 单文件产物 dist/index.html
npm run build:pwa  # PWA 产物，供 GitHub Pages 部署
```

改协议时，`protocol.md`、`pc/server.py`、`src/logic/protocol.js`、`src/logic/frame-codec.js` 必须同步。
````

- [ ] **Step 4: 更新 `docs/HANDOFF.md`**

把「三、代码地图」「四、怎么跑」「九、协作约定」中的相关条目改为：

代码地图：

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
├── serve_web.py                托管 dist/ 的 HTTPS 静态服务
├── pc\                         电脑端
└── .trash\                     废弃文件暂存区
```

怎么跑：

```powershell
npm install
npm run dev                    # 手机打开 https://<局域网IP>:5173
npm run build                  # 单文件产物
npm run build:pwa              # PWA 产物
uv run --project pc python serve_web.py   # 托管 dist/，端口 8443
```

协作约定中的同步位置改为：`protocol.md`、`pc/server.py`、`src/logic/protocol.js`、`src/logic/frame-codec.js`。

- [ ] **Step 5: 提交**

```bash
git add serve_web.py readme.md docs/HANDOFF.md
git commit -m "chore: 本地服务改为托管 dist，文档同步新工程结构"
```

---

### Task 9: 全量验证

**Files:** 无新增或修改。

- [ ] **Step 1: 单元测试**

Run:

```bash
npm test
```

Expected：5 个测试全部 PASS。

- [ ] **Step 2: 单文件构建**

Run:

```bash
npm run build
```

Expected：成功，`dist/index.html` 存在且体积大于 100 KB。

- [ ] **Step 3: PWA 构建**

Run:

```bash
npm run build:pwa
```

Expected：成功，`dist/manifest.webmanifest` 与 `dist/sw.js` 存在。

- [ ] **Step 4: 开发服务器冒烟检查**

Run:

```bash
node node_modules/vite/bin/vite.js --host > "$TEMP/vite-dev.log" 2>&1 &
VITE_PID=$!
sleep 6
curl -sk -o /dev/null -w "%{http_code}\n" https://127.0.0.1:5173/
kill $VITE_PID
```

Expected：输出 `200`。

- [ ] **Step 5: 确认工作区干净**

Run:

```bash
git status --short
```

Expected：无输出。

- [ ] **Step 6: 真机验收交付**

把以下验收点列给用户，由用户用手机完成：

1. `npm run dev` 后手机打开 `https://<局域网IP>:5173`，页面正常显示。
2. 点「扫描连接」能选中电脑并连上，状态变绿、事件行显示「已连接（第 1 段）」。
3. 即时模式逐字上屏、退格、回车；中文输入法组合结束才发送。
4. 经典模式下 `Ctrl+Enter` 或「发送」按钮整段上屏，内容带换行。
5. 拉取剪贴板：电脑内容出现在输入框并写入手机剪贴板。
6. 推送剪贴板：手机剪贴板内容覆盖电脑剪贴板。
7. 杀掉电脑端进程，网页 9 秒内判定断开，重启电脑端后自动接回。
````

---

## 实施偏差记录

执行过程中对计划原文做了以下修正，代码以此为准：

1. **Task 2 脚本**：`test` 改为 `node --test src/logic/*.test.js`（Node 24 不接受裸目录参数）；移除 `rimraf`（Vite 默认清空 `outDir`）；`dev` 改为 `vite`（`server.host: true` 已在配置中）；删除会误导的 `preview` 脚本；PWA manifest 增加 `lang: 'zh-CN'`。
2. **Task 4 BLE 生命周期加固**：`connect()` 改为单飞；引入代际校验（重新扫描、断链递增，作废在途连接与旧写队列）；重新扫描时先取到新设备再拆除旧链路，取消选择保留旧连接；重连改为 `setTimeout` 串行调度，并以实际拿到 characteristic 判定成功。这些修正解决了旧实现中迟到的连接失败击穿新链路、假 connected、重连停摆等竞态。
3. **Task 3 测试**：在计划 5 条用例之外增加跨语言字节夹具、4 字节长度字段、UTF-8 多字节字符中间分片三条，共 8 条。
4. **Task 6 输入区**：即时输入不再使用 `v-model` + 模板 `@input` 的组合（依赖 Vue 内部监听器注册顺序），改为 `:value="text"` + 单一 `@input`；`composing` 改为普通变量；组合期间 `keydown` 直接返回；剪贴板写回改为 async try/catch；Web Bluetooth 能力检查与提示上移到 `App.vue`。
5. **Task 6/7 产物**：单文件构建的 `dist/` 会连同 `public/` 下两张 PWA 图标一起复制，`index.html` 本身 JS/CSS 已全部内联，体积约 80 KB。
6. **Task 9 验证**：单文件产物约 80 KB，不采用计划里「大于 100 KB」的经验阈值；以构建成功与内联检查为准。
7. **输入区细节**：即时模式下只对 `insertText` 与 `deleteContentBackward` 清空输入框，其他输入类型保留内容（与旧版一致）；不在连接状态时切换即时开关，占位文案优先显示链路状态（比旧版更合理，属已记录的小偏差）。
8. **运行环境**：`package.json` 声明 `engines.node >= 22`，因为 `node --test` 的 glob 参数需要 Node 22+。
