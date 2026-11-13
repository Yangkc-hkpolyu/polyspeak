import Vue from 'vue'
import SpeakingApp from './speaking/SpeakingApp.vue'
import './speaking/speaking.css'
import './speaking/focus.css'
Vue.config.productionTip = false
new Vue({ render: h => h(SpeakingApp) }).$mount('#app')
