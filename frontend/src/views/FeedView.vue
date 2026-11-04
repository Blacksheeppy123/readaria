<script setup>
defineOptions({ name: 'FeedView' })

import { ref, onMounted, onUnmounted, onActivated, computed, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { showToast, showLoadingToast, closeToast, showDialog } from 'vant'
import { getArticles } from '@/api/feeds'
import { useArticleStore } from '@/stores/articleStore'
import { useFeedStore } from '@/stores/feedStore'
import { usePlayerStore } from '@/stores/playerStore'
import { usePodcastPlayerStore } from '@/stores/podcastPlayerStore'
import { useQueueStore } from '@/stores/queueStore'
import { useUserStore } from '@/stores/userStore'
import { usePodcastStore } from '@/stores/podcastStore'
import { useOnboardingStore } from '@/stores/onboardingStore'
import { useNetworkStatus } from '@/composables/useNetworkStatus'
import { resolveSourceName } from '@/utils/sourceName'
import { trackArticlesFirstSynced } from '@/utils/analytics'

const { t, locale } = useI18n()
const router = useRouter()
const route = useRoute()
const feedStore = useFeedStore()
const playerStore = usePlayerStore()
const podcastPlayerStore = usePodcastPlayerStore()
const queueStore = useQueueStore()
const articleStore = useArticleStore()
const userStore = useUserStore()
const podcastStore = usePodcastStore()
const onboardingStore = useOnboardingStore()

const articles = ref([])
const seenUrls = ref(new Set())
const loading = ref(false)
const finished = ref(false)
const refreshing = ref(false)
const overviewTodayReadyCount = ref(0)
const currentPage = ref(1)
const pageSize = 20
const requestGeneration = ref(0) // 防止快速切换 tab/sort 导致旧请求污染列表

// 源筛选 — 横滑 tabs
const activeTab = ref(0) // 0 = All, 1+ = specific feeds
const selectedFeed = ref(null)
const filterPrompted = ref(false)
const feedsLoaded = ref(false) // 标记 feeds 是否已加载
const { isOnline: isNetworkOnline } = useNetworkStatus()

// 文章本地缓存：按用户 + 查询条件隔离，避免跨账号泄漏和数据错位
function getStoredUserId() {
  try {
    const savedUser = localStorage.getItem('readaria_user')
    if (!savedUser) return null
    return JSON.parse(savedUser)?.id || null
  } catch (_) {
    return null
  }
}
function getArticlesCacheKey() {
  const userId = getStoredUserId() || 'anonymous'
  const feedId = selectedFeed.value?.id || 'all'
  return `readaria_feed_articles_cache_${userId}_${feedId}_${sortField.value}_${sortDirection.value}`
}
const saveArticlesToCache = () => {
  try {
    localStorage.setItem(getArticlesCacheKey(), JSON.stringify(articles.value))
  } catch (_) {}
}
const loadArticlesFromCache = () => {
  try {
    const cached = localStorage.getItem(getArticlesCacheKey())
    return cached ? JSON.parse(cached) : []
  } catch (_) {
    return []
  }
}
const clearArticlesCache = () => {
  try {
    localStorage.removeItem(getArticlesCacheKey())
  } catch (_) {}
}

// 排序
const sortField = ref('updated_at')
const sortDirection = ref('desc')
const showSortSheet = ref(false)

// 新用户提示
const hasSeenFilterHint = ref(false)

// feeds 列表 (用于横滑 tabs)
const feedTabs = computed(() => {
  const tabs = [{ id: null, name: t('articles.allSources') }]
  feedStore.feeds.forEach(f => {
    tabs.push({ id: f.id, name: f.feed_name, feed: f })
  })
  return tabs
})

onMounted(async () => {
  // 恢复排序
  const savedSort = sessionStorage.getItem('articles_sort')
  if (savedSort) {
    try {
      const data = JSON.parse(savedSort)
      if (data?.order_by) sortField.value = data.order_by
      if (data?.direction) sortDirection.value = data.direction
    } catch (_) {}
  }

  // 先加载 feeds，再恢复筛选（筛选依赖 feeds 列表做 index 映射）
  if (feedStore.feeds.length === 0) {
    try {
      await feedStore.fetchFeeds()
    } catch (_) {}
  }
  feedsLoaded.value = true

  // 检查新用户提示状态
  hasSeenFilterHint.value = localStorage.getItem('feed_filter_hint_seen') === 'true'

  // 检查URL query参数中的 source（从FeedManageView点击过来）
  const sourceId = route.query.source
  if (sourceId && feedStore.feeds.length > 0) {
    const idx = feedStore.feeds.findIndex(f => f.id === parseInt(sourceId))
    if (idx >= 0) {
      selectedFeed.value = feedStore.feeds[idx]
      activeTab.value = idx + 1
      sessionStorage.setItem('articles_filter', JSON.stringify({ selectedFeed: selectedFeed.value }))
    }
    // 消费掉 source query，避免刷新时覆盖用户后续选择
    router.replace({ query: {} })
  } else {
    // 恢复筛选（feeds 已加载，可以正确映射 activeTab）
    const saved = sessionStorage.getItem('articles_filter')
    if (saved) {
      try {
        const data = JSON.parse(saved)
        if (data?.selectedFeed) {
          const idx = feedStore.feeds.findIndex(f => f.id === data.selectedFeed.id)
          if (idx >= 0) {
            selectedFeed.value = data.selectedFeed
            activeTab.value = idx + 1
          } else {
            // 保存的 feed 已不存在，清除
            sessionStorage.removeItem('articles_filter')
          }
        }
      } catch (_) {}
    }
  }

  onLoad().then(() => {
    // Starter pack 落地后兜底：
    // 后台 link_global_articles_to_feed 还没回填 user_article_refs 时，
    // 首次 onLoad 会拿到空列表。利用 experience podcast 的 120s 窗口作为标记，
    // 在 30s 内最多 10 次轮询，让文章列表自动出现，无需用户手动下拉刷新。
    if (articles.value.length > 0) return
    if (!onboardingStore.isExperiencePodcastRecentlyRequested) return
    // keep-alive 保留 FeedView 实例：每次启动新 starter-pack 兜底周期都重置 attempts，
    // 避免继承之前 landing 已消耗的预算导致提前停止重试。
    starterPackRefreshAttempts = 0
    starterPackRefreshTimerId = setTimeout(refreshFromStarterPack, STARTER_PACK_REFRESH_INTERVAL_MS)
  }).catch(() => {})

  // 并行获取播客列表，用于判断今日播客生成状态
  podcastStore.fetchPodcasts()
    .then(() => { podcastsLoaded.value = true })
    .catch(() => { podcastsLoaded.value = true })

  window.addEventListener('article-read', onArticleRead)
  window.addEventListener('focus', onFocusSync)
  window.addEventListener('pageshow', onShowSync)
})

const onArticleRead = (e) => {
  const url = e?.detail?.url
  if (!url) return
  const item = articles.value.find(a => a.url === url)
  if (item) item.is_read = true
}

const syncReadFromSession = () => {
  try {
    const raw = sessionStorage.getItem('read_urls_cache')
    const list = Array.isArray(JSON.parse(raw || '[]')) ? JSON.parse(raw || '[]') : []
    if (list.length === 0) return
    const set = new Set(list)
    articles.value.forEach(a => { if (a?.url && set.has(a.url)) a.is_read = true })
  } catch (_) {}
}
const onFocusSync = () => syncReadFromSession()
const onShowSync = () => syncReadFromSession()

onActivated(() => {
  // 轻量级状态同步：从 sessionStorage 同步已读状态
  syncReadFromSession()
})

onUnmounted(() => {
  window.removeEventListener('article-read', onArticleRead)
  window.removeEventListener('focus', onFocusSync)
  window.removeEventListener('pageshow', onShowSync)
  if (experiencePodcastTimeoutId) {
    clearTimeout(experiencePodcastTimeoutId)
    experiencePodcastTimeoutId = null
  }
  if (starterPackRefreshTimerId) {
    clearTimeout(starterPackRefreshTimerId)
    starterPackRefreshTimerId = null
  }
  starterPackRefreshAttempts = 0
})

// 加载更多
const onLoad = async (options = {}) => {
  if (finished.value) return
  loading.value = true
  const gen = requestGeneration.value
  try {
    const params = {
      page: currentPage.value,
      size: pageSize,
      order_by: sortField.value,
      sort: sortDirection.value
    }
    if (selectedFeed.value?.id) {
      params.feed_id = selectedFeed.value.id
    }
    const response = await getArticles(params, {
      ...options,
      preserveEnvelope: true
    })

    // 请求已过时（用户切换了 tab 或 sort），丢弃结果
    if (gen !== requestGeneration.value) return

    const items = Array.isArray(response?.articles) ? response.articles : []
    const pagination = response?.pagination || {}
    const overview = response?.overview || {}
    if (currentPage.value === 1) {
      overviewTodayReadyCount.value = Number(overview.today_ready_count ?? pagination.playable_total ?? 0)
    }

    let newArticles = items

    newArticles = newArticles.filter(a => {
      const key = a.url
      if (!key || seenUrls.value.has(key)) return false
      seenUrls.value.add(key)
      return true
    })

    if (newArticles.length === 0) {
      if (currentPage.value === 1 && selectedFeed.value && !filterPrompted.value) {
        filterPrompted.value = true
        try {
          await showDialog({
            title: t('common.noData'),
            message: t('articles.noArticles'),
            showCancelButton: true,
            cancelButtonText: t('common.cancel'),
            confirmButtonText: t('articles.allSources')
          })
          selectedFeed.value = null
          activeTab.value = 0
          sessionStorage.removeItem('articles_filter')
          articles.value = []
          seenUrls.value = new Set()
          currentPage.value = 1
          finished.value = false
          await onLoad()
          return
        } catch (_) {
          finished.value = true
        }
      } else {
        finished.value = true
      }
    } else {
      articles.value.push(...newArticles)
      syncReadFromSession()
      saveArticlesToCache()
      // 追踪首次同步成功（仅登录用户 + 未筛选全部源 + 第一页，避免子集入口误触发）
      // 注意：必须在 currentPage++ 之前判断，否则满页时 currentPage 已被自增为 2 导致漏报
      const userId = getStoredUserId()
      const isBootstrapState = selectedFeed.value === null && currentPage.value === 1
      if (userId && isBootstrapState) {
        const firstSyncKey = `ph_articles_first_synced_${userId}`
        if (!localStorage.getItem(firstSyncKey)) {
          trackArticlesFirstSynced(newArticles.length)
          localStorage.setItem(firstSyncKey, '1')
        }
      }
      if (newArticles.length >= pageSize) {
        currentPage.value++
      } else {
        finished.value = true
      }
    }
  } catch (error) {
    console.error('加载文章失败:', error)
    if (typeof navigator !== 'undefined' && !navigator.onLine) {
      const cached = loadArticlesFromCache()
      if (cached.length > 0) {
        articles.value = cached
        cached.forEach(a => { if (a?.url) seenUrls.value.add(a.url) })
        showToast({ message: t('feed.offlineShowingCached'), icon: 'fail', duration: 3000 })
      } else {
        showToast({ message: t('feed.offlineNoCache'), icon: 'fail', duration: 3000 })
      }
    }
    finished.value = true
    throw error
  } finally {
    loading.value = false
  }
}

// 下拉刷新
const onRefresh = async () => {
  // 用户主动下拉刷新时停止 starter pack 兜底轮询，避免重复触发
  if (starterPackRefreshTimerId) {
    clearTimeout(starterPackRefreshTimerId)
    starterPackRefreshTimerId = null
  }
  starterPackRefreshAttempts = 0
  finished.value = false
  currentPage.value = 1
  articles.value = []
  overviewTodayReadyCount.value = 0
  seenUrls.value = new Set()
  try {
    await onLoad({ silent: false })
    showToast(t('common.refreshSuccess'))
  } catch (_) {
    showToast({ message: t('articles.loadFailed'), icon: 'fail', duration: 3000 })
  } finally {
    refreshing.value = false
  }
}

// 横滑 tab 切换
const onTabChange = (index) => {
  // 标记提示为已看过
  if (!hasSeenFilterHint.value) {
    hasSeenFilterHint.value = true
    localStorage.setItem('feed_filter_hint_seen', 'true')
  }
  const tab = feedTabs.value[index]
  if (tab.id === null) {
    selectedFeed.value = null
    sessionStorage.removeItem('articles_filter')
  } else {
    selectedFeed.value = tab.feed
    sessionStorage.setItem('articles_filter', JSON.stringify({ selectedFeed: tab.feed }))
  }
  filterPrompted.value = false
  articles.value = []
  overviewTodayReadyCount.value = 0
  currentPage.value = 1
  finished.value = false
  seenUrls.value = new Set()
  requestGeneration.value++
  onLoad()
}

// 排序
const openSort = () => { showSortSheet.value = true }
const onSelectSort = (type) => {
  if (type === 'updated_desc') {
    sortField.value = 'updated_at'
    sortDirection.value = 'desc'
  } else if (type === 'published_desc') {
    sortField.value = 'published_at'
    sortDirection.value = 'desc'
  }
  sessionStorage.setItem('articles_sort', JSON.stringify({
    order_by: sortField.value,
    direction: sortDirection.value
  }))
  finished.value = false
  currentPage.value = 1
  articles.value = []
  overviewTodayReadyCount.value = 0
  seenUrls.value = new Set()
  requestGeneration.value++
  onLoad()
  showSortSheet.value = false
}

// 格式化日期
const formatDate = (dateStr) => {
  const date = new Date(dateStr)
  const now = new Date()
  const diff = now - date
  const days = Math.floor(diff / (1000 * 60 * 60 * 24))
  if (days === 0) {
    const hours = Math.floor(diff / (1000 * 60 * 60))
    if (hours === 0) {
      const minutes = Math.floor(diff / (1000 * 60))
      return minutes === 0 ? t('common.justNow') : t('common.minutesAgo', { n: minutes })
    }
    return t('common.hoursAgo', { n: hours })
  }
  if (days === 1) return t('common.yesterday')
  if (days < 7) return t('common.daysAgo', { n: days })
  return date.toLocaleDateString()
}

const truncateSummary = (text, maxLength = 120) => {
  if (!text) return t('articles.noSummary')
  const plainText = text.replace(/<[^>]*>/g, '').trim()
  if (plainText.length <= maxLength) return plainText
  return plainText.substring(0, maxLength) + '...'
}

const getSourceName = (sourceUrl) => {
  if (!sourceUrl) return t('common.unknownSource')
  return resolveSourceName(feedStore.feeds, sourceUrl) || t('common.unknownSource')
}

// 文章详情
let navLock = false
const viewArticle = (article) => {
  if (navLock) return
  navLock = true
  setTimeout(() => { navLock = false }, 600)
  try { articleStore.setCurrent(article) } catch (_) {}
  try {
    const idx = articles.value.findIndex(a => a.url === article.url)
    if (idx >= 0) articles.value[idx].is_read = true
  } catch (_) {}

  const toast = showLoadingToast({ message: t('articles.opening'), forbidClick: true, duration: 0 })

  const articleKey = `article_${encodeURIComponent(article.url)}`
  sessionStorage.setItem(articleKey, JSON.stringify(article))

  router.push({
    name: 'article-detail',
    params: { id: encodeURIComponent(article.url) },
    state: {
      article: {
        id: article.id,
        title: article.title,
        url: article.url,
        author: article.author,
        published_at: article.published_at,
        summary: article.summary,
        content: article.content,
        source: article.source,
        tags: article.tags,
        metadata: article.metadata
      }
    }
  })
  setTimeout(() => { try { closeToast() } catch (_) {} }, 300)
}

// 播放
const isPlaying = (article) => {
  if (!playerStore.currentArticle) return false
  return playerStore.currentArticle.url === article.url
}

const getPlayProgress = (article) => {
  if (!isPlaying(article)) return null
  const progress = playerStore.progress
  if (progress <= 0) return t('articles.nowPlaying')
  return t('articles.playedProgress', { progress: Math.round(progress) })
}

const handlePlayClick = (article) => {
  if (isPlaying(article)) {
    playerStore.togglePlayPause()
    return
  }
  const currentIndex = articles.value.findIndex(a => a.url === article.url)
  if (currentIndex === -1) {
    showToast(t('articles.cannotLocate'))
    return
  }
  const playlist = articles.value.slice(currentIndex)
  playerStore.playFromList(playlist, 0)
  showToast({ message: t('articles.startPlaying'), icon: 'volume-o', duration: 1000 })
}

// 加入队列
const handleAddToQueue = (article) => {
  queueStore.addToQueue(article)
}

// 导航
const goToSearch = () => { router.push({ name: 'search' }) }
const goToManage = () => { router.push({ name: 'feed-manage' }) }

// Onboarding: check if feeds are empty
const hasFeeds = computed(() => feedsLoaded.value && feedStore.feeds.length > 0)
const quickFilter = ref('all')

const showFirstPodcastCta = computed(() => {
  if (!hasFeeds.value) return false
  if (onboardingStore.isOnboardingComplete) return false
  if (podcastStore.isTodayPodcastCompleted) return false
  // 后台 link_global_articles_to_feed 可能还没回填 user_article_refs，
  // 此时 articles 为空也应继续展示 CTA：只要 cache podcast 已就绪
  // 或近期触发过 experience podcast 请求，就允许进入 Magic Moment。
  if (podcastStore.onboardingCachePodcast) return true
  if (onboardingStore.isExperiencePodcastRecentlyRequested) return true
  return articles.value.length > 0
})

const generateFirstPodcast = async () => {
  const cache = podcastStore.onboardingCachePodcast
  if (cache) {
    // Magic Moment：直接播放体验播客，并进入详情页承接播放体验
    // podcastPlayerStore.play() 内部会 emit first-audio-played 事件
    try {
      const audioUrl = await podcastStore.getPodcastAudioUrl(cache.id)
      await podcastPlayerStore.play(cache, audioUrl)
    } catch (e) {}
    router.push({ name: 'podcast-detail', params: { id: String(cache.id) } })
    return
  }
  router.push({ name: 'listen' })
}

// 首次播客自动触发：当 CTA 可见且没有播客在进行/完成/缓存时，后台自动开始生成
// 必须等待 fetchPodcasts 完成后才判断，避免与 experience podcast 复制产生竞态
let hasAutoTriggeredPodcast = false
let experiencePodcastTimeoutId = null
let starterPackRefreshTimerId = null
let starterPackRefreshAttempts = 0
const STARTER_PACK_REFRESH_MAX_ATTEMPTS = 10
const STARTER_PACK_REFRESH_INTERVAL_MS = 3000
const podcastsLoaded = ref(false)

// Starter pack 落地后的兜底轮询：
// addFeed 已转为 BackgroundTasks 异步链接 user_article_refs，FeedView 一来就 GET /articles
// 大概率拿到空列表。这里在 30s 内最多重试 10 次，文章一旦出现即停。
const refreshFromStarterPack = async () => {
  if (articles.value.length > 0) {
    // 已经有文章了，兜底任务完成，清掉 marker 避免后续误触发
    onboardingStore.clearExperiencePodcastRequested?.()
    starterPackRefreshAttempts = 0
    return
  }
  if (starterPackRefreshAttempts >= STARTER_PACK_REFRESH_MAX_ATTEMPTS) {
    // 达到上限仍然空列表，认为兜底失效，清 marker 避免下次进入又来一轮
    onboardingStore.clearExperiencePodcastRequested?.()
    starterPackRefreshAttempts = 0
    return
  }
  if (!onboardingStore.isExperiencePodcastRecentlyRequested) return
  starterPackRefreshAttempts++

  finished.value = false
  currentPage.value = 1
  seenUrls.value = new Set()
  requestGeneration.value++

  try {
    await onLoad({ silent: true })
  } catch (_) {}

  if (articles.value.length > 0) {
    onboardingStore.clearExperiencePodcastRequested?.()
    starterPackRefreshAttempts = 0
    return
  }
  if (starterPackRefreshAttempts >= STARTER_PACK_REFRESH_MAX_ATTEMPTS) {
    onboardingStore.clearExperiencePodcastRequested?.()
    starterPackRefreshAttempts = 0
    return
  }
  if (!onboardingStore.isExperiencePodcastRecentlyRequested) return
  starterPackRefreshTimerId = setTimeout(refreshFromStarterPack, STARTER_PACK_REFRESH_INTERVAL_MS)
}
watch([showFirstPodcastCta, podcastsLoaded], ([visible, loaded]) => {
  if (!visible || !loaded || hasAutoTriggeredPodcast) return
  if (podcastStore.isTodayPodcastInProgress || podcastStore.isTodayPodcastCompleted) return
  if (podcastStore.onboardingCachePodcast) {
    // 已发现 cache 播客，清掉 onboarding 标志避免下次进入误判
    onboardingStore.clearExperiencePodcastRequested?.()
    return
  }

  // 如果 onboarding 刚刚请求了 experience podcast，延迟触发以避免竞态
  if (onboardingStore.isExperiencePodcastRecentlyRequested) {
    experiencePodcastTimeoutId = setTimeout(async () => {
      experiencePodcastTimeoutId = null
      if (hasAutoTriggeredPodcast) return
      // 关键：再 fetch 一次最新状态，避免读到 onMounted 时的旧快照
      try {
        await podcastStore.fetchPodcasts({ syncPolling: false })
      } catch (_) {}
      if (podcastStore.onboardingCachePodcast) {
        onboardingStore.clearExperiencePodcastRequested?.()
        return
      }
      if (podcastStore.isTodayPodcastInProgress || podcastStore.isTodayPodcastCompleted) return
      hasAutoTriggeredPodcast = true
      podcastStore.generatePodcast({ style: 'deep_dive' }).catch(() => {})
    }, 8000)
    return
  }

  hasAutoTriggeredPodcast = true
  podcastStore.generatePodcast({ style: 'deep_dive' }).catch(() => {})
}, { immediate: true })

const firstPodcastCtaTitle = computed(() => {
  // cache 播客优先：避免 cache + user_generated 竞态时把可播放卡片误标为"生成中"
  if (podcastStore.onboardingCachePodcast) {
    return t('onboarding.podcast.playNow') || 'Play your first podcast'
  }
  if (podcastStore.isTodayPodcastInProgress) {
    return t('onboarding.podcast.generating')
  }
  return t('onboarding.podcast.ctaTitle')
})

const firstPodcastCtaDesc = computed(() => {
  if (podcastStore.onboardingCachePodcast) {
    return t('onboarding.podcast.readyDesc') || 'Ready to play — tap to listen'
  }
  if (podcastStore.isTodayPodcastInProgress) {
    return t('onboarding.podcast.ctaDesc')
  }
  return t('onboarding.podcast.ctaDesc')
})

const goToDiscover = () => router.push({ name: 'feed-discover' })

const playableArticlesCount = computed(() =>
  articles.value.filter(article => {
    const content = String(article?.content || '').trim()
    const summary = String(article?.summary || '').trim()
    return content.length > 0 || summary.length > 0
  }).length
)

const filteredArticles = computed(() => {
  if (quickFilter.value === 'unread') {
    return articles.value.filter(article => !(article.is_read === true || !!article.read_at))
  }
  if (quickFilter.value === 'playable') {
    return articles.value.filter(article => {
      const content = String(article?.content || '').trim()
      const summary = String(article?.summary || '').trim()
      return content.length > 0 || summary.length > 0
    })
  }
  return articles.value
})

const isDefaultFeedView = computed(() => !selectedFeed.value && quickFilter.value === 'all')
const shouldShowLaunchModules = computed(() => hasFeeds.value && isDefaultFeedView.value)
const feedOverviewSummary = computed(() => {
  if (overviewTodayReadyCount.value <= 0) return t('feed.launchOverviewNone')
  return t('feed.launchOverviewSummary', { count: overviewTodayReadyCount.value })
})
const feedPodcastCtaLabel = computed(() => {
  if (podcastStore.isTodayPodcastCompleted) return t('podcast.listenToday')
  if (podcastStore.isTodayPodcastInProgress) return t('podcast.generatingToday')
  if (overviewTodayReadyCount.value <= 0) return t('feed.openListen')
  if (podcastStore.todayPodcastStatus === 'failed') return t('podcast.retryGenerate')
  return t('feed.generateTodaysPodcast')
})
const featuredArticle = computed(() =>
  shouldShowLaunchModules.value ? (filteredArticles.value[0] || null) : null
)
const secondaryArticles = computed(() =>
  featuredArticle.value ? filteredArticles.value.slice(1) : filteredArticles.value
)
const emptyStateDescription = computed(() => {
  if (quickFilter.value === 'unread') return t('articles.noUnreadArticles')
  if (quickFilter.value === 'playable') return t('articles.noPlayableArticles')
  return t('articles.noArticles')
})
</script>

<template>
  <div class="feed-view">
    <van-nav-bar :title="$t('nav.feed')" fixed placeholder>
      <template #right>
        <div class="nav-right-buttons">
          <van-icon name="search" size="20" @click="goToSearch" class="nav-icon" />
          <van-icon name="sort" size="20" @click="openSort" class="nav-icon" />
          <van-icon name="apps-o" size="20" @click="goToManage" class="nav-icon" />
        </div>
      </template>
    </van-nav-bar>

    <!-- 横滑源筛选器 (only show when user has feeds) -->
    <van-tabs
      v-if="hasFeeds"
      v-model:active="activeTab"
      type="card"
      shrink
      swipeable
      @change="onTabChange"
      class="feed-tabs"
    >
      <van-tab v-for="tab in feedTabs" :key="tab.id ?? 'all'" :title="tab.name" />
    </van-tabs>
    <!-- 筛选提示 (仅新用户显示) -->
    <div v-if="hasFeeds && !hasSeenFilterHint" class="filter-hint">
      <van-icon name="arrow-left" size="12" color="var(--readaria-muted)" />
      <span>{{ $t('articles.swipeToFilter') }}</span>
      <van-icon name="arrow" size="12" color="var(--readaria-muted)" />
    </div>

    <van-pull-refresh
      v-model="refreshing"
      @refresh="onRefresh"
      :pull-distance="80"
      :head-height="50"
      :success-text="$t('common.refreshSuccess')"
      :success-duration="800"
    >
      <!-- 骨架屏 -->
      <template v-if="articles.length === 0 && loading">
        <div v-for="i in 5" :key="i" class="skeleton-card">
          <van-skeleton title :row="3" />
        </div>
      </template>

      <!-- First podcast CTA for onboarding users -->
      <div v-if="showFirstPodcastCta" class="first-podcast-cta" @click="generateFirstPodcast">
        <div class="cta-content">
          <div class="cta-icon">
            <van-loading v-if="podcastStore.isTodayPodcastInProgress" size="20" color="var(--readaria-accent)" />
            <template v-else-if="podcastStore.onboardingCachePodcast">▶️</template>
            <template v-else>🎙️</template>
          </div>
          <div class="cta-text">
            <h3>{{ firstPodcastCtaTitle }}</h3>
            <p>{{ firstPodcastCtaDesc }}</p>
          </div>
        </div>
        <van-icon v-if="!podcastStore.isTodayPodcastInProgress" name="arrow" color="var(--readaria-accent)" />
      </div>

      <van-list
        v-model:loading="loading"
        :finished="finished"
        :finished-text="$t('common.noMore')"
        @load="onLoad"
      >
        <div v-if="shouldShowLaunchModules" class="feed-overview">
          <p class="overview-kicker">{{ $t('feed.launchToday') }}</p>
          <h2>{{ feedOverviewSummary }}</h2>
          <button class="overview-cta" @click.stop="router.push({ name: 'listen', query: { scrollTo: 'podcast' } })">
            {{ feedPodcastCtaLabel }}
          </button>
        </div>

        <div v-if="hasFeeds" class="quick-filter-row">
          <button
            class="quick-filter"
            :class="{ active: quickFilter === 'all' }"
            @click="quickFilter = 'all'"
          >
            {{ $t('articles.allStatus') }}
          </button>
          <button
            class="quick-filter"
            :class="{ active: quickFilter === 'unread' }"
            @click="quickFilter = 'unread'"
          >
            {{ $t('articles.unread') }}
          </button>
          <button
            class="quick-filter"
            :class="{ active: quickFilter === 'playable' }"
            @click="quickFilter = 'playable'"
          >
            {{ $t('articles.playable') }}
          </button>
        </div>

        <div
          v-if="featuredArticle"
          class="featured-article"
          :class="{ playing: isPlaying(featuredArticle) }"
          @click="viewArticle(featuredArticle)"
        >
          <p class="featured-kicker">{{ $t('feed.launchFeatured') }}</p>
          <h3 class="featured-title">{{ featuredArticle.title }}</h3>
          <p class="featured-summary">{{ truncateSummary(featuredArticle.summary, 92) }}</p>
          <p class="featured-meta">
            {{ getSourceName(featuredArticle.source) }} · {{ formatDate(featuredArticle.updated_at || featuredArticle.published_at) }}
          </p>
          <div class="featured-actions">
            <button class="featured-button featured-button--primary" @click.stop="handlePlayClick(featuredArticle)">
              {{ isPlaying(featuredArticle) && !playerStore.isPaused ? $t('podcast.pause') : $t('feed.listenAction') }}
            </button>
            <button class="featured-button" @click.stop="handleAddToQueue(featuredArticle)">
              {{ $t('feed.queueAction') }}
            </button>
          </div>
        </div>

        <div
          v-for="article in secondaryArticles"
          :key="article.url"
          class="article-card"
          :class="{
            read: article.is_read === true || !!article.read_at,
            playing: isPlaying(article)
          }"
          @click="viewArticle(article)"
        >
          <div class="article-content">
            <div class="article-header">
              <h3 class="article-title" :class="{ read: article.is_read === true || !!article.read_at }">{{ article.title }}</h3>
              <div class="article-meta">
                <span class="article-source">{{ getSourceName(article.source) }}</span>
                <span class="article-author" v-if="article.author">{{ article.author }}</span>
                <span class="article-time">{{ formatDate(article.updated_at || article.published_at) }}</span>
              </div>
            </div>
            <div class="article-summary">{{ truncateSummary(article.summary) }}</div>

            <div v-if="isPlaying(article)" class="play-progress">
              <van-icon name="volume-o" size="14" />
              <span>{{ getPlayProgress(article) }}</span>
            </div>
          </div>

          <!-- 操作按钮组 -->
          <div class="article-actions">
            <!-- 加入队列 -->
            <van-icon
              name="plus"
              size="20"
              class="queue-btn"
              :class="{ 'in-queue': queueStore.isInQueue(article) }"
              :color="queueStore.isInQueue(article) ? 'var(--readaria-accent)' : 'var(--readaria-muted)'"
              @click.stop="handleAddToQueue(article)"
            />
            <!-- 播放 -->
            <van-icon
              :name="isPlaying(article) && !playerStore.isPaused ? 'pause-circle' : 'play-circle'"
              size="28"
              class="play-btn"
              :color="'var(--readaria-accent)'"
              @click.stop="handlePlayClick(article)"
            />
          </div>
        </div>
      </van-list>

      <van-empty v-if="filteredArticles.length === 0 && !loading && finished && hasFeeds" :description="emptyStateDescription" />

      <van-empty
        v-if="!hasFeeds && !loading && isNetworkOnline"
        :description="$t('articles.subscribeFirst')"
      />
    </van-pull-refresh>

    <!-- 排序弹窗 -->
    <van-action-sheet
      v-model:show="showSortSheet"
      :title="$t('articles.sortBy')"
      safe-area-inset-bottom
      teleport="body"
    >
      <div class="filter-content">
        <van-cell
          :title="$t('articles.sortByUpdated')"
          is-link
          :class="{ 'selected': sortField === 'updated_at' }"
          @click="onSelectSort('updated_desc')"
        />
        <van-cell
          :title="$t('articles.sortByPublished')"
          is-link
          :class="{ 'selected': sortField === 'published_at' }"
          @click="onSelectSort('published_desc')"
        />
      </div>
    </van-action-sheet>
  </div>
