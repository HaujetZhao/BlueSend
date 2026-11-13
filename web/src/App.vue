<script setup>
import { computed, onUnmounted, ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { useBle } from './composables/useBle.js';
import { BENCH_BYTES } from './logic/protocol.js';
import { randomBenchPayload, sha256Hex } from './logic/bench.js';
import { setLocale } from './logic/i18n.js';
import { needRefresh, updateServiceWorker } from '@pwa-update';

const { t, locale } = useI18n({ useScope: 'global' });
const nextLocale = computed(() => (locale.value === 'zh' ? 'en' : 'zh'));

const instantMode = ref(true);
const text = ref('');
const inputEl = ref(null);
let composing = false;
const hasTriedConnect = ref(false);
// 测速期间两颗按钮都锁住：一次只跑一个方向。
const benching = ref(false);
// 文件上传入口（连接作用域）。电脑会下发所有候选地址，手机逐个探测，用第一个
// 通的。探测是 HTTPS 页面发往局域网 HTTP 的请求：Chrome 用「本地网络」权限放行，
// 请求需要声明 targetAddressSpace，授权后即豁免混合内容拦截。
const uploadLinks = ref([]);
const uploadPerm = ref('unsupported');
const uploadBusy = ref(false);
const uploadBlocked = ref(false);
// 探测结果只对当次 net 有效。用代际号判新旧，不能比数组引用：ref 会把数组
// 包成 reactive 代理，uploadLinks.value 永远不等于传进来的原始数组。
let uploadGeneration = 0;

const {
  status,
  lastEvent,
  warning,
  connected,
  connect: connectBle,
  send,
  sendAsync,
  uplinkChunkSize,
  note,
} = useBle({
  onClipboard: applyPulledClipboard,
  onBench: showBenchResult,
  onReceiveProgress: showReceiveProgress,
  onNet: (hosts) => {
    uploadGeneration += 1;
    uploadLinks.value = hosts;
    uploadBusy.value = false;
    uploadBlocked.value = false;
    if (hosts.length) prepareUpload(hosts, uploadGeneration);
  },
});

const statusLabel = computed(() => t(`status.${status.value}`));
// 已授权时探测完全自动，探不到可达入口就把按钮置灰；但置灰只是提示，不阻止
// 点击——网络可能在两次探测之间恢复，真正可不可达由点击那一刻的探测决定。
// 没授权时无法探测，按钮同样保持可点，那次点击是触发授权提示的用户手势。
const canUpload = computed(
  () => connected.value
    && uploadLinks.value.length > 0
    && !uploadBusy.value,
);
const placeholder = computed(() => {
  if (status.value === 'connecting') return t('placeholder.connecting');
  if (status.value === 'connected') {
    return instantMode.value ? t('placeholder.instant') : t('placeholder.manual');
  }
  return hasTriedConnect.value ? t('placeholder.background') : t('placeholder.idle');
});

function toggleLocale() {
  setLocale(nextLocale.value);
}

watch(status, (state) => {
  if (state !== 'connected') {
    // 断线或重连期间结果不会再来，别把按钮一直锁着。
    benching.value = false;
    return;
  }
  // 版本不兼容时弹窗会打断操作，别先把焦点抢到输入框、把键盘顶起来。
  if (warning.value) return;
  focusInput();
});

watch(warning, (text) => {
  if (!text) return;
  // 弹窗出现时收起键盘；不然遮罩挡着，输入框还占着键盘。
  inputEl.value?.blur();
});

function dismissWarning() {
  warning.value = '';
}

function connect() {
  if (!navigator.bluetooth) {
    alert(t('alerts.noBluetooth'));
    return;
  }
  hasTriedConnect.value = true;
  connectBle();
}

function focusInput() {
  inputEl.value?.focus();
}

// 点按钮会把焦点从输入框抢走（手机键盘跟着收起）。按下之前先记住焦点在不在
// 输入框里，操作开始后还回去——原本没在打字就维持原样。
let inputHadFocus = false;

function rememberInputFocus() {
  inputHadFocus = document.activeElement === inputEl.value;
}

function restoreInputFocus() {
  if (!inputHadFocus) return;
  inputHadFocus = false;
  focusInput();
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

function onCompositionStart() {
  composing = true;
}

function onCompositionEnd(event) {
  composing = false;
  if (!instantMode.value) return;
  if (event.data) send({ t: 'text', v: event.data });
  clearTextarea(event);
  focusInput();
}

function onInput(event) {
  if (!instantMode.value) {
    text.value = event.target.value;
    return;
  }
  if (composing) {
    // 组合期间让模型跟随输入框，避免其他响应式更新冲掉输入法候选文本。
    text.value = event.target.value;
    return;
  }
  if (event.inputType === 'insertText') {
    if (event.data) send({ t: 'text', v: event.data });
    clearTextarea(event);
  } else if (event.inputType === 'deleteContentBackward') {
    send({ t: 'key', v: 'backspace' });
    clearTextarea(event);
  } else {
    // 其他输入类型（如 Delete、Ctrl+Backspace）保留在输入框里，与旧版一致。
    text.value = event.target.value;
  }
}

function clearTextarea(event) {
  event.target.value = '';
  text.value = '';
}

function onPaste(event) {
  if (!instantMode.value) return;
  event.preventDefault();
  const pasted = event.clipboardData.getData('text');
  if (pasted) send({ t: 'text', v: pasted });
  clearTextarea(event);
  focusInput();
}

function onKeydown(event) {
  if (composing) return;
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
    clearTextarea(event);
    focusInput();
  } else if (event.key === 'Backspace' && text.value === '') {
    event.preventDefault();
    send({ t: 'key', v: 'backspace' });
  }
}

function pullClipboard() {
  restoreInputFocus();
  send({ t: 'pull' });
}

const LOCAL_NETWORK_PERMISSION = 'local-network';
// 局域网内的 HTTP 响应是毫秒级的（实测几十毫秒），0.5 秒足够；探测是并发跑的，
// 等待上限就是这个值，不可达的候选不该让用户干等。
const PROBE_TIMEOUT_MS = 500;
// 公网页面上首次探测会弹「本地网络」授权框，用户可能要看几秒，别被普通超时打断。
const PROBE_PROMPT_TIMEOUT_MS = 20000;
// 页面本身就在局域网地址上时（本地 dev server），请求属于同地址空间，不需要
// 本地网络权限，浏览器也不会弹授权框——只有公网页面（在线版）才可能要。
const pageIsLocal = /^(localhost|127\.|10\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.)/.test(
  location.hostname,
);

// 这次探测可能弹出授权框：公网页面且权限还是 prompt。denied 不会再弹。
function mayPrompt() {
  return !pageIsLocal && uploadPerm.value === 'prompt';
}

// 公网页面上还没拿到本地网络权限：探测失败也可能是权限没放行。
function permissionMayBlock() {
  return !pageIsLocal && (uploadPerm.value === 'prompt' || uploadPerm.value === 'denied');
}

async function permissionState() {
  try {
    const status = await navigator.permissions.query({
      name: LOCAL_NETWORK_PERMISSION,
    });
    return status.state;
  } catch {
    // 老浏览器不认识这个权限名，也就没有豁免混合内容的办法。
    return 'unsupported';
  }
}

// 收到 net 后自动探测一次，据此决定按钮要不要提示性置灰。探测结果只是提示：
// 网络和权限都可能随时变化，点击时一律重新探测。
// 权限状态不能当探测的前置条件：local-network 管的是「公网页面访问局域网」，
// 页面本身就在局域网地址上时同地址空间不需要授权（实测权限是 prompt 也能通）。
// 只有公网页面 + 浏览器不认识这个权限时才跳过，那种情况下探测必然被混合内容拦死。
async function prepareUpload(hosts, generation) {
  uploadPerm.value = await permissionState();
  if (generation !== uploadGeneration) return;
  if (uploadPerm.value === 'unsupported' && !pageIsLocal) return;
  uploadBusy.value = true;
  const url = await firstReachable(hosts, PROBE_TIMEOUT_MS);
  if (generation !== uploadGeneration) return;
  uploadBusy.value = false;
  uploadBlocked.value = !url;
  // 按钮自己变灰，得让用户知道为什么。
  if (uploadBlocked.value) noteUnreachable();
}

// 探测失败在 fetch 里一律是 TypeError，分不清是网络不通还是浏览器没给本地
// 网络权限，所以权限可能挡路时把两种可能都说出来。
function noteUnreachable() {
  note(
    permissionMayBlock()
      ? t('upload.unreachablePermission')
      : t('upload.unreachable'),
  );
}

// 打开电脑托管的上传页。探测完成前不打开任何页面：不可达时不该甩给用户一个
// 空白页。探测是并发的，正常网络下 0.5 秒内就有结果，仍在 Chrome 留给
// window.open 的用户激活窗口（5 秒）内；真被拦截就退化为顶层导航。
async function openUpload() {
  const hosts = uploadLinks.value;
  if (!hosts.length) return;
  note(t('upload.probing'));
  // 每次点击都重新探测：网络可能在两次 net 之间断掉，之前探测的结果不可信。
  let url;
  if (uploadPerm.value === 'unsupported' && !pageIsLocal) {
    // 公网页面上没法豁免混合内容，只能用默认路由那个地址，失败就失败。
    url = hosts[0];
  } else {
    const timeout = mayPrompt() ? PROBE_PROMPT_TIMEOUT_MS : PROBE_TIMEOUT_MS;
    url = await firstReachable(hosts, timeout);
  }
  if (!url) {
    // 这次点击可能刚刚拿到授权，重新读一次权限，只为了让提示说得准确。
    uploadPerm.value = await permissionState();
    uploadBlocked.value = true;
    noteUnreachable();
    return;
  }
  uploadBlocked.value = false;
  const popup = window.open(url, '_blank');
  if (!popup) {
    // 授权提示耗时超过激活窗口时 window.open 会被拦；顶层导航总能打开。
    location.href = url;
    return;
  }
  note(t('upload.opened'));
}

// 用来探测的请求走本机的 /ping，token 原样带上。targetAddressSpace 让 Chrome
// 在解析前就知道目标是局域网，用户授权后豁免混合内容拦截。
async function reachable(pageUrl, timeoutMs) {
  const probe = new URL(pageUrl);
  probe.pathname = '/ping';
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    await fetch(probe, {
      mode: 'no-cors',
      cache: 'no-store',
      targetAddressSpace: 'local',
      signal: controller.signal,
    });
    return true;
  } catch {
    return false;
  } finally {
    clearTimeout(timer);
  }
}

