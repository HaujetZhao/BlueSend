import { ref, computed, onUnmounted } from 'vue';
import { BleClient } from '../logic/ble-client.js';

export function useBle({ onClipboard, onBench, onReceiveProgress, onNet }) {
  const status = ref('disconnected');
  // 空串表示还没有任何事件，界面用当前语言的「尚未连接」占位。
  const lastEvent = ref('');
  // 需要打断操作的持久警告（如协议不兼容）。普通事件会不断覆盖事件行，
  // 这类提示用 modal 呈现，不能只写一行字。
  const warning = ref('');

  const connected = computed(() => status.value === 'connected');

  const client = new BleClient({
    onState: (state) => {
      status.value = state;
    },
    onEvent: (text) => {
      lastEvent.value = text;
    },
    onWarning: (text) => {
      warning.value = text;
    },
    onClipboard,
    onBench,
    onReceiveProgress,
    onNet,
  });

  onUnmounted(() => client.dispose());

  return {
    status,
    lastEvent,
    warning,
    connected,
    connect: () => client.requestDevice(),
    send: (message) => client.send(message),
    sendAsync: (message, onProgress) => client.sendAsync(message, onProgress),
    uplinkChunkSize: () => client.uplinkChunkSize,
    note: (text) => client.note(text),
  };
}
