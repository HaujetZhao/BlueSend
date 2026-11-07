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

export default defineConfig({
  plugins: [vue(), viteSingleFile()],
  base: './',
  server: {
    host: true,
    https,
  },
});
