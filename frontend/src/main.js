import { createApp } from 'vue'
import TDesign from 'tdesign-vue-next'
import 'tdesign-vue-next/es/style/index.css'
import './styles.css'
import { initTheme } from './theme'
import { initI18n } from './i18n'
import App from './App.vue'
import router from './router'

initTheme()
initI18n()
createApp(App).use(TDesign).use(router).mount('#app')
