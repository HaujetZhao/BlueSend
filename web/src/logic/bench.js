// 上下行测速的载荷与结果格式。载荷随机生成，内容没有业务含义。
import { BENCH_BYTES } from './protocol.js';

// 每次随机生成 base64 载荷，两个方向都用：固定模式换两片之后仍是合法 JSON、
// 长度也对，只有内容哈希能验出分片被调换或重复。base64 是纯 ASCII，JSON 编码
// 不产生转义，字符数即字节数；262144 能被 3 整除，编码不带补位符。
export function randomBenchPayload() {
  const bytes = new Uint8Array((BENCH_BYTES / 4) * 3);
  for (let i = 0; i < bytes.length; i += 65536) {
    crypto.getRandomValues(bytes.subarray(i, i + 65536));
  }
  let binary = '';
  for (let i = 0; i < bytes.length; i += 8192) {
    binary += String.fromCharCode(...bytes.subarray(i, i + 8192));
  }
  return btoa(binary);
}

// 内容校验：拿收到的载荷重算 SHA-256，与发送方随消息带上的值比对。
export async function sha256Hex(text) {
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text));
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, '0')).join('');
}
