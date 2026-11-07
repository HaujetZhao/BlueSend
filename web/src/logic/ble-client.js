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
  #connecting = null;
  #generation = 0;
  #disposed = false;

  constructor({ onState, onEvent, onClipboard }) {
    this.#onState = onState;
    this.#onEvent = onEvent;
    this.#onClipboard = onClipboard;
    document.addEventListener('visibilitychange', this.#onVisibilityChange);
  }

  note(text) {
    this.#note(text);
  }

  async requestDevice() {
    this.#stopReconnect();
    this.#onState('connecting');
    try {
      const device = await navigator.bluetooth.requestDevice({
        filters: [{ services: [SERVICE_UUID] }],
        optionalServices: [SERVICE_UUID],
      });
      this.#teardownLink();
      this.#device = device;
      device.addEventListener('gattserverdisconnected', this.#onDeviceDisconnect);
      await this.connect();
    } catch (err) {
      console.warn('选择设备失败', err);
      // 取消选择时旧链路还活着，恢复到已连接状态。
      this.#onState(this.#characteristic ? 'connected' : 'disconnected');
    }
  }

  connect() {
    if (this.#connecting) return this.#connecting;
    const attempt = this.#doConnect();
    const tracked = attempt.finally(() => {
      if (this.#connecting === tracked) this.#connecting = null;
    });
    this.#connecting = tracked;
    return tracked;
  }

  async #doConnect() {
    const generation = this.#generation;
    try {
      this.#onState('connecting');
      const server = await this.#device.gatt.connect();
      const service = await server.getPrimaryService(SERVICE_UUID);
      const characteristic = await service.getCharacteristic(CHAR_UUID);
      if (generation !== this.#generation || this.#disposed) return;
      this.#characteristic = characteristic;
      await characteristic.startNotifications();
      if (generation !== this.#generation || this.#disposed) return;
      characteristic.addEventListener('characteristicvaluechanged', this.#onNotify);
      this.#decoder.reset();
      this.#writeChain = Promise.resolve();
      this.#noteAlive();
      this.#stopReconnect();
      this.#connectedAt = Date.now();
      this.#note(`已连接（第 ${this.#dropCount + 1} 段）`);
      this.#flushPendingLogs();
      this.#onState('connected');
    } catch (err) {
      if (generation !== this.#generation || this.#disposed) return;
      console.warn('连接失败', err);
      this.#characteristic = null;
      this.#onState('disconnected');
      throw err;
    }
  }

  send(message) {
    const characteristic = this.#characteristic;
    if (!characteristic) return false;
    const generation = this.#generation;
    const frame = encodeFrame(message);
    this.#writeChain = this.#writeChain
      .then(() => this.#writeFrame(characteristic, frame, generation))
      .catch((err) => {
        console.error('发送失败', message.t, err);
        if (generation === this.#generation) {
          this.#handleDrop('写入失败：' + err.message);
        }
      });
    return true;
  }

  dispose() {
    this.#disposed = true;
    document.removeEventListener('visibilitychange', this.#onVisibilityChange);
    this.#stopReconnect();
    this.#teardownLink();
  }

  #teardownLink() {
    this.#generation += 1;
    this.#connecting = null;
    clearTimeout(this.#heartbeatTimer);
    this.#heartbeatTimer = null;
    const device = this.#device;
    this.#device = null;
    this.#characteristic = null;
    this.#decoder.reset();
    this.#writeChain = Promise.resolve();
    device?.removeEventListener('gattserverdisconnected', this.#onDeviceDisconnect);
    device?.gatt?.disconnect();
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

  async #writeFrame(characteristic, frame, generation) {
    const size = characteristic.maxWriteWithResponseSize || FALLBACK_WRITE_CHUNK;
    for (let i = 0; i < frame.length; i += size) {
      // 链路已经换了或断了，旧队列里的分片不再写。
      if (generation !== this.#generation) return;
      // 有响应写由 ATT 保证先后顺序，这正是无响应写分片乱序的根源。
      await characteristic.writeValueWithResponse(frame.subarray(i, i + size));
    }
  }

  #onDeviceDisconnect = () => this.#handleDrop('物理断开');

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
    this.#generation += 1;
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
    this.#reconnectTimer = setTimeout(() => {
      this.#reconnectTimer = null;
      this.#attemptReconnect();
    }, RECONNECT_INTERVAL_MS);
  }

  async #attemptReconnect() {
    if (!this.#device) return;
    try {
      await this.connect();
      // 被代际作废的 attempt 也会 resolve，只有真正拿到 characteristic 才算连上。
      if (this.#characteristic) {
        this.#reconnectFailures = 0;
      } else {
        this.#scheduleReconnect();
      }
    } catch (err) {
      this.#reconnectFailures += 1;
      // 每 2 秒试一次，全记会刷屏，只记第一次和之后每 10 次。
      if (this.#reconnectFailures === 1 || this.#reconnectFailures % 10 === 0) {
        this.#note(`重连失败 ${this.#reconnectFailures} 次：${err.message}`);
      }
      this.#scheduleReconnect();
    }
  }

  #stopReconnect() {
    clearTimeout(this.#reconnectTimer);
    this.#reconnectTimer = null;
  }

  #onVisibilityChange = () => {
    // 页面回到前台时蓝牙可能已经被系统掐掉，主动检查一次。
    if (document.visibilityState === 'visible' && this.#device && !this.#characteristic) {
      this.connect().catch(() => {});
    }
  };
}
