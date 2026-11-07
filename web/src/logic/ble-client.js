import {
  SERVICE_UUID,
  UPLINK_UUID,
  DOWNLINK_UUID,
  HEARTBEAT_TIMEOUT_MS,
  UPLINK_LIMIT_MIN,
  RECONNECT_INTERVAL_MS,
  WRITE_ACK_TIMEOUT_MS,
} from './protocol.js';
import { encodeFrame, FrameDecoder } from './frame-codec.js';

// 写入的 Promise 可能一直挂着（带响应写等不到应答、无响应写在缓冲满时排队），
// 所以加一道上限；超时后调用方会主动断开链路。超时值可按消息大小放宽。
function writeWithTimeout(write, timeoutMs = WRITE_ACK_TIMEOUT_MS) {
  let timer;
  const timeout = new Promise((_, reject) => {
    timer = setTimeout(
      () => reject(new Error(`等待写入完成超过 ${timeoutMs} 毫秒`)),
      timeoutMs,
    );
  });
  return Promise.race([write, timeout]).finally(() => clearTimeout(timer));
}

// 空中排空实测约 8 毫秒一片（512 B ≈ 63 KB/s）。最后一片的应答要等前面的
// 片在空中排空，超时按片数放宽，余量 3 倍。
const DRAIN_MS_PER_CHUNK = 25;

// 重连可能无限进行（见坑 11），积压不设上限会一直吃内存；溢出时丢最旧的，
// 保住用户最近打的字。这些消息还没交给写链，不属于坑 12 禁止的应用层重传。
const OUTBOX_LIMIT = 100;

export class BleClient {
  #onState;
  #onEvent;
  #onClipboard;
  #onBench;
  #onReceiveProgress;
  #onNet;

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
  // 电脑端看不到的断开原因（心跳超时、写入失败、解析失败）：断开时链路已经
  // 没了，先攒着，重连宣布后补发。
  #pendingLogs = [];
  // 重连期间还没能交给写链的消息；本轮重新宣布连接后整批补发。
  #outbox = [];
  // 本轮重连是否已经提示过积压溢出，提示一次就够，免得刷掉真正的连接状态。
  #outboxOverflowNotified = false;
  #connecting = null;
  // 上行分片序号：连接作用域的连续计数。不能每条消息从 0 数——电脑端重组器
  // 跨消息只进不退，重新从 0 计数会被当成重复片全部丢弃。
  #uplinkSeq = 0;
  // 上行单片线包上限：电脑端按协商出的 MTU 下发（mtu 消息），同样是连接作用域。
  // 收到之前用 ATT 最小 MTU 推出来的 20，任何链路上都写得出去。
  #uplinkLimit = UPLINK_LIMIT_MIN;
  #generation = 0;
  #disposed = false;
  // 刚收到的下行测速载荷，留着给随后的 benchend 做内容校验。
  #benchPayload = '';

