<script setup>
import { computed, onUnmounted, ref, watch } from 'vue';
import { useBle } from './composables/useBle.js';
import { needRefresh, updateServiceWorker } from '@pwa-update';

const instantMode = ref(true);
const text = ref('');
const inputEl = ref(null);
let composing = false;
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

async function applyPulledClipboard(content) {
  text.value = content;
  focusInput();
  // 浏览器权限限制下写入可能失败；内容已经显示在输入框里，不影响使用。
  try {
    await navigator.clipboard.writeText(content);
    console.info('已写入手机剪贴板');
  } catch (err) {
    console.warn('写入手机剪贴板失败', err);
  }
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

    <textarea
      ref="inputEl"
      :value="text"
      :style="{ height: instantMode ? '80px' : '120px' }"
      :placeholder="placeholder"
      @compositionstart="onCompositionStart"
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
