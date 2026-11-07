import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';
import { VitePWA } from 'vite-plugin-pwa';

// PWA 构建配置：用于 GitHub Pages 在线版。
// 与 vite.config.js（单文件构建，给本地 HTTPS 托管）分开，
// 因为 service worker 和 manifest 必须是独立外链文件，无法内联进单 HTML。
export default defineConfig({
  plugins: [
    vue(),
    VitePWA({
      // prompt 而非 autoUpdate：新版只在后台预缓存，不强制刷新页面。
      registerType: 'prompt',
      manifest: {
        lang: 'zh-CN',
        name: '手机 ↔ 电脑 蓝牙通道',
        short_name: '蓝牙输入',
        description: '通过 BLE 用手机给电脑打字、同步剪贴板。',
        theme_color: '#0f0f13',
        background_color: '#0f0f13',
        display: 'standalone',
        start_url: './',
        icons: [
          { src: 'icon-192.png', sizes: '192x192', type: 'image/png', purpose: 'any maskable' },
          { src: 'icon-512.png', sizes: '512x512', type: 'image/png', purpose: 'any maskable' },
        ],
      },
      workbox: {
        globPatterns: ['**/*.{js,css,html,svg,png,json}'],
      },
    }),
  ],
  base: './',
});
