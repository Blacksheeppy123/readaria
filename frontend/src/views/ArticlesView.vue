<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { showToast, showLoadingToast, closeToast, showDialog } from 'vant'
import { getArticles } from '@/api/feeds'
import { useArticleStore } from '@/stores/articleStore'
import { useFeedStore } from '@/stores/feedStore'
import { usePlayerStore } from '@/stores/playerStore'
import { resolveSourceName } from '@/utils/sourceName'

const { t } = useI18n()

const router = useRouter()
const feedStore = useFeedStore()
const playerStore = usePlayerStore()
const articles = ref([])
const seenUrls = ref(new Set())
const loading = ref(false)
const finished = ref(false)
const refreshing = ref(false)
const currentPage = ref(1)
const pageSize = 20
// 来源筛选（仅保留来源选择）
const selectedFeed = ref(null)
const showFeedFilter = ref(false)
const filterPrompted = ref(false)
// 排序：默认按更新时间倒序
const sortField = ref('updated_at') // 'updated_at' | 'published_at'
const sortDirection = ref('desc')   // 'asc' | 'desc'
const showSortSheet = ref(false)

onMounted(async () => {
  // 恢复来源筛选
  const saved = sessionStorage.getItem('articles_filter')
  if (saved) {
    try {
      const data = JSON.parse(saved)
      if (data && data.selectedFeed) selectedFeed.value = data.selectedFeed
    } catch (_) {}
  }
  // 恢复排序配置
  const savedSort = sessionStorage.getItem('articles_sort')
  if (savedSort) {
    try {
      const data = JSON.parse(savedSort)
      if (data?.order_by) sortField.value = data.order_by
      if (data?.direction) sortDirection.value = data.direction
    } catch (_) {}
  }
  // 先加载订阅列表，用于显示来源名称
  if (feedStore.feeds.length === 0) {
    try {
      await feedStore.fetchFeeds()
    } catch (error) {
      console.error('加载订阅列表失败:', error)
    }
  }
  // 然后加载文章
  onLoad()

  // 监听全局”已读”事件，及时更新列表样式
  window.addEventListener('article-read', onArticleRead)
  window.addEventListener('focus', onFocusSync)
  window.addEventListener('pageshow', onShowSync)
})

// 事件处理函数（提到 onMounted 外以便 onUnmounted 引用）
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
    articles.value.forEach(a => { if (a && a.url && set.has(a.url)) a.is_read = true })
  } catch (_) {}
}
const onFocusSync = () => syncReadFromSession()
const onShowSync = () => syncReadFromSession()

onUnmounted(() => {
  window.removeEventListener('article-read', onArticleRead)
  window.removeEventListener('focus', onFocusSync)
  window.removeEventListener('pageshow', onShowSync)
})

// 加载更多
const onLoad = async () => {
  if (finished.value) return

  loading.value = true
  try {
    const params = {
      page: currentPage.value,
      size: pageSize,
      order_by: sortField.value,
      sort: sortDirection.value
    }
    // 使用 feed_id 筛选而不是 source，避免 rsshub.app 和 localhost URL 不匹配问题
    if (selectedFeed.value?.id) {
      params.feed_id = selectedFeed.value.id
    }
    const response = await getArticles(params)

    // 响应拦截器已经解包，response直接就是文章数组
    let newArticles = Array.isArray(response) ? response : []

    // 去重：按 URL 作为唯一键
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
      // 同步最近已读缓存，确保样式立即更新
      try {
        const raw = sessionStorage.getItem('read_urls_cache')
        const list = Array.isArray(JSON.parse(raw || '[]')) ? JSON.parse(raw || '[]') : []
        if (list.length > 0) {
          const set = new Set(list)
          articles.value.forEach(a => { if (a && a.url && set.has(a.url)) a.is_read = true })
        }
      } catch (_) {}
      // 仅当返回数量达到页大小时，继续尝试下一页
      if (newArticles.length >= pageSize) {
        currentPage.value++
      } else {
        finished.value = true
      }
    }
  } catch (error) {
    console.error('加载文章失败:', error)
    showToast(t('articles.loadFailed'))
    finished.value = true
    throw error
  } finally {
    loading.value = false
  }
}

