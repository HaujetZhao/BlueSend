import test from 'node:test';
import assert from 'node:assert/strict';
import { encodeFrame, FrameDecoder } from './frame-codec.js';

test('单帧编解码往返', () => {
  const frame = encodeFrame({ t: 'text', v: '你好' });
  assert.deepEqual(new FrameDecoder().push(frame), [{ t: 'text', v: '你好' }]);
});

test('一帧分多次推送', () => {
  const frame = encodeFrame({ t: 'clip', v: '分片' });
  const decoder = new FrameDecoder();
  assert.deepEqual(decoder.push(frame.subarray(0, 3)), []);
  assert.deepEqual(decoder.push(frame.subarray(3, 6)), []);
  assert.deepEqual(decoder.push(frame.subarray(6)), [{ t: 'clip', v: '分片' }]);
});

test('一次推送含多帧', () => {
  const first = encodeFrame({ t: 'hb' });
  const second = encodeFrame({ t: 'pong' });
  const merged = new Uint8Array(first.length + second.length);
  merged.set(first);
  merged.set(second, first.length);
  assert.deepEqual(new FrameDecoder().push(merged), [{ t: 'hb' }, { t: 'pong' }]);
});

test('中文按 UTF-8 字节计长度', () => {
  const payload = { t: 'text', v: '中文🙂' };
  const frame = encodeFrame(payload);
  assert.equal(frame.length, 4 + new TextEncoder().encode(JSON.stringify(payload)).length);
  assert.deepEqual(new FrameDecoder().push(frame), [payload]);
});

test('空对象', () => {
  assert.deepEqual(new FrameDecoder().push(encodeFrame({})), [{}]);
});
