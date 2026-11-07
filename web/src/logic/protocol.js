export const SERVICE_UUID = '7d9f0001-3c4e-4b6a-9f2e-1a2b3c4d5e6f';
// 上行：手机写入，电脑接收。
export const UPLINK_UUID = '7d9f0002-3c4e-4b6a-9f2e-1a2b3c4d5e6f';
// 下行：电脑通知，手机接收。
export const DOWNLINK_UUID = '7d9f0003-3c4e-4b6a-9f2e-1a2b3c4d5e6f';

// 电脑每 3 秒一次心跳，三个周期没动静就判定链路已死。
export const HEARTBEAT_TIMEOUT_MS = 9000;
// 上行单片线包上限由电脑端下发：ATT 的写 PDU 与通知 PDU 都是「操作码 1＋句柄 2
// ＋值」，单片上限同为 MTU-3，所以电脑端算它下行分片的那个数就是手机的上限。
// 电脑端随订阅变化发 `mtu` 消息，手机减去自己的 4 字节序号头就是载荷。
// 消息到达之前先按 LE 的默认 ATT_MTU 23 算：20 字节在任何链路上都成立。
export const UPLINK_LIMIT_MIN = 20;
export const RECONNECT_INTERVAL_MS = 2000;
// 正常 ATT 应答不到 100 毫秒。超过这个时间还没回来，链路在实践上已经不可用，
// 不必等满 ATT 规定的 30 秒事务超时——那段时间里所有输入都会堵在写队列里。
export const WRITE_ACK_TIMEOUT_MS = 2000;
// 测速载荷大小：每次测速固定 256 KB，与 server/core/protocol.py 一致。
export const BENCH_BYTES = 256 * 1024;