// 下拉刷新
const onRefresh = async () => {
  finished.value = false
  currentPage.value = 1
  articles.value = []
  seenUrls.value = new Set()
  try {
    await onLoad()
    showToast(t('common.refreshSuccess'))
  } catch (_) {
    // onLoad 内部已显示 loadFailed toast
  } finally {
    refreshing.value = false
  }
}

// 打开排序弹窗
const openSort = () => {
  showSortSheet.value = true
}

// 选择排序方式
const onSelectSort = (type) => {
  if (type === 'updated_desc') {
    sortField.value = 'updated_at'
    sortDirection.value = 'desc'
  } else if (type === 'published_desc') {
    sortField.value = 'published_at'
    sortDirection.value = 'desc'
  }
  // 持久化到 sessionStorage
  sessionStorage.setItem('articles_sort', JSON.stringify({
    order_by: sortField.value,
    direction: sortDirection.value
  }))
  // 重新加载列表
  finished.value = false
  currentPage.value = 1
  articles.value = []
  seenUrls.value = new Set()
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

// 截取摘要
const truncateSummary = (text, maxLength = 120) => {
  if (!text) return t('articles.noSummary')
  // 移除HTML标签
  const plainText = text.replace(/<[^>]*>/g, '').trim()
  if (plainText.length <= maxLength) return plainText
  return plainText.substring(0, maxLength) + '...'
}

// 从source URL提取订阅源名称
const getSourceName = (sourceUrl) => {
  if (!sourceUrl) return t('common.unknownSource')
  return resolveSourceName(feedStore.feeds, sourceUrl) || t('common.unknownSource')
}

// 查看文章详情（防重复点击 600ms）
const articleStore = useArticleStore()
let navLock = false
const viewArticle = (article) => {
  if (navLock) return
  navLock = true
  setTimeout(() => { navLock = false }, 600)
  // 将文章放入全局 store，详情页可同步渲染，减少闪烁
  try { articleStore.setCurrent(article) } catch (_) {}
  // 预先在当前列表标记为已读，提升返回时的即时反馈
  try {
    const idx = articles.value.findIndex(a => a.url === article.url)
    if (idx >= 0) articles.value[idx].is_read = true
  } catch (_) {}

  // 预取详情，尽量拿到完整 content 再进入，避免正文二次更新
  const toast = showLoadingToast({ message: t('articles.opening'), forbidClick: true, duration: 0 })
  ;(async () => {
    try {
      const { getArticleByUrl } = await import('@/api/feeds')
      const resp = await getArticleByUrl(article.url)
      if (resp && resp.article) {
        // 仅更新缓存，避免替换当前 store 对象引起首屏头部重绘
        const key = `article_${encodeURIComponent(resp.article.url || article.url)}`
        sessionStorage.setItem(key, JSON.stringify(resp.article))
      }
    } catch (_) {}
  })()

  // 使用sessionStorage备份文章数据（防止history.state丢失）
  const articleKey = `article_${encodeURIComponent(article.url)}`
  sessionStorage.setItem(articleKey, JSON.stringify(article))

  // Vue Router 4 不支持通过params传递对象
  // 使用 state 传递文章数据（只传递纯数据，避免 DataCloneError）
  router.push({
    name: 'article-detail',
    params: {
      // 传编码后的URL，避免路由二次规范化引起的参数变动
      id: encodeURIComponent(article.url)
    },
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

// 打开来源筛选
const openFilter = () => { showFeedFilter.value = true }

// 选择来源
const onSelectFeed = (feed) => {
  selectedFeed.value = feed
  showFeedFilter.value = false
  sessionStorage.setItem('articles_filter', JSON.stringify({ selectedFeed: feed }))
  // 重置并加载
  filterPrompted.value = false
  articles.value = []
  currentPage.value = 1
  finished.value = false
  seenUrls.value = new Set()
  onLoad()
}

// 清除来源筛选
const clearFilter = () => {
  selectedFeed.value = null
  showFeedFilter.value = false
  sessionStorage.removeItem('articles_filter')
  filterPrompted.value = false
  articles.value = []
  currentPage.value = 1
  finished.value = false
  seenUrls.value = new Set()
  onLoad()
}

// 跳转到搜索页面
const goToSearch = () => {
  router.push({ name: 'search' })
}

// 检查文章是否正在播放
const isPlaying = (article) => {
  if (!playerStore.currentArticle) return false
  return playerStore.currentArticle.url === article.url
}

// 获取播放进度文本
const getPlayProgress = (article) => {
  if (!isPlaying(article)) return null
  const progress = playerStore.progress
  if (progress <= 0) return t('articles.nowPlaying')
  return t('articles.playedProgress', { progress: Math.round(progress) })
}

// 处理播放按钮点击（播放/暂停切换）
const handlePlayClick = (article) => {
  // 如果点击的是正在播放的文章，切换播放/暂停
  if (isPlaying(article)) {
    playerStore.togglePlayPause()
    return
  }

  // 否则从该文章开始播放
  playFromHere(article)
}

// 从当前文章开始播放
const playFromHere = (article) => {
  // 找到当前文章在列表中的位置
  const currentIndex = articles.value.findIndex(a => a.url === article.url)
  if (currentIndex === -1) {
    showToast(t('articles.cannotLocate'))
    return
  }

  // 创建从当前文章开始的播放队列
  const playlist = articles.value.slice(currentIndex)

  // 开始播放
  playerStore.playFromList(playlist, 0)
  showToast({ message: t('articles.startPlaying'), icon: 'volume-o', duration: 1000 })
}
</script>

<template>
  <div class="articles-view">
    <van-nav-bar :title="$t('articles.title')" fixed placeholder>
      <template #right>
        <div class="nav-right-buttons">
          <van-icon name="search" size="20" @click="goToSearch" class="nav-icon" />
          <van-icon name="filter-o" size="20" @click="openFilter" class="nav-icon" :class="{ 'active': selectedFeed }" />
          <van-icon name="sort" size="20" @click="openSort" class="nav-icon" />
        </div>
      </template>
    </van-nav-bar>

    <!-- 显性展示筛选状态 -->
    <div class="filter-status">{{ $t('articles.filterSource') }}{{ selectedFeed ? selectedFeed.feed_name : $t('articles.allSources') }}</div>

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

      <van-list
        v-else
        v-model:loading="loading"
        :finished="finished"
        :finished-text="$t('common.noMore')"
        @load="onLoad"
      >
        <div
          v-for="article in articles"
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

            <!-- 播放进度提示 -->
            <div v-if="isPlaying(article)" class="play-progress">
              <van-icon name="volume-o" size="14" />
              <span>{{ getPlayProgress(article) }}</span>
            </div>
          </div>

          <!-- 播放按钮 -->
          <van-icon
            :name="isPlaying(article) && !playerStore.isPaused ? 'pause-circle' : 'play-circle'"
            size="28"
            class="play-btn"
            :color="isPlaying(article) && !playerStore.isPaused ? '#07c160' : '#1989fa'"
            @click.stop="handlePlayClick(article)"
          />
        </div>
      </van-list>

      <van-empty v-if="articles.length === 0 && !loading && finished" :description="$t('articles.noArticles')" />
    </van-pull-refresh>
    <!-- 来源筛选弹窗 -->
    <van-action-sheet
      v-model:show="showFeedFilter"
      :title="$t('articles.selectSource')"
      safe-area-inset-bottom
      teleport="body"
    >
      <div class="filter-content">
        <van-cell
          :title="$t('articles.noFilter')"
          is-link
          :class="{ 'selected': !selectedFeed }"
          @click="clearFilter"
        />
        <van-cell
          v-for="feed in feedStore.feeds"
          :key="feed.id"
          :title="feed.feed_name"
          is-link
          :class="{ 'selected': selectedFeed && selectedFeed.id === feed.id }"
          @click="onSelectFeed(feed)"
        />
      </div>
    </van-action-sheet>

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
.articles-view {
  min-height: 100vh;
  background: #f7f8fa;

  /* iOS 底部安全区域适配 - 防止最后一项被底部导航栏/Home Indicator 遮挡 */
  /* 计算公式：Tabbar 高度(50px) + 底部安全区域 + 缓冲空间(20px) */
  padding-bottom: calc(50px + env(safe-area-inset-bottom, 0px) + 20px);

  /* ⚠️ 注意：顶部不需要 padding，NavBar placeholder 已处理间距 */
}

/* 导航栏右侧按钮组 */
.nav-right-buttons {
  display: flex;
  align-items: center;
  gap: 16px;
}

.nav-icon {
  color: #323233;
  cursor: pointer;
  padding: 4px;
  transition: color 0.2s;
  /* 确保足够的点击区域（至少 44x44px） */
  min-width: 28px;
  min-height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.nav-icon:active {
  color: #1989fa;
  transform: scale(0.95);
}

.nav-icon.active {
  color: #1989fa;
}

.filter-status {
  position: sticky;
  top: 46px;
  z-index: 99;
  padding: 6px 12px;
  font-size: 12px;
  color: #646566;
  background: #f7f8fa;
}


.skeleton-card {
  background: white;
  margin: 12px;
  padding: 16px;
  border-radius: 8px;
}

.filter-content {
  max-height: 60vh;
  overflow-y: auto;
  /* iOS 底部安全区域适配 - 防止最后一项被 Home Indicator 遮挡（与 van-action-sheet 的 safe-area-inset-bottom 叠加） */
  padding-bottom: max(24px, env(safe-area-inset-bottom));
  /* 优化滚动性能 */
  -webkit-overflow-scrolling: touch;
}

.filter-content .selected {
  background-color: #f7f8fa;
}

.filter-content :deep(.van-cell__label) {
  font-size: 11px;
  color: #969799;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.article-card {
  background: white;
  margin: 12px;
  padding: 16px;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.3s;
  display: flex;
  align-items: center;
  gap: 12px;
  position: relative;
}

.article-card:active {
  background: #f7f8fa;
}

.article-content {
  flex: 1;
  overflow: hidden;
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
  color: #323233;
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
  color: #969799;
  flex-wrap: wrap;
}

.article-source {
  color: #1989fa;
  font-weight: 500;
}

.article-author {
  color: #646566;
}

.article-summary {
  font-size: 14px;
  color: #646566;
  line-height: 1.6;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
  white-space: pre-line;
}

/* 阅读态整体弱化（来源筛选列表里也更明显） */
.article-card.read .article-title { color: #c8c9cc !important; font-weight: 400 !important; }
.article-card.read .article-summary { color: #a7a7a7; }
.article-card.read .article-meta { color: #b1b3b8; }

/* ✅ 播放中的文章高亮样式（参考讯飞有声） */
.article-card.playing {
  background: linear-gradient(to right, #e8f4ff, #ffffff);
  border-left: 3px solid #1989fa;
  box-shadow: 0 2px 8px rgba(25, 137, 250, 0.1);
}

.article-card.playing .article-title {
  color: #1989fa !important;
  font-weight: 600 !important;
}

.article-card.playing:active {
  background: linear-gradient(to right, #d4e9ff, #f7f8fa);
}

/* 播放进度提示 */
.play-progress {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-top: 8px;
  padding: 4px 8px;
  background: linear-gradient(135deg, #1989fa, #07c160);
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

/* 已移除筛选样式 */
</style>
