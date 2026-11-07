export const SERVICE_UUID = '7d9f0001-3c4e-4b6a-9f2e-1a2b3c4d5e6f';
// 上行：手机写入，电脑接收。
export const UPLINK_UUID = '7d9f0002-3c4e-4b6a-9f2e-1a2b3c4d5e6f';
// 下行：电脑通知，手机接收。
export const DOWNLINK_UUID = '7d9f0003-3c4e-4b6a-9f2e-1a2b3c4d5e6f';

// 电脑每 3 秒一次心跳，三个周期没动静就判定链路已死。
export const HEARTBEAT_TIMEOUT_MS = 9000;
// 上行单包上限。Chrome 没有暴露 maxWriteWithResponseSize（原型上根本没有这个
// 成员），所以这里永远是实际生效的值。实测 Chrome 硬性拒绝超过 512 字节的写
// （514 报 InvalidModificationError），而 512 稳定通过——链路的 MTU 是 517。
export const WRITE_CHUNK = 512;
export const RECONNECT_INTERVAL_MS = 2000;
// 正常 ATT 应答不到 100 毫秒。超过这个时间还没回来，链路在实践上已经不可用，
// 不必等满 ATT 规定的 30 秒事务超时——那段时间里所有输入都会堵在写队列里。
export const WRITE_ACK_TIMEOUT_MS = 2000;
// 测速载荷大小：每次测速固定 256 KB，与 pc/bluetooth_input/protocol.py 一致。
export const BENCH_BYTES = 256 * 1024;
