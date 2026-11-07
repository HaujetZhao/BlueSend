// 非 PWA 构建（dev、单文件）没有 service worker，更新提示恒为空。
import { ref } from 'vue';

export const needRefresh = ref(false);
export function updateServiceWorker() {}