// 并发探测全部候选，第一个通的胜出。串行最坏要 N × 超时，点击时容易耗光
// 浏览器留给 window.open 的用户激活窗口。
async function firstReachable(hosts, timeoutMs) {
  return new Promise((resolve) => {
    let pending = hosts.length;
    for (const url of hosts) {
      reachable(url, timeoutMs).then((ok) => {
        if (ok) resolve(url);
        else if (--pending === 0) resolve(null);
      });
    }
  });
}

async function pushClipboard() {
  restoreInputFocus();
  let content;
  try {
    content = await navigator.clipboard.readText();
  } catch (err) {
    alert(t('alerts.clipboardReadDenied', { message: err.message }));
    return;
  }
  if (!content) {
    alert(t('alerts.clipboardEmpty'));
    return;
  }
  try {
    // 等到最后一片的 ATT 应答再宣布成功：send() 只代表进了队列。
    await sendAsync({ t: 'clip', v: content });
    note(t('clipboard.pushed', { count: String(content.length) }));
  } catch (err) {
    note(t('clipboard.pushFailed', { message: err.message }));
  }
}

async function applyPulledClipboard(content) {
  // 成功的标志是写进手机剪贴板，不再把内容塞进输入框。
  try {
    await navigator.clipboard.writeText(content);
    note(t('clipboard.pulled', { count: String(content.length) }));
  } catch (err) {
    console.warn('写入手机剪贴板失败', err);
    // 浏览器拒绝写入时保底：放进输入框，内容不至于丢。
    text.value = content;
    note(t('clipboard.writeFailed'));
  }
}

