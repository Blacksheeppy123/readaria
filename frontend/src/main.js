import { createApp } from 'vue'
import { createPinia } from 'pinia'
import * as Sentry from '@sentry/vue'
import posthog from 'posthog-js'
import router from './router'
import i18n from './i18n'
import App from './App.vue'
import { useUserStore } from './stores/userStore'
import { initPostHog } from './utils/analytics'
import './style.css'

// PWA注册
import { registerSW } from 'virtual:pwa-register'

// Vant样式和组件
import 'vant/lib/index.css'
import {
  Tabbar,
  TabbarItem,
  NavBar,
  Card,
  Button,
  Empty,
  ActionSheet,
  Form,
  Field,
  Toast,
  showToast,
  Dialog,
  PullRefresh,
  List,
  Cell,
  CellGroup,
  Skeleton,
  Tag,
  Search,
  Icon,
  Loading,
  ShareSheet,
  Divider,
  Collapse,
  CollapseItem,
  Checkbox,
  Progress,
  Slider,
  Tabs,
  Tab,
  SwipeCell,
  Popup,
  Switch
} from 'vant'
import { Space } from 'vant'

console.log('Main.js loading...')

// 注册 Service Worker
const updateSW = registerSW({
  onNeedRefresh() {
    console.log('New content available, please refresh.')
    showToast({
      message: i18n.global.t('pwa.newVersion'),
      duration: 2000
    })
  },
  onOfflineReady() {
    console.log('App ready to work offline')
    showToast({
      message: i18n.global.t('pwa.offlineReady'),
      duration: 2000
    })
  },
  onRegistered(registration) {
    console.log('Service Worker registered:', registration)
  },
  onRegisterError(error) {
    console.error('Service Worker registration failed:', error)
  }
})

const app = createApp(App)

// ---- Sentry 错误追踪初始化 ----
const sentryDsn = import.meta.env.VITE_SENTRY_DSN
if (sentryDsn && sentryDsn !== 'https://xxx@xxx.ingest.sentry.io/xxx') {
  Sentry.init({
    app,
    dsn: sentryDsn,
    environment: 'production',
    release: import.meta.env.VITE_GIT_SHA,
    tracesSampleRate: 0.1,
    tracePropagationTargets: ['localhost', /^https:\/\/api\.marlinworks\.xyz/],
  })
  console.log('[Sentry] 错误追踪已启用')
}

// ---- PostHog 产品分析初始化 ----
const posthogKey = import.meta.env.VITE_POSTHOG_KEY
const cookieConsent = localStorage.getItem('readaria_cookie_consent')
if (import.meta.env.PROD && posthogKey && cookieConsent === 'accepted') {
  initPostHog(posthogKey)
}

const pinia = createPinia()

// 注册Vant组件
app.use(Tabbar)
app.use(TabbarItem)
app.use(NavBar)
app.use(Card)
app.use(Button)
app.use(Empty)
app.use(ActionSheet)
app.use(Form)
app.use(Field)
app.use(Toast)
app.use(Dialog)
app.use(PullRefresh)
app.use(List)
app.use(Cell)
app.use(CellGroup)
app.use(Skeleton)
app.use(Tag)
app.use(Search)
app.use(Icon)
app.use(Loading)
app.use(ShareSheet)
app.use(Divider)
app.use(Space)
app.use(Collapse)
app.use(CollapseItem)
app.use(Checkbox)
app.use(Progress)
app.use(Slider)
app.use(Tabs)
app.use(Tab)
app.use(SwipeCell)
app.use(Popup)
app.use(Switch)

app.use(pinia)
app.use(router)
app.use(i18n)

// ==================== TTS 缓存自动清理 ====================

// TTS 版本号（MP3 迁移）
const TTS_CACHE_VERSION = 'v2_mp3_20251225'

/**
 * 清理旧版本 TTS 缓存
 * 从 AAC/Opus + IndexedDB 迁移到 MP3 + 服务器缓存
 */
const clearOldTtsCache = async () => {
  try {
    const currentVersion = localStorage.getItem('tts_cache_version')

    if (currentVersion !== TTS_CACHE_VERSION) {
      console.log('[TTS] 检测到旧版本缓存，开始清理...')

      // 删除 IndexedDB
      try {
        await indexedDB.deleteDatabase('readaria-tts-cache')
        console.log('[TTS] ✅ IndexedDB 已删除')
      } catch (err) {
        console.warn('[TTS] IndexedDB 删除失败:', err)
      }

      // 清理 localStorage 中的 TTS 日志（可选，保留最近诊断数据）
      // localStorage.removeItem('tts_debug_logs')

      // 更新版本标识
      localStorage.setItem('tts_cache_version', TTS_CACHE_VERSION)

      console.log('[TTS] ✅ 旧版本缓存已清理')

      // 可选：显示提示（首次打开时）
      if (currentVersion && currentVersion !== TTS_CACHE_VERSION) {
        // 老用户升级，显示提示
        setTimeout(() => {
          import('vant').then(({ showNotify }) => {
            showNotify({
              type: 'success',
              message: i18n.global.t('pwa.ttsUpgraded'),
              duration: 3000
            })
          })
        }, 1000) // 延迟1秒显示，避免与其他提示冲突
      }
    } else {
      console.log('[TTS] 缓存版本已是最新:', TTS_CACHE_VERSION)
    }
  } catch (error) {
    console.error('[TTS] 缓存清理失败:', error)
  }
}

// 在应用启动时执行缓存清理
clearOldTtsCache()

// ==================== 初始化 ====================

// 初始化用户状态（从localStorage恢复）
const userStore = useUserStore()
userStore.initFromStorage()

// 恢复并同步听读队列（登录用户从服务端拉取）
import('./stores/queueStore').then(({ useQueueStore }) => {
  useQueueStore().initSync().catch(error => {
    console.warn('[Main] Queue init sync failed:', error)
  })
})

console.log('Mounting app...')
app.mount('#app')
console.log('App mounted!')
