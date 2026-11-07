import test from 'node:test';
import assert from 'node:assert/strict';
import { describeBench, sha256Hex } from './bench.js';

test('sha256 与标准向量一致', async () => {
  assert.equal(
    await sha256Hex('abc'),
    'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad',
  );
});

test('两片互换后哈希就变了', async () => {
  // 内容全部是 ASCII，长度一样，JSON 照样解析得通——只有哈希能发现。
  const original = '0123456789abcdef';
  const swapped = '0123456789bacdef';
  assert.notEqual(await sha256Hex(original), await sha256Hex(swapped));
});

test('结果行含速率与单包大小', () => {
  assert.equal(
    describeBench('下行', { bytes: 262144, ms: 3300, chunk: 512 }),
    '下行 256 KB / 3.3 秒 = 77.6 KB/s（单包 512 B）',
  );
});
