export const SERVICE_UUID = '7d9f0001-3c4e-4b6a-9f2e-1a2b3c4d5e6f';
export const CHAR_UUID = '7d9f0002-3c4e-4b6a-9f2e-1a2b3c4d5e6f';

// 电脑每 3 秒一次心跳，三个周期没动静就判定链路已死。
export const HEARTBEAT_TIMEOUT_MS = 9000;
// 拿不到协商后的写入上限时使用，覆盖 4.2 默认 MTU。
export const FALLBACK_WRITE_CHUNK = 180;
export const RECONNECT_INTERVAL_MS = 2000;
