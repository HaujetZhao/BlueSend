import { createApp } from 'vue';
import App from './App.vue';
import { i18n } from './logic/i18n.js';
import './styles.css';

createApp(App).use(i18n).mount('#app');
