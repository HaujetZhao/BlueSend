import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';
import { viteSingleFile } from 'vite-plugin-singlefile';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

// 开发服务器与单文件构建共用一份配置。
// HTTPS 是 Web Bluetooth 的硬性要求：手机必须通过安全上下文打开页面。
const root = fileURLToPath(new URL('.', import.meta.url));
const https = {
  key: fs.readFileSync(path.join(root, 'certs/key.pem')),
  cert: fs.readFileSync(path.join(root, 'certs/cert.pem')),
};
const version = JSON.parse(
  fs.readFileSync(path.join(root, 'package.json'), 'utf-8'),
).version;

export default defineConfig({
  plugins: [vue(), viteSingleFile()],
  base: './',
  // 页面版本随电脑端下发的一起参与比对，来源只有 package.json 一处。
  define: { __APP_VERSION__: JSON.stringify(version) },
  resolve: {
    alias: {
      // dev 与单文件构建没有 service worker，指向桩，避免解析 PWA 虚拟模块。
      '@pwa-update': fileURLToPath(
        new URL('./src/logic/pwa-update.stub.js', import.meta.url),
      ),
    },
  },
  server: {
    host: true,
    https,
  },
});