// 结果行按当前语言拼装。插值一律传字符串：vue-i18n 会对数字做本地化分组
// （1,234），把「256 KB」的口径弄乱。
function benchText(directionKey, { bytes, ms, chunk }) {
  const seconds = ms / 1000;
  const rate = bytes / seconds / 1024;
  return t('bench.result', {
    direction: t(directionKey),
    kb: String(bytes / 1024),
    seconds: seconds.toFixed(1),
    rate: rate.toFixed(1),
    chunk: String(chunk),
  });
}

// 一片一片刷会让事件行闪个不停，节流到 100 毫秒一次。
const PROGRESS_INTERVAL_MS = 100;
let benchDirection = '';
let benchStarted = 0;
let benchDoneAt = 0;
let benchShownAt = 0;

// 过程只报百分比，速率一律只在结果行出现。
// 上行的进度来自无响应写的 resolve，那是「进了协议栈队列」而不是「上了空中」——
// 实测入队 3.7 毫秒/片、空口 5.9 毫秒/片。拿它算速率会比真实值高出一截，等最后
// 一片的 ATT 应答回来又被总时间打回原形，看着就是「卡两秒、速度腰斩」。下行的进度
// 虽然是真实收到的字节，但一次测速只有几秒，过程速率没什么意义，口径统一更安静。
function showBenchProgress(received, total) {
  const now = performance.now();
  const percent = Math.floor((received / total) * 100);
  // 最后一片要等前面所有分片排空，期间没有新的进度可报，别被节流吞掉。
  if (percent < 99 && now - benchShownAt < PROGRESS_INTERVAL_MS) return;
  benchShownAt = now;
  lastEvent.value = benchDirection === 'up' && percent >= 99
    ? t('bench.draining')
    : t('bench.progress', { percent: String(percent) });
}

