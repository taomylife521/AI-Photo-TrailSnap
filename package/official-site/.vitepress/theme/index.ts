/// <reference types="vitepress/client" />
import DefaultTheme from 'vitepress/theme'
import { h } from 'vue'
import { useData } from 'vitepress'
import Comments from './components/Comments.vue'
import Home from './components/Home.vue'
import TicketRecognitionDemo from './components/TicketRecognitionDemo.vue'
import TicketRecognitionTryIt from './components/TicketRecognitionTryIt.vue'
import './style.css'
import {Mermaid} from "@leelaa/vitepress-plugin-extended";
import { enhanceAppWithTabs } from 'vitepress-plugin-tabs/client'

export default {
  extends: DefaultTheme,
  Layout() {
    const { frontmatter } = useData()
    return h(DefaultTheme.Layout, null, {
      // Hide comments on the custom home page
      'doc-after': () => frontmatter.value.home_custom ? null : h(Comments)
    })
  },
  enhanceApp({ app }: { app: any }) {
    app.component('Home', Home)
    app.component('TicketRecognitionDemo', TicketRecognitionDemo)
    app.component('TicketRecognitionTryIt', TicketRecognitionTryIt)
    app.component("Mermaid", Mermaid);
    enhanceAppWithTabs(app)
  }
}