  constructor({ onState, onEvent, onClipboard, onBench, onReceiveProgress, onNet }) {
    this.#onState = onState;
    this.#onEvent = onEvent;
    this.#onClipboard = onClipboard;
    this.#onBench = onBench;
    this.#onReceiveProgress = onReceiveProgress;
    this.#onNet = onNet;
    document.addEventListener('visibilitychange', this.#onVisibilityChange);
  }

  // 只刷手机端的事件行。业务日志不再镜像到电脑端——那边对同一件事已有自己的
  // 记录（`收到剪贴板推送 46 字`），镜像过去只是重复。连接探针与断开诊断另有
  // 通路，见 #doConnect 与 #handleDrop。
  note(text) {
    this.#emit(text);
  }

  // 上行实际使用的单包大小，测速时随结果一起上报。
  get uplinkChunkSize() {
    return this.#uplinkLimit;
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
      this.#onState(this.#announced ? 'connected' : 'disconnected');
      // 入口处的 #stopReconnect() 让旧设备的后台重连停了；选择器取消或
      // 连接失败后没有新链路接手，这里必须重新调度，否则再也连不回来。
      if (this.#device && !this.#link) this.#scheduleReconnect();
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
      this.#uplinkSeq = 0;
      this.#uplinkLimit = UPLINK_LIMIT_MIN;
      this.#noteAlive();
      this.#stopReconnect();
      this.#connectedAt = Date.now();
      // 「已连接」这条日志兼作探针：电脑端重启后 Chrome 还在用旧 GATT 句柄，
      // 这次写必然失败。写成功才对外宣布连上，写失败就静默丢弃、继续后台重连。
      // 探针与状态栏用同一句话，电脑端日志和手机事件行能直接对照。
      const text = `已连接（第 ${this.#dropCount + 1} 次）`;
      try {
        await this.#queue(this.#link, { t: 'log', v: text }, generation);
      } catch {
        return;
      }
      if (generation !== this.#generation || this.#disposed) return;
      this.#announced = true;
      this.#emit(text);
      this.#flushPendingLogs();
      this.#flushOutbox();
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
    // 从未选过设备，无处可发，调用方（如拉取剪贴板）需要知道失败。
    if (!this.#device) return false;
    // 后台重连中，或探针写还没成功：链路尚不可信，先攒着，等本轮宣布后补发。
    if (!this.#announced) {
      this.#outbox.push(message);
      if (this.#outbox.length > OUTBOX_LIMIT) {
        const dropped = this.#outbox.shift();
        console.warn('重连期间积压消息过多，丢弃最早的一条', dropped);
        if (!this.#outboxOverflowNotified) {
          this.#outboxOverflowNotified = true;
          this.#emit('重连期间积压消息过多，最早的一条已丢弃');
        }
      }
      return true;
    }
    this.#queue(this.#link, message, this.#generation);
    return true;
  }

  // 只在已宣布连接时使用：返回的 Promise 在最后一片收到 ATT 应答后 resolve。
  // 测速用它把「整条消息写完」的耗时框出来；onProgress 每写完一片调一次。
  sendAsync(message, onProgress) {
    return this.#queue(this.#link, message, this.#generation, onProgress).then((written) => {
      // 断线时队列里的帧会被静默跳过，测速不能把「没发出去」算成「发得很快」。
      if (!written) throw new Error('链路已切换，本帧作废');
    });
  }

  // 本轮重连已经宣布，按顺序把积压交给写链。若写链随后失败，代际作废会让
  // 剩余消息自然不再写出，按坑 12 的语义丢弃，不做应用层重试。
  #flushOutbox() {
    const link = this.#link;
    const generation = this.#generation;
    const messages = this.#outbox.splice(0);
    this.#outboxOverflowNotified = false;
    for (const message of messages) {
      this.#queue(link, message, generation);
    }
  }

  #queue(link, message, generation, onProgress) {
    const frame = encodeFrame(message);
    const write = this.#writeChain.then(() =>
      this.#writeFrame(link.uplink, frame, generation, onProgress),
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
    // 上传入口是连接作用域的，旧链路的地址不能带进下一次连接。
    this.#onNet([]);
    // 换了设备（或销毁）时，旧设备积压的消息不该发给新设备。
    // dispose() 走的就是这里，不必再清一遍。
    this.#outbox.length = 0;
    this.#outboxOverflowNotified = false;
    this.#decoder.reset();
    this.#writeChain = Promise.resolve();
    this.#uplinkSeq = 0;
    this.#uplinkLimit = UPLINK_LIMIT_MIN;
    device?.removeEventListener('gattserverdisconnected', this.#onDeviceDisconnect);
    device?.gatt?.disconnect();
  }

  #emit(text) {
    console.info(text);
    this.#onEvent(text);
  }

