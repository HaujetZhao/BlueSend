// 语言只跟随系统（浏览器语言）：中文环境用中文，其余英文。
// 手动切换只对本次会话生效，不写入 localStorage，刷新后回到系统语言。
import { createI18n } from 'vue-i18n';
import zh from '../locales/zh.js';
import en from '../locales/en.js';

function detectLocale() {
  return navigator.languages.some((lang) => lang.toLowerCase().startsWith('zh'))
    ? 'zh'
    : 'en';
}

export const i18n = createI18n({
  legacy: false,
  locale: detectLocale(),
  fallbackLocale: 'en',
  messages: { zh, en },
});

function applyDocumentLocale() {
  const locale = i18n.global.locale.value;
  document.documentElement.lang = locale === 'zh' ? 'zh-CN' : 'en';
  document.title = i18n.global.t('app.title');
}

export function setLocale(locale) {
  i18n.global.locale.value = locale;
  applyDocumentLocale();
}

applyDocumentLocale();
