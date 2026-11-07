import {
  SERVICE_UUID,
  UPLINK_UUID,
  DOWNLINK_UUID,
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
  // 上下行两条特征值永远同时存在，用一次赋值一起拿进来，不作分别判空。
  #link = null;
  #decoder = new FrameDecoder();
  #writeChain = Promise.resolve();
  #heartbeatTimer = null;
  #reconnectTimer = null;
  #connectedAt = 0;
  #dropCount = 0;
  #reconnectFailures = 0;
  // 本轮连接是否已经对外宣布；没宣布就断的是后台重连过程中的失败。
  #announced = false;
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
      this.#onState(this.#link ? 'connected' : 'disconnected');
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
      const server = await this.#device.gatt.connect();
      const service = await server.getPrimaryService(SERVICE_UUID);
      const uplink = await service.getCharacteristic(UPLINK_UUID);
      const downlink = await service.getCharacteristic(DOWNLINK_UUID);
      if (generation !== this.#generation || this.#disposed) return;
      this.#link = { uplink, downlink };
      this.#announced = false;
      // Chrome 把订阅状态缓存在特征值对象上：电脑端重启后，startNotifications
      // 会以为自己还订阅着而直接返回，CCCD 一次都不写，Windows 端就永远收不到订阅。
      // 先取消一次，再订阅，可以逼它把 CCCD 重新写一遍。未订阅时取消会抛错，属预期。
      await downlink.stopNotifications().catch(() => {});
      await downlink.startNotifications();
      if (generation !== this.#generation || this.#disposed) return;
      downlink.addEventListener('characteristicvaluechanged', this.#onNotify);
      this.#decoder.reset();
      this.#writeChain = Promise.resolve();
      this.#noteAlive();
      this.#stopReconnect();
      this.#connectedAt = Date.now();
      // 「已连接」这条日志兼作探针：电脑端重启后 Chrome 还在用旧 GATT 句柄，
      // 这次写必然失败。写成功才对外宣布连上，写失败就静默丢弃、继续后台重连。
      const text = `已连接（第 ${this.#dropCount + 1} 段）`;
      try {
        await this.#queue(this.#link, { t: 'log', v: text }, generation);
      } catch {
        return;
      }
      if (generation !== this.#generation || this.#disposed) return;
      this.#announced = true;
      this.#emit(text);
      this.#flushPendingLogs();
      this.#onState('connected');
    } catch (err) {
      if (generation !== this.#generation || this.#disposed) return;
      console.warn('连接失败', err);
      this.#link = null;
      this.#onState('disconnected');
      throw err;
    }
  }

  send(message) {
    const link = this.#link;
    if (!link) return false;
    this.#queue(link, message, this.#generation);
    return true;
  }

  #queue(link, message, generation) {
    const frame = encodeFrame(message);
    const write = this.#writeChain.then(() =>
      this.#writeFrame(link.uplink, frame, generation),
    );
    this.#writeChain = write.catch((err) => {
      console.error('发送失败', message.t, err);
      if (generation === this.#generation) {
        this.#handleDrop('写入失败：' + err.message);
      }
    });
    return write;
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
    this.#link = null;
    this.#announced = false;
    this.#decoder.reset();
    this.#writeChain = Promise.resolve();
    device?.removeEventListener('gattserverdisconnected', this.#onDeviceDisconnect);
    device?.gatt?.disconnect();
  }

  #emit(text) {
    console.info(text);
    this.#onEvent(text);
  }

  #note(text) {
    this.#emit(text);
    if (this.#link) {
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

  async #writeFrame(uplink, frame, generation) {
    const size = uplink.maxWriteWithResponseSize || FALLBACK_WRITE_CHUNK;
    for (let i = 0; i < frame.length; i += size) {
      // 链路已经换了或断了，旧队列里的分片不再写。
      if (generation !== this.#generation) return;
      // 必须用带响应写：只有它由 ATT 保证先后顺序，无响应写会让分片乱序。
      await uplink.writeValueWithResponse(frame.subarray(i, i + size));
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
    if (this.#disposed || !this.#link) return;
    this.#generation += 1;
    const lasted = this.#connectedAt
      ? ((Date.now() - this.#connectedAt) / 1000).toFixed(1)
      : '未知';
    this.#connectedAt = 0;
    this.#dropCount += 1;
    clearTimeout(this.#heartbeatTimer);
    this.#link = null;
    this.#decoder.reset();
    this.#writeChain = Promise.resolve();
    const text = `第 ${this.#dropCount} 次断开：${reason}，上一段连接存活 ${lasted} 秒`;
    // 还没对外宣布连上就断了，说明是后台重连过程中的失败，不刷前台。
    if (this.#announced) {
      this.#announced = false;
      this.#note(text);
    } else {
      console.info(text);
    }
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
      // 被代际作废的 attempt 也会 resolve，只有真正拿到特征值才算连上。
      if (this.#link) {
        this.#reconnectFailures = 0;
      } else {
        this.#scheduleReconnect();
      }
    } catch (err) {
      this.#reconnectFailures += 1;
      // 后台重连失败不刷前台，只留控制台；每 10 次记一条避免刷屏。
      if (this.#reconnectFailures === 1 || this.#reconnectFailures % 10 === 0) {
        console.warn(`重连失败 ${this.#reconnectFailures} 次：${err.message}`);
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
    if (document.visibilityState === 'visible' && this.#device && !this.#link) {
      this.connect().catch(() => {});
    }
  };
}
