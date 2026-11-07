import { useRegisterSW } from 'virtual:pwa-register/vue';

export const { needRefresh, updateServiceWorker } = useRegisterSW();
