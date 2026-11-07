// 帧格式：[4 字节大端长度][UTF-8 JSON]，与 pc/frame_codec.py 对齐。
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

  reset() {
    this.#buffer = new Uint8Array(0);
  }
}
