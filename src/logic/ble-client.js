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
