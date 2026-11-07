// 帧格式：[4 字节大端长度][UTF-8 JSON]，与 server/core/frame_codec.py 对齐。
export function encodeFrame(message) {
  const body = new TextEncoder().encode(JSON.stringify(message));
  const frame = new Uint8Array(4 + body.length);
  new DataView(frame.buffer).setUint32(0, body.length, false);
  frame.set(body, 4);
  return frame;
}

export class FrameDecoder {
  #buffer = new Uint8Array(0);

  push(chunk) {
    const merged = new Uint8Array(this.#buffer.length + chunk.length);
    merged.set(this.#buffer);
    merged.set(chunk, this.#buffer.length);
    this.#buffer = merged;

    const messages = [];
    for (;;) {
      if (this.#buffer.length < 4) break;
      const length = new DataView(
        this.#buffer.buffer,
        this.#buffer.byteOffset,
        4,
      ).getUint32(0, false);
      if (this.#buffer.length < 4 + length) break;
      const body = new TextDecoder().decode(this.#buffer.subarray(4, 4 + length));
      this.#buffer = this.#buffer.slice(4 + length);
      messages.push(JSON.parse(body));
    }
    return messages;
  }

  // 当前正在拼的这一帧已收多少字节、总共多少字节；没有半帧时返回 null。
  // 测速时用它显示下行进度——长度前缀就在帧头，接收方不用等帧拼完再问。
  progress() {
    if (this.#buffer.length < 4) return null;
    const length = new DataView(
      this.#buffer.buffer,
      this.#buffer.byteOffset,
      4,
    ).getUint32(0, false);
    return { received: this.#buffer.length, total: 4 + length };
  }

  reset() {
    this.#buffer = new Uint8Array(0);
  }
}
