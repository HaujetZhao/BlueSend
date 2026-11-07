// 上下行测速的载荷与结果格式。载荷两端各自生成，内容没有业务含义。
import { BENCH_BYTES } from './protocol.js';

// 重复的可打印 ASCII：JSON 编码不产生转义，字符数与字节数一致，测量口径可预测。
const PATTERN = '0123456789abcdef';

// 两条测速消息共用同一份载荷，模块加载时建一次。
export const BENCH_PAYLOAD = PATTERN.repeat(BENCH_BYTES / PATTERN.length);

// bytes 与 ms 都由发送方计时得到；chunk 是发送时实际使用的单包大小。
export function describeBench(direction, { bytes, ms, chunk }) {
  const seconds = ms / 1000;
  const rate = bytes / seconds / 1024;
  return `${direction} ${bytes / 1024} KB / ${seconds.toFixed(1)} 秒 = ${rate.toFixed(1)} KB/s（单包 ${chunk} B）`;
}
