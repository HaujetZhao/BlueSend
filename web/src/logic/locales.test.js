import test from 'node:test';
import assert from 'node:assert/strict';
import zh from '../locales/zh.js';
import en from '../locales/en.js';

function keyPaths(obj, prefix = '') {
  return Object.entries(obj).flatMap(([key, value]) => {
    const path = prefix ? `${prefix}.${key}` : key;
    return value && typeof value === 'object' ? keyPaths(value, path) : [path];
  });
}

test('中英字典键集合一致', () => {
  assert.deepEqual(keyPaths(zh).sort(), keyPaths(en).sort());
});
