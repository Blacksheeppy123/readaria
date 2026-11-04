import { createRouter, createWebHistory } from 'vue-router'
import { useUserStore } from '@/stores/userStore'
import { useOnboardingStore } from '@/stores/onboardingStore'
import { useFeedStore } from '@/stores/feedStore'
import { responsive } from './responsive'
import i18n from '@/i18n'

/**
 * 老用户保护：如果用户已有 feeds，自动完成 onboarding，避免强制老用户走 onboarding 流程。
 * 只在 onboarding pending 时调用一次，完成后状态持久化到 localStorage。
 */
async function skipOnboardingIfExistingUser(onboardingStore) {
  if (!onboardingStore.isLanguagePending && !onboardingStore.isPathPending) {
    return false
  }
  const feedStore = useFeedStore()
  try {
    await feedStore.fetchFeeds()
    if (feedStore.feeds.length > 0) {
      console.log('[Router] Existing user with feeds detected, auto-completing onboarding')
      onboardingStore.markFirstAudioPlayed()
      return true
    }
  } catch (e) {
    // fetch 失败时不阻断，继续走 onboarding 流程
  }
  return false
}

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  scrollBehavior(to, from, savedPosition) {
    if (savedPosition) {
      return savedPosition
    }
    return { top: 0 }
  },
  routes: [
    {
      path: '/',
      name: 'landing',
      component: () => import('@/views/LandingView.vue'),
      meta: { title: 'Your Feeds, Narrated', skipAuth: true, hideTabbar: true }
    },
    {
      path: '/company',
      name: 'company',
      component: () => import('@/views/CompanyLandingView.vue'),
      meta: { title: 'MarlinWorks Limited — Building AI-Powered Knowledge Management Tools', skipAuth: true, hideTabbar: true }
    },
    {
      path: '/login',
      name: 'login',
      component: () => import('@/views/LoginView.vue'),
      meta: { titleKey: 'login.loginButton', skipAuth: true, hideTabbar: true, desktopCenter: true }
    },
    {
      path: '/register',
      name: 'register',
      component: () => import('@/views/RegisterView.vue'),
      meta: { titleKey: 'register.title', skipAuth: true, hideTabbar: true, desktopCenter: true }
    },
    {
      path: '/feed',
      name: 'feed',
      component: responsive(
        () => import('@/views/FeedView.vue'),
        () => import('@/views/desktop/DesktopFeedView.vue'),
        'FeedView'
      ),
      meta: { titleKey: 'nav.feed', requiresAuth: true, desktop: true }
    },
    {
      path: '/feed/manage',
      name: 'feed-manage',
      component: responsive(
        () => import('@/views/FeedManageView.vue'),
        () => import('@/views/desktop/DesktopFeedManageView.vue')
      ),
      meta: { titleKey: 'feeds.title', requiresAuth: true, hideTabbar: true, desktop: true }
    },
    {
      path: '/feed/discover',
      name: 'feed-discover',
      component: responsive(
        () => import('@/views/FeedDiscoverView.vue'),
        () => import('@/views/desktop/DesktopFeedDiscoverView.vue')
      ),
      meta: { titleKey: 'feeds.discoverTitle', requiresAuth: true, hideTabbar: true, desktop: true }
    },
    {
      path: '/listen',
      name: 'listen',
      component: () => import('@/views/ListenView.vue'),
      meta: { titleKey: 'nav.listen', requiresAuth: true }
    },
    // Legacy routes (redirect)
    {
      path: '/feeds',
      redirect: '/feed'
    },
    {
      path: '/articles',
      redirect: '/feed'
    },
    {
      path: '/manage/discover',
      redirect: '/feed/discover'
    },
    {
      path: '/manage/feeds',
      redirect: '/feed/manage'
    },
    {
      path: '/manage',
      redirect: '/feed/manage'
    },
    {
      path: '/me',
      name: 'me',
      component: () => import('@/views/MeView.vue'),
      meta: { titleKey: 'nav.me', requiresAuth: true }
    },
    {
      path: '/saved',
      name: 'saved',
      component: responsive(
        () => import('@/views/SavedView.vue'),
        () => import('@/views/desktop/DesktopSavedView.vue')
      ),
      meta: { titleKey: 'saved.title', requiresAuth: true, hideTabbar: true, desktop: true }
    },
    {
      path: '/article/:id',
      name: 'article-detail',
      component: responsive(
        () => import('@/views/ArticleDetail.vue'),
        () => import('@/views/desktop/DesktopArticleReader.vue')
      ),
      meta: { titleKey: 'articles.title', requiresAuth: true, hideTabbar: true, desktop: true },
      props: true
    },
    {
      path: '/search',
      name: 'search',
      component: () => import('@/views/SearchView.vue'),
      meta: { titleKey: 'search.title', requiresAuth: true }
    },
    {
      path: '/player',
      name: 'player',
      component: () => import('@/views/TtsPlayerView.vue'),
      meta: { titleKey: 'player.nowPlaying', requiresAuth: true, hideTabbar: true, desktopBare: true }
    },
    {
      path: '/debug/tts',
      name: 'debug-tts',
      component: () => import('@/views/DebugTTSView.vue'),
      meta: { titleKey: 'debug.ttsTitle', requiresAuth: true, desktopBare: true }
    },
    {
      path: '/debug/tts-logs',
      name: 'debug-tts-logs',
      component: () => import('@/views/DebugTTSLogsView.vue'),
      meta: { titleKey: 'debug.ttsLogsTitle', requiresAuth: true, requiresDebugAccess: true, desktopBare: true }
    },
    {
      path: '/podcasts',
      redirect: '/listen'
    },
    {
      path: '/podcasts/:id',
      name: 'podcast-detail',
      component: () => import('@/views/PodcastDetailView.vue'),
      meta: { titleKey: 'podcast.detail', requiresAuth: true, hideTabbar: true, desktopBare: true },
      props: true
    },
    {
      path: '/podcasts/:id/chat',
      name: 'podcast-chat',
      component: () => import('@/views/PodcastChatView.vue'),
      meta: { titleKey: 'podcast.chatWithPodcast', requiresAuth: true, hideTabbar: true, desktopBare: true },
      props: true
    },
    {
      path: '/podcast-preview/:token',
      name: 'podcast-preview',
      component: () => import('@/views/SharePodcastView.vue'),
      meta: { title: 'Podcast Preview', skipAuth: true, hideTabbar: true },
      props: true
    },
    {
      path: '/privacy',
      name: 'privacy',
      component: () => import('@/views/PrivacyPolicyView.vue'),
      meta: { title: 'Privacy Policy', skipAuth: true, hideTabbar: true }
    },
    {
      path: '/terms',
      name: 'terms',
      component: () => import('@/views/TermsOfServiceView.vue'),
      meta: { title: 'Terms of Service', skipAuth: true, hideTabbar: true }
    },
    {
      path: '/onboarding/language',
      name: 'onboarding-language',
      component: () => import('@/views/OnboardingLanguageView.vue'),
      meta: { titleKey: 'onboarding.language.title', requiresAuth: true, hideTabbar: true, desktopBare: true }
    },
    {
      path: '/onboarding/path',
      name: 'onboarding-path',
      component: () => import('@/views/OnboardingPathView.vue'),
      meta: { titleKey: 'onboarding.path.title', requiresAuth: true, hideTabbar: true, desktopBare: true }
    }
    // Week 5 Cleanup (2025-11-20): WeChatConfigView route removed
    // Reason: Migrated to RSSHub-CookieCloud solution - Cookie 配置现在通过浏览器插件完成
  ]
})

