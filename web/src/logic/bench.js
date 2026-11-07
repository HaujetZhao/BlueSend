// 上下行测速的载荷与结果格式。载荷两端各自生成，内容没有业务含义。
import { BENCH_BYTES } from './protocol.js';

// 上行载荷：重复的可打印 ASCII，JSON 编码不产生转义，字符数与字节数一致。
// 下行载荷由电脑端每次随机生成，并附带 SHA-256 供手机校验。
const PATTERN = '0123456789abcdef';

// 上行测速用这一份；模块加载时建一次。
export const BENCH_PAYLOAD = PATTERN.repeat(BENCH_BYTES / PATTERN.length);

// bytes 与 ms 都由发送方计时得到；chunk 是发送时实际使用的单包大小。
export function describeBench(direction, { bytes, ms, chunk }) {
  const seconds = ms / 1000;
  const rate = bytes / seconds / 1024;
  return `${direction} ${bytes / 1024} KB / ${seconds.toFixed(1)} 秒 = ${rate.toFixed(1)} KB/s（单包 ${chunk} B）`;
}

// 下行内容校验：拿收到的载荷重算 SHA-256，与电脑端随 benchend 带上来的值比对。
// 载荷是 ASCII，分片被调换或重复时帧照样解析成合法 JSON、长度也照样对得上，
// 只有内容哈希能把这种错暴露出来。
export async function sha256Hex(text) {
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text));
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, '0')).join('');
}
