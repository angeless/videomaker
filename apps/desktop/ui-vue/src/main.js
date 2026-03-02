import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router/index.js'

import './assets/styles/variables.css'
import './assets/styles/base.css'
import './assets/styles/layout.css'
import './assets/styles/components.css'

const app = createApp(App)
app.use(createPinia())
app.use(router)
app.mount('#app')