// 全局路由守卫
router.beforeEach(async (to, from, next) => {
  const userStore = useUserStore()
  const onboardingStore = useOnboardingStore()

  // 域名检测：marlinworks.xyz 访问根路径时重定向到公司页面
  if (to.path === '/' && typeof window !== 'undefined') {
    const hostname = window.location.hostname
    if (hostname === 'marlinworks.xyz') {
      next({ name: 'company' })
      return
    }
  }

  // 设置页面标题
  const { t } = i18n.global
  if (to.meta.titleKey) {
    document.title = `${t(to.meta.titleKey)} - Readaria`
  } else if (to.meta.title) {
    document.title = `${to.meta.title} - Readaria`
  } else {
    document.title = 'Readaria'
  }

  // 检查是否需要认证
  if (to.meta.requiresAuth) {
    if (!userStore.isLoggedIn) {
      // 未登录，跳转到登录页
      console.log('未登录，跳转到登录页')
      next({
        name: 'login',
        query: { redirect: to.fullPath } // 保存目标路由，登录后跳转
      })
      return
    }

    // 检查是否需要 Debug 权限（白名单用户）
    if (to.meta.requiresDebugAccess && !userStore.isDebugUser) {
      console.log('无 Debug 权限，跳转到首页')
      next({ name: 'feed' })
      return
    }

    // Onboarding redirect: logged-in users who haven't completed onboarding
    if (!to.path.startsWith('/onboarding')) {
      // 老用户保护：已有 feeds 的用户自动跳过 onboarding
      const skipped = await skipOnboardingIfExistingUser(onboardingStore)
      if (skipped) {
        next()
        return
      }

      if (onboardingStore.isLanguagePending) {
        next({ name: 'onboarding-language' })
        return
      }
      if (onboardingStore.isPathPending) {
        next({ name: 'onboarding-path' })
        return
      }
    }

    next()
  } else {
    // 如果已登录用户访问登录/注册/落地页，重定向到首页（但不阻止法律页面）
    if (to.meta.skipAuth && userStore.isLoggedIn && ['login', 'register', 'landing', 'company'].includes(to.name)) {
      // 老用户保护：已有 feeds 的用户自动跳过 onboarding
      const skipped = await skipOnboardingIfExistingUser(onboardingStore)
      if (skipped) {
        next({ name: 'feed' })
        return
      }

      // If onboarding is pending, redirect there instead of feed
      if (onboardingStore.isLanguagePending) {
        next({ name: 'onboarding-language' })
        return
      }
      if (onboardingStore.isPathPending) {
        next({ name: 'onboarding-path' })
        return
      }
      next({ name: 'feed' })
    } else {
      next()
    }
  }
})

export default router