// 下行进度由手机自己从帧头算：电脑端的 notify 返回时只是把数据塞进了发送队列，
// 发大帧时也插不进任何消息来报进度。progress 为 null 表示这一帧已经收完。
function showReceiveProgress(progress) {
  if (!benching.value || benchDirection !== 'down') return;
  if (!progress) {
    benchDoneAt = performance.now();
    return;
  }
  // 只有测速消息会这么大，心跳、剪贴板不管。
  if (progress.total < BENCH_BYTES) return;
  // 第一片到达才算开始，不含电脑端准备的那段时间。
  if (!benchStarted) benchStarted = performance.now();
  showBenchProgress(progress.received, progress.total);
}

async function benchUplink() {
  if (benching.value) return;
  benching.value = true;
  benchDirection = 'up';
  benchShownAt = 0;
  // 载荷与哈希在计时窗口外生成。消息自带 sha256，电脑端重算比对——无响应写
  // 的分片若被调换，帧仍合法、长度也对，只有内容哈希能发现。
  const payload = randomBenchPayload();
  const sha256 = await sha256Hex(payload);
  benchStarted = performance.now();
  // 只改事件行，不发 log 消息：日志写在计时窗口之前会污染测量。
  lastEvent.value = t('bench.running');
  try {
    // 单包大小先取：写完再看，链路可能已经断了。
    const chunk = uplinkChunkSize();
    // 计时终点是最后一片的 ATT 应答——它到达时前面的分片已在空中排空，
    // 所以这个耗时就是真实空口时间，不是本地入队时间。
    await sendAsync({ t: 'benchup', v: payload, sha256 }, showBenchProgress);
    note(
      benchText('bench.up', {
        bytes: BENCH_BYTES,
        ms: performance.now() - benchStarted,
        chunk,
      }),
    );
  } catch (err) {
    note(t('bench.upInterrupted', { message: err.message }));
  } finally {
    benching.value = false;
  }
}

function benchDownlink() {
  if (benching.value) return;
  benching.value = true;
  benchDirection = 'down';
  benchStarted = 0;
  benchDoneAt = 0;
  benchShownAt = 0;
  lastEvent.value = t('bench.running');
  // 计时只能在手机端做，电脑端只管发数据。
  send({ t: 'benchdown' });
}

async function showBenchResult({ bytes, chunk, sha256, payload }) {
  benching.value = false;
  const summary = benchText('bench.down', { bytes, ms: benchDoneAt - benchStarted, chunk });
  // 电脑端每次发随机载荷，哈希对不上就是分片被调换、重复或丢了字节。
  // 这种情况帧仍是合法 JSON，长度也对，前面那些检查一律看不出来。
  const actual = await sha256Hex(payload);
  // 通过就不必说：结果行本来就够长了，多一段哈希还要换行。失败才顶上去。
  note(
    actual === sha256
      ? summary
      : `${summary} · ${t('bench.checksumFailed', {
        actual: actual.slice(0, 8),
        expected: sha256.slice(0, 8),
      })}`,
  );
}

