<script setup>
import { computed, onUnmounted, ref, watch } from 'vue';
import { useBle } from './composables/useBle.js';
import { BENCH_BYTES } from './logic/protocol.js';
import { describeBench, randomBenchPayload, sha256Hex } from './logic/bench.js';
import { needRefresh, updateServiceWorker } from '@pwa-update';

const instantMode = ref(true);
const text = ref('');
const inputEl = ref(null);
let composing = false;
const hasTriedConnect = ref(false);
// 测速期间两颗按钮都锁住：一次只跑一个方向。
const benching = ref(false);

const {
  status,
  lastEvent,
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
});

const statusLabel = computed(
  () => ({ disconnected: '未连接', connecting: '连接中', connected: '已连接' })[status.value],
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
  if (state !== 'connected') {
    // 断线或重连期间结果不会再来，别把按钮一直锁着。
    benching.value = false;
    return;
  }
  focusInput();
});

function connect() {
  if (!navigator.bluetooth) {
    alert('浏览器不支持 Web Bluetooth，或页面不在 HTTPS 下打开。');
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

async function pushClipboard() {
  restoreInputFocus();
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
  try {
    // 等到最后一片的 ATT 应答再宣布成功：send() 只代表进了队列。
    await sendAsync({ t: 'clip', v: content });
    note(`成功推送剪贴板（${content.length} 字符）`);
  } catch (err) {
    note('推送剪贴板失败：' + err.message);
  }
}

async function applyPulledClipboard(content) {
  // 成功的标志是写进手机剪贴板，不再把内容塞进输入框。
  try {
    await navigator.clipboard.writeText(content);
    note(`成功拉取剪贴板（${content.length} 字符）`);
  } catch (err) {
    console.warn('写入手机剪贴板失败', err);
    // 浏览器拒绝写入时保底：放进输入框，内容不至于丢。
    text.value = content;
    note('手机剪贴板写入失败，内容已放进输入框');
  }
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
    ? '测速中… 99%（等待链路确认）'
    : `测速中… ${percent}%`;
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
  lastEvent.value = '测速中…';
  try {
    // 单包大小先取：写完再看，链路可能已经断了。
    const chunk = uplinkChunkSize();
    // 计时终点是最后一片的 ATT 应答——它到达时前面的分片已在空中排空，
    // 所以这个耗时就是真实空口时间，不是本地入队时间。
    await sendAsync({ t: 'benchup', v: payload, sha256 }, showBenchProgress);
    note(
      describeBench('上行', {
        bytes: BENCH_BYTES,
        ms: performance.now() - benchStarted,
        chunk,
      }),
    );
  } catch (err) {
    note('上行测速中断：' + err.message);
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
  lastEvent.value = '测速中…';
  // 计时只能在手机端做，电脑端只管发数据。
  send({ t: 'benchdown' });
}

async function showBenchResult({ bytes, chunk, sha256, payload }) {
  benching.value = false;
  const summary = describeBench('下行', { bytes, ms: benchDoneAt - benchStarted, chunk });
  // 电脑端每次发随机载荷，哈希对不上就是分片被调换、重复或丢了字节。
  // 这种情况帧仍是合法 JSON，长度也对，前面那些检查一律看不出来。
  const actual = await sha256Hex(payload);
  // 通过就不必说：结果行本来就够长了，多一段哈希还要换行。失败才顶上去。
  note(
    actual === sha256
      ? summary
      : `${summary} · 内容校验失败（${actual.slice(0, 8)}≠${sha256.slice(0, 8)}）`,
  );
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
      <button
        class="status-badge"
        :class="status"
        :disabled="status === 'connecting'"
        :aria-label="status === 'connected' ? '重新连接' : '连接蓝牙'"
        @click="connect"
      >
        {{ statusLabel }}
      </button>

      <div class="switch-container">
        <span>即时发送</span>
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
      <button class="btn-clear" @click="clearInput">清空</button>
      <button class="btn-send" :disabled="!connected" @click="sendText">
        发送 (Ctrl+Enter)
      </button>
    </div>

    <div class="clipboard-group">
      <button class="btn-pull" :disabled="!connected" @pointerdown="rememberInputFocus" @click="pullClipboard">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <path d="M12 4v14" /><path d="M6 13l6 6 6-6" />
        </svg>
        拉取剪贴板
      </button>
      <button class="btn-push" :disabled="!connected" @pointerdown="rememberInputFocus" @click="pushClipboard">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <path d="M12 20V6" /><path d="M6 11l6-6 6 6" />
        </svg>
        推送剪贴板
      </button>
    </div>

    <div class="bench-group">
      <button class="btn-bench" :disabled="!connected || benching" @click="benchUplink">
        上行测速
      </button>
      <span class="bench-sep"></span>
      <button class="btn-bench" :disabled="!connected || benching" @click="benchDownlink">
        下行测速
      </button>
    </div>

    <div class="event-log">
      {{ lastEvent }}
      <button
        v-if="needRefresh"
        class="update-hint"
        @click="updateServiceWorker(true)"
      >
        有新版本，点击刷新
      </button>
    </div>
  </div>
</template>