</template>

<style scoped>
.feed-view {
  min-height: 100vh;
  background: linear-gradient(180deg, var(--readaria-paper) 0%, #f2eadf 100%);
  padding-bottom: calc(50px + env(safe-area-inset-bottom, 0px) + 20px);
}

.nav-right-buttons {
  display: flex;
  align-items: center;
  gap: 16px;
}

.nav-icon {
  color: var(--readaria-ink);
  cursor: pointer;
  padding: 4px;
  transition: color 0.2s;
  min-width: 28px;
  min-height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.nav-icon:active {
  color: var(--readaria-accent);
  transform: scale(0.95);
}

/* 横滑源筛选器 */
.feed-tabs {
  position: sticky;
  top: 46px;
  z-index: 99;
  background: linear-gradient(180deg, var(--readaria-paper) 0%, #f2eadf 100%);
  padding: 8px 0 4px;
  touch-action: pan-x;
}

/* Android 上真正承接横向手势的是 nav，而不是外层 wrap */
.feed-tabs :deep(.van-tabs__wrap) {
  overflow: hidden;
  touch-action: pan-x;
}

.feed-tabs :deep(.van-tabs__nav) {
  scrollbar-width: none;
}

.feed-tabs :deep(.van-tabs__nav::-webkit-scrollbar) {
  display: none;
}

.feed-tabs :deep(.van-tabs__nav--card) {
  margin: 0 12px;
  border: none;
  background: transparent;
  flex-wrap: nowrap;
}

.feed-tabs :deep(.van-tabs__nav--card.van-tabs__nav--shrink) {
  display: flex;
}

.feed-tabs :deep(.van-tabs__nav--card.van-tabs__nav--complete) {
  overflow-x: auto !important;
  overflow-y: hidden;
  -webkit-overflow-scrolling: touch;
  touch-action: pan-x;
  overscroll-behavior-x: contain;
}

.feed-tabs :deep(.van-tab) {
  border: none;
  border-radius: 0;
  margin: 0 8px;
  padding: 0 2px 8px;
  font-size: 13px;
  color: var(--readaria-muted);
  background: transparent;
  flex: 0 0 auto;
  touch-action: pan-x;
}

.feed-tabs :deep(.van-tab__text) {
  touch-action: pan-x;
}

.feed-tabs :deep(.van-tab--active) {
  background: transparent;
  color: var(--readaria-ink);
  border-color: transparent;
  box-shadow: inset 0 -2px 0 var(--readaria-accent);
}

/* 筛选提示 */
.filter-hint {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  padding: 4px 0 8px;
  font-size: 12px;
  color: var(--readaria-muted);
  background: transparent;
}

.skeleton-card {
  background: rgba(255, 252, 248, 0.9);
  margin: 12px;
  padding: 16px;
  border-radius: 18px;
  border: 1px solid var(--readaria-border);
}

.feed-overview {
  margin: 14px 12px 12px;
  padding: 18px;
  border-radius: 24px;
  background: rgba(255, 251, 245, 0.9);
  border: 1px solid var(--readaria-border);
  box-shadow: 0 16px 34px rgba(66, 49, 33, 0.08);
}

.overview-kicker,
.featured-kicker {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.14em;
  color: #9a674f;
  margin: 0 0 8px;
}

.feed-overview h2,
.featured-title {
  font-family: var(--readaria-serif);
  font-weight: 600;
  color: var(--readaria-ink);
}

.feed-overview h2 {
  font-size: 28px;
  line-height: 1.08;
  margin: 0 0 14px;
}

.overview-cta,
.featured-button {
  border: 0;
  border-radius: 999px;
  padding: 10px 16px;
  font-size: 13px;
  font-weight: 600;
}

.overview-cta,
.featured-button:not(.featured-button--primary) {
  background: var(--readaria-accent-soft);
  color: #b55333;
}

.featured-button--primary {
  background: var(--readaria-navy);
  color: var(--readaria-paper);
}

.quick-filter-row {
  display: flex;
  gap: 10px;
  padding: 0 12px 8px;
  overflow-x: auto;
}

.quick-filter {
  border: 0;
  border-radius: 999px;
  padding: 8px 14px;
  background: rgba(23, 33, 48, 0.06);
  color: var(--readaria-muted);
  font-size: 12px;
  white-space: nowrap;
}

.quick-filter.active {
  background: var(--readaria-accent-soft);
  color: #b55333;
}

.featured-article {
  margin: 8px 12px 14px;
  padding: 18px;
  border-radius: 24px;
  background: rgba(255, 252, 248, 0.92);
  border: 1px solid var(--readaria-border);
  box-shadow: 0 18px 40px rgba(64, 45, 31, 0.08);
}

.featured-title {
  font-size: 26px;
  line-height: 1.06;
  margin: 0 0 10px;
}

.featured-summary,
.featured-meta {
  margin: 0;
  color: var(--readaria-muted);
}

.featured-summary {
  line-height: 1.6;
  margin-bottom: 10px;
}

.featured-meta {
  font-size: 13px;
}

.featured-actions {
  display: flex;
  gap: 10px;
  margin-top: 14px;
}

.filter-content {
  max-height: 60vh;
  overflow-y: auto;
  padding-bottom: max(24px, env(safe-area-inset-bottom));
  -webkit-overflow-scrolling: touch;
}

.filter-content .selected {
  background-color: var(--readaria-stone);
}

.article-card {
  background: transparent;
  margin: 12px;
  padding: 0 0 14px;
  border-radius: 0;
  cursor: pointer;
  transition: all 0.3s;
  display: flex;
  align-items: flex-start;
  gap: 12px;
  position: relative;
  border-bottom: 1px solid rgba(23, 33, 48, 0.08);
}

.article-card:active {
  background: rgba(23, 33, 48, 0.03);
}

.article-content {
  flex: 1;
  overflow: hidden;
}

.article-actions {
  display: flex;
  flex-direction: row;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.queue-btn {
  cursor: pointer;
  transition: transform 0.2s;
  padding: 4px;
}

.queue-btn:active {
  transform: scale(0.9);
}

.queue-btn.in-queue {
  opacity: 0.6;
}

.play-btn {
  flex-shrink: 0;
  cursor: pointer;
  transition: transform 0.2s;
}

.play-btn:active {
  transform: scale(0.9);
}

.article-header {
  margin-bottom: 8px;
}

.article-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--readaria-ink);
  margin: 0 0 8px 0;
  line-height: 1.5;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.article-title.read {
  color: #c8c9cc !important;
  font-weight: 400 !important;
}

.article-meta {
  display: flex;
  gap: 12px;
  font-size: 12px;
  color: var(--readaria-muted);
  flex-wrap: wrap;
}

.article-source {
  color: #9a674f;
  font-weight: 500;
}

.article-author {
  color: #646566;
}

.article-summary {
  font-size: 14px;
  color: var(--readaria-muted);
  line-height: 1.6;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
  white-space: pre-line;
}

.article-card.read .article-title { color: #c8c9cc !important; font-weight: 400 !important; }
.article-card.read .article-summary { color: #a7a7a7; }
.article-card.read .article-meta { color: #b1b3b8; }

.article-card.playing {
  background: linear-gradient(to right, rgba(199, 91, 57, 0.08), transparent 70%);
  border-left: 3px solid var(--readaria-accent);
  box-shadow: none;
  padding-left: 10px;
}

.article-card.playing .article-title {
  color: var(--readaria-accent) !important;
  font-weight: 600 !important;
}

.article-card.playing:active {
  background: linear-gradient(to right, rgba(199, 91, 57, 0.12), rgba(23, 33, 48, 0.02));
}

.play-progress {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-top: 8px;
  padding: 4px 8px;
  background: linear-gradient(135deg, var(--readaria-accent), #d89166);
  border-radius: 12px;
  color: white;
  font-size: 12px;
  font-weight: 500;
  width: fit-content;
  box-shadow: 0 2px 4px rgba(25, 137, 250, 0.2);
}

.play-progress span {
  line-height: 1;
}

/* Onboarding - Enhanced with animations and gradients */
.onboarding {
  padding: 32px 16px 20px;
  animation: fadeInUp 0.5s ease-out;
}

@keyframes fadeInUp {
  from {
    opacity: 0;
    transform: translateY(20px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.onboarding-header {
  text-align: center;
  margin-bottom: 32px;
}

.onboarding-title {
  font-size: 24px;
  font-family: var(--readaria-serif);
  font-weight: 600;
  color: var(--readaria-ink);
  margin: 0 0 10px;
}

.onboarding-desc {
  font-size: 14px;
  color: var(--readaria-muted);
  margin: 0;
  line-height: 1.5;
}

.onboarding-cards {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.onboarding-card {
  display: flex;
  align-items: center;
  gap: 16px;
  background: rgba(255, 252, 248, 0.88);
  border-radius: 22px;
  padding: 20px 18px;
  cursor: pointer;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  box-shadow: 0 16px 34px rgba(66, 49, 33, 0.08);
  border: 1px solid var(--readaria-border);
  position: relative;
  overflow: hidden;
}

.onboarding-card::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: linear-gradient(135deg, var(--card-gradient-start, var(--readaria-paper)) 0%, var(--card-gradient-end, #fff) 100%);
  opacity: 0;
  transition: opacity 0.3s ease;
  z-index: 0;
}

.onboarding-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.08);
}

.onboarding-card:active {
  transform: translateY(0);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
}

/* Card-specific gradient backgrounds */
.onboarding-card:nth-child(1) {
  --card-gradient-start: rgba(255, 193, 7, 0.08);
  --card-gradient-end: rgba(255, 152, 0, 0.04);
}

.onboarding-card:nth-child(2) {
  --card-gradient-start: rgba(33, 150, 243, 0.08);
  --card-gradient-end: rgba(25, 118, 210, 0.04);
}

.onboarding-card:nth-child(3) {
  --card-gradient-start: rgba(76, 175, 80, 0.08);
  --card-gradient-end: rgba(56, 142, 60, 0.04);
}

.card-icon {
  font-size: 28px;
  flex-shrink: 0;
  width: 52px;
  height: 52px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%);
  border-radius: 14px;
  box-shadow: inset 0 1px 2px rgba(255, 255, 255, 0.8), 0 2px 4px rgba(0, 0, 0, 0.04);
  position: relative;
  z-index: 1;
  animation: scaleIn 0.4s ease-out backwards;
}

/* Staggered icon animation */
.onboarding-card:nth-child(1) .card-icon {
  animation-delay: 0.1s;
  background: linear-gradient(135deg, #fff3e0 0%, #ffe0b2 100%);
}

.onboarding-card:nth-child(2) .card-icon {
  animation-delay: 0.2s;
  background: linear-gradient(135deg, #e3f2fd 0%, #bbdefb 100%);
}

.onboarding-card:nth-child(3) .card-icon {
  animation-delay: 0.3s;
  background: linear-gradient(135deg, #e8f5e9 0%, #c8e6c9 100%);
}

@keyframes scaleIn {
  from {
    opacity: 0;
    transform: scale(0.8);
  }
  to {
    opacity: 1;
    transform: scale(1);
  }
}

.onboarding-card .card-body,
.onboarding-card .van-icon {
  position: relative;
  z-index: 1;
}

.card-body {
  flex: 1;
  min-width: 0;
}

.card-body h3 {
  font-size: 16px;
  font-weight: 600;
  color: var(--readaria-ink);
  margin: 0 0 6px;
  transition: color 0.2s ease;
}

.onboarding-card:hover .card-body h3 {
  color: var(--readaria-accent);
}

.card-body p {
  font-size: 13px;
  color: var(--readaria-muted);
  margin: 0;
  line-height: 1.5;
}

/* Loading state animation */
.onboarding-card .van-loading {
  position: relative;
  z-index: 1;
}

/* Pulse animation for starter pack when loading */
@keyframes pulse {
  0%, 100% {
    opacity: 1;
  }
  50% {
    opacity: 0.6;
  }
}

.onboarding-card:has(.van-loading) {
  pointer-events: none;
}

.onboarding-card:has(.van-loading) .card-icon {
  animation: pulse 1.5s ease-in-out infinite;
}

/* First podcast CTA for onboarding users */
.first-podcast-cta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  background: linear-gradient(135deg, rgba(199, 91, 57, 0.08) 0%, rgba(199, 91, 57, 0.02) 100%);
  border: 1.5px solid var(--readaria-accent);
  border-radius: 16px;
  padding: 16px 18px;
  margin: 12px 0 16px;
  cursor: pointer;
  transition: all 0.25s ease;
  animation: fadeInUp 0.5s ease-out;
}

.first-podcast-cta:hover {
  transform: translateY(-1px);
  box-shadow: 0 6px 20px rgba(199, 91, 57, 0.12);
}

.first-podcast-cta:active {
  transform: translateY(0);
}

.cta-content {
  display: flex;
  align-items: center;
  gap: 14px;
  flex: 1;
  min-width: 0;
}

.cta-icon {
  font-size: 24px;
  flex-shrink: 0;
  width: 44px;
  height: 44px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(199, 91, 57, 0.1);
  border-radius: 12px;
}

.cta-text {
  min-width: 0;
}

.cta-text h3 {
  font-size: 15px;
  font-weight: 600;
  color: var(--readaria-ink);
  margin: 0 0 3px;
  line-height: 1.3;
}

.cta-text p {
  font-size: 12px;
  color: var(--readaria-muted);
  margin: 0;
  line-height: 1.4;
}
</style>