// 同一个页面开多个标签页时，每个标签页都是一路独立的 Web Bluetooth 客户端，
// 会互相抢同一台设备。开页时就探测并提醒。
const tabChannel = new BroadcastChannel('ble-tab');
tabChannel.onmessage = (event) => {
  if (event.data === 'ping') {
    tabChannel.postMessage('here');
  } else {
    note(t('events.duplicateTab'));
  }
};
tabChannel.postMessage('ping');

onUnmounted(() => tabChannel.close());
</script>

<template>
  <div class="card">
    <div class="top-bar">
      <button
        class="status-badge"
        :class="status"
        :disabled="status === 'connecting'"
        :aria-label="status === 'connected' ? t('status.reconnectAria') : t('status.connectAria')"
        @click="connect"
      >
        {{ statusLabel }}
      </button>

      <div class="switch-container">
        <span>{{ t('switch.instant') }}</span>
        <label class="switch">
          <input v-model="instantMode" type="checkbox" @change="toggleInstant">
          <span class="slider"></span>
        </label>
      </div>
    </div>

    <textarea
      ref="inputEl"
      :value="text"
      :style="{ height: instantMode ? '96px' : '120px' }"
      :placeholder="placeholder"
      @compositionstart="onCompositionStart"
      @compositionend="onCompositionEnd"
      @input="onInput"
      @paste="onPaste"
      @keydown="onKeydown"
    ></textarea>

    <div v-if="!instantMode" class="button-group">
      <button class="btn-clear" @click="clearInput">{{ t('actions.clear') }}</button>
      <button class="btn-send" :disabled="!connected" @click="sendText">
        {{ t('actions.send') }}
      </button>
    </div>

    <div class="clipboard-group">
      <button class="btn-pull" :disabled="!connected" @pointerdown="rememberInputFocus" @click="pullClipboard">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <path d="M12 4v14" /><path d="M6 13l6 6 6-6" />
        </svg>
        {{ t('actions.pullClipboard') }}
      </button>
      <button class="btn-push" :disabled="!connected" @pointerdown="rememberInputFocus" @click="pushClipboard">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <path d="M12 20V6" /><path d="M6 11l6-6 6 6" />
        </svg>
        {{ t('actions.pushClipboard') }}
      </button>
    </div>

    <div class="bench-group">
      <button class="btn-bench" :disabled="!connected || benching" @click="benchUplink">
        {{ t('actions.benchUp') }}
      </button>
      <span class="bench-sep"></span>
      <button class="btn-bench" :disabled="!connected || benching" @click="benchDownlink">
        {{ t('actions.benchDown') }}
      </button>
      <span class="bench-sep"></span>
      <button
        class="btn-bench"
        :class="{ 'is-blocked': uploadBlocked }"
        :disabled="!canUpload"
        @click="openUpload"
      >
        {{ t('actions.sendFile') }}
      </button>
    </div>

    <div class="event-log">
      {{ lastEvent || t('events.notConnected') }}
      <button
        v-if="needRefresh"
        class="update-hint"
        @click="updateServiceWorker(true)"
      >
        {{ t('actions.refresh') }}
      </button>
    </div>
  </div>

  <div v-if="warning" class="modal-mask" role="alertdialog" aria-modal="true">
    <div class="modal">
      <h2 class="modal-title">{{ t('warning.title') }}</h2>
      <p class="modal-text">{{ warning }}</p>
      <div class="modal-actions">
        <button @click="dismissWarning">{{ t('actions.dismiss') }}</button>
      </div>
    </div>
  </div>

  <footer class="repo">
    <button class="lang-switch" :aria-label="t('actions.langToggleAria')" @click="toggleLocale">
      {{ t('localeName') }}
    </button>
    <a href="https://github.com/HaujetZhao/BlueSend" target="_blank" rel="noopener">
      <svg viewBox="0 0 16 16" aria-hidden="true">
        <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z" />
      </svg>
      HaujetZhao/BlueSend
    </a>
  </footer>
</template>
