import { ref, computed, onUnmounted } from 'vue';
import { BleClient } from '../logic/ble-client.js';

export function useBle({ onClipboard, onBench, onReceiveProgress }) {
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
    onBench,
    onReceiveProgress,
  });

  onUnmounted(() => client.dispose());

  return {
    status,
    lastEvent,
    connected,
    connect: () => client.requestDevice(),
    send: (message) => client.send(message),
    sendAsync: (message) => client.sendAsync(message),
    uplinkChunkSize: () => client.uplinkChunkSize,
    note: (text) => client.note(text),
  };
}
