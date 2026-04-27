/// <reference types="vitepress/client" />
import DefaultTheme from 'vitepress/theme'
import { h } from 'vue'
import Comments from './components/Comments.vue'
import Home from './components/Home.vue'
import TicketRecognitionDemo from './components/TicketRecognitionDemo.vue'
import TicketRecognitionTryIt from './components/TicketRecognitionTryIt.vue'
import './style.css'
import {Mermaid} from "@leelaa/vitepress-plugin-extended";
import { enhanceAppWithTabs } from 'vitepress-plugin-tabs/client'

import { useData, inBrowser } from 'vitepress'
import { useRouter } from 'vitepress/client'
import NProgress from 'nprogress'
import 'nprogress/nprogress.css'

NProgress.configure({
  showSpinner: false,
  speed: 300,
  minimum: 0.2
})

export default {
  extends: DefaultTheme,

  Layout() {
    const { frontmatter } = useData()

    // VitePress 2.0 正确路由监听
    if (inBrowser) {
      const router = useRouter()
      router.onBeforeRouteChange = () => {
        NProgress.start()
      }
      router.onAfterRouteChange = () => {
        NProgress.done()
      }
    }

    return h(DefaultTheme.Layout, null, {
      'doc-after': () => frontmatter.value.home_custom ? null : h(Comments)
    })
  },

  enhanceApp({ app, router }: { app: any; router: any }) {
    // 全局组件
    app.component('Home', Home)
    app.component('TicketRecognitionDemo', TicketRecognitionDemo)
    app.component('TicketRecognitionTryIt', TicketRecognitionTryIt)
    app.component('Mermaid', Mermaid)
    enhanceAppWithTabs(app)
  }
}