  #flushPendingLogs() {
    for (const text of this.#pendingLogs.splice(0)) {
      this.send({ t: 'log', v: text });
    }
  }

  async #writeFrame(uplink, frame, generation, onProgress) {
    // 每片 4 字节大端序号前缀：电脑端写回调跑在线程池上，并发投递的字节顺序
    // 会颠倒（实测 517 片三轮坏一次），接收端按序号重排。载荷 = 线包上限 - 4。
    const size = this.#uplinkLimit - 4;
    const chunks = Math.ceil(frame.length / size);
    // 序号取连接作用域的连续计数，跨消息不归零（见字段注释）。
    const seqBase = this.#uplinkSeq;
    this.#uplinkSeq += chunks;
    // 最后一片的应答要等前面所有分片在空中排空（实测约 8 毫秒一片），超时按
    // 片数放宽，余量 3 倍。固定 2 秒会把大消息的收尾误杀成断链。
    const timeoutMs = WRITE_ACK_TIMEOUT_MS + DRAIN_MS_PER_CHUNK * chunks;
    for (let i = 0, seq = seqBase; i < frame.length; i += size, seq += 1) {
      // 链路已经换了或断了，旧队列里的分片不再写。返回值告诉 sendAsync 这一帧作废。
      if (generation !== this.#generation) return false;
      const body = frame.subarray(i, i + size);
      const last = i + size >= frame.length;
      const chunk = new Uint8Array(4 + body.length);
      new DataView(chunk.buffer).setUint32(0, seq, false);
      chunk.set(body, 4);
      // 中间片用无响应写连续入队，不等应答（停等只有 8 KB/s，这样约 63 KB/s）；
      // 最后一片用带响应写——它的应答到达时前面的片必然已排空，一次拿到整条
      // 消息的送达确认、下一条消息的排队栅栏和测速的真实终点。
      await writeWithTimeout(
        last
          ? uplink.writeValueWithResponse(chunk)
          : uplink.writeValueWithoutResponse(chunk),
        timeoutMs,
      );
      onProgress?.(Math.min(i + size, frame.length), frame.length);
    }
    return true;
  }

  #onDeviceDisconnect = () => this.#handleDrop('物理断开');

  #onNotify = (event) => {
    // 断线前排队的回调可能在重连成功后才执行。只认当前链路的特征值，
    // 否则旧链路的字节会被灌进新链路的解码器，把帧边界带偏。
    if (event.target !== this.#link?.downlink) return;
    // 收到字节就说明链路活着。不能等整条消息拼齐才喂狗：一条 256 KB 的测速
    // 消息要十几秒才凑满，那期间心跳也发不出来（一帧的字节流必须原子发送）。
    this.#noteAlive();
    const view = event.target.value;
    const chunk = new Uint8Array(view.buffer, view.byteOffset, view.byteLength);
    try {
      for (const message of this.#decoder.push(chunk)) {
        this.#dispatch(message);
      }
    } catch (err) {
      // 字节流已经和帧格式对不上，继续解析只会越错越远；
      // 断开重连，让两端从干净状态开始。
      console.error('接收数据解析失败', err);
      this.#handleDrop('接收数据解析失败');
      return;
    }
    // 帧被取走后缓冲里剩下的就是半帧，进度只看它。null 表示这一帧已经收完。
    this.#onReceiveProgress(this.#decoder.progress());
  };

  #dispatch(message) {
    console.debug('收到', message.t);
    switch (message.t) {
      case 'hb':
      case 'pong':
        break;
      case 'mtu':
        // 电脑端按协商出的 MTU 算的单片上限，连接边界会复位成 ATT 最小值。
        this.#uplinkLimit = message.up;
        break;
      case 'net':
        // 电脑托管的文件上传入口。连接作用域，断开时清空。
        this.#onNet(message.hosts);
        break;
      case 'benchdata':
        // 载荷没有业务含义，但要留着：benchend 到达时拿它重算哈希，验分片顺序。
        this.#benchPayload = message.v;
        break;
      case 'clip':
        this.#onClipboard(message.v);
        break;
      case 'notice':
        this.#emit(message.v);
        break;
      case 'benchend':
        this.#onBench({
          bytes: message.bytes,
          chunk: message.chunk,
          sha256: message.sha256,
          payload: this.#benchPayload,
        });
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
    this.#onNet([]);
    this.#decoder.reset();
    this.#writeChain = Promise.resolve();
    this.#uplinkSeq = 0;
    this.#uplinkLimit = UPLINK_LIMIT_MIN;
    // 写失败或心跳超时不代表链路已经断了。主动断开，电脑端才能看到会话结束、
    // 清掉它那边的半帧缓冲；否则重连会继续用一条已经失步的流。
    if (this.#device?.gatt?.connected) this.#device.gatt.disconnect();
    const logText = `第 ${this.#dropCount} 次断开：${reason}，上次连接存活 ${lasted} 秒`;
    console.info(logText);
    // 还没对外宣布连上就断了，说明是后台重连过程中的失败，不刷前台。
    if (this.#announced) {
      this.#announced = false;
      this.#emit('连接已断开，正在自动重连…');
      // 物理断开电脑端自己就能看到（订阅清零 + 链路状态：已断开），不必再发；
      // 另外三种原因只有手机知道，攒到重连后补发。
      if (reason !== '物理断开') this.#pendingLogs.push(logText);
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
