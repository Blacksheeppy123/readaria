<script setup>
defineOptions({ name: 'DesktopArticleReader' })
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { showToast } from 'vant'
import { useFeedStore } from '@/stores/feedStore'
import { useDesktopArticleStore } from '@/stores/desktopArticleStore'
import { useDesktopShortcuts } from '@/composables/useDesktopShortcuts'
import { useDesktopLayout } from '@/composables/useDesktopLayout'
import { getArticleByUrl, markReadByUrl, saveArticleByUrl, unsaveArticleByUrl, isArticleSaved } from '@/api/feeds'
import { openArticleInReader } from '@/utils/articleState'
import ArticleListPane from '@/components/desktop/ArticleListPane.vue'
import ListToolbar from '@/components/desktop/ListToolbar.vue'
import PaneDivider from '@/components/desktop/PaneDivider.vue'
import ReadingPane from '@/components/desktop/ReadingPane.vue'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const feedStore = useFeedStore()
const store = useDesktopArticleStore()
const { immersive, listWidth, setListWidth, persistLayout } = useDesktopLayout()

// 中栏拖拽调宽
let listDragStart = 0
const onListDragStart = () => { listDragStart = listWidth.value }
const onListDrag = (delta) => setListWidth(listDragStart + delta)

const article = ref(null)
const loading = ref(true)
const notFound = ref(false)
// 加载代际：路由切换/前进后退并发时，只有最新请求允许提交状态
let loadGen = 0

// :id 兼容两种历史格式：encodeURIComponent(url)（FeedView）与裸 url（SavedView）
const resolveUrl = () => {
  const raw = String(route.params.id || '')
  try { return decodeURIComponent(raw) } catch (_) { return raw }
}

const hasFullContent = (d) => !!(d && d.content && String(d.content).trim().length > 0)

const currentFeedName = computed(() => {
  if (store.selectedFeedId === null) return t('desktop.allFeeds')
  return feedStore.feeds.find(f => f.id === store.selectedFeedId)?.feed_name || t('desktop.allFeeds')
})

const toggleSort = () => {
  store.setSort(store.sortField === 'updated_at' ? 'published_at' : 'updated_at').catch(() => {})
}

const loadMore = () => store.loadMore().catch(() => {})

// s 键：保存/取消收藏选中的列表项
const toggleSaveAt = async (i) => {
  const a = store.articles[i]
  if (!a?.url) return
  try {
    const status = await isArticleSaved(a.url)
    if (status?.saved === true) {
      await unsaveArticleByUrl(a.url)
      showToast({ message: t('articleDetail.unsaveSuccess'), icon: 'info' })
    } else {
      await saveArticleByUrl(a.url)
      showToast({ message: t('articleDetail.saveSuccess'), icon: 'success' })
    }
  } catch (_) {
    showToast(t('common.operationFailed'))
  }
}

const loadArticle = async () => {
  const gen = ++loadGen
  loading.value = true
  notFound.value = false
  article.value = null
  const url = resolveUrl()

  // 1) history state → 2) sessionStorage：仅作即时渲染的元数据
  // 列表接口 only_summary，缓存通常无正文——有正文才视为完整，否则先渲染标题再补拉全文
  let cached = null
  const stateArticle = window.history.state?.article
  if (stateArticle?.url === url) cached = stateArticle
  if (!cached) {
    try {
      const raw = sessionStorage.getItem(`article_${encodeURIComponent(url)}`)
      const parsed = raw ? JSON.parse(raw) : null
      if (parsed?.url === url) cached = parsed
    } catch (_) {}
  }
  if (cached) {
    if (gen !== loadGen) return
    article.value = cached
    if (hasFullContent(cached)) loading.value = false
  }

  // 3) 正文缺失时补拉全文（刷新/深链场景同样依赖此路径）
  if (!hasFullContent(article.value)) {
    try {
      const resp = await getArticleByUrl(url)
      if (gen !== loadGen) return
      const full = resp?.article || resp
      if (full && typeof full === 'object' && full.url) {
        article.value = { ...article.value, ...full }
      } else if (!article.value) {
        notFound.value = true
      }
    } catch (_) {
      if (gen !== loadGen) return
      // 有摘要缓存时降级显示标题与摘要，不视为 notFound
      if (!article.value) notFound.value = true
    }
  }
  if (gen !== loadGen) return
  loading.value = false

  if (article.value?.url) {
    const articleUrl = article.value.url
    store.setSelected(articleUrl)
    store.markLocalRead(articleUrl)
    markReadByUrl(articleUrl).catch(() => {})
    // 同步移动端一致性：read_urls_cache + article-read 事件
    try {
      const key = 'read_urls_cache'
      const list = JSON.parse(sessionStorage.getItem(key) || '[]')
      if (!list.includes(articleUrl)) {
        list.push(articleUrl)
        sessionStorage.setItem(key, JSON.stringify(list))
      }
    } catch (_) {}
    window.dispatchEvent(new CustomEvent('article-read', { detail: { url: articleUrl } }))
  }
}

const openArticle = (item) => {
  // 同路由参数变化不重挂载：由 route.params.id 的 watch 统一加载（含已读标记）
  openArticleInReader(router, item)
}

// 浏览器前进/后退与中栏点击都经路由变化进入同一加载路径
watch(() => route.params.id, (id) => { if (id) loadArticle() })

useDesktopShortcuts({
  getCount: () => store.articles.length,
  getIndex: () => store.selectedIndex,
  setIndex: (i) => store.setSelected(store.articles[i]?.url ?? null),
  onOpen: (i) => { const a = store.articles[i]; if (a) openArticle(a) },
  onSave: toggleSaveAt
})

onMounted(async () => {
  if (feedStore.feeds.length === 0) {
    try { await feedStore.fetchFeeds() } catch (_) {}
  }
  if (store.articles.length === 0) {
    store.loadMore().catch(() => {})
  }
  await loadArticle()
})
</script>

<template>
  <div class="desktop-reader" :class="{ immersive }">
    <div v-show="!immersive" class="reader-column">
      <ListToolbar
        :current-feed-name="currentFeedName"
        :sort-field="store.sortField"
        @toggle-sort="toggleSort"
      />
      <ArticleListPane
        :articles="store.articles"
        :loading="store.loading"
        :finished="store.finished"
        :selected-url="store.selectedUrl"
        @select="openArticle"
        @load-more="loadMore"
      />
    </div>
    <PaneDivider
      v-show="!immersive"
      @dragstart="onListDragStart"
      @drag="onListDrag"
      @dragend="persistLayout"
    />
    <ReadingPane v-if="!notFound" :article="article" :loading="loading" />
    <section v-else class="reader-error">
      <p>{{ $t('desktop.articleNotFound') }}</p>
      <button class="back-btn" @click="router.push({ name: 'feed' })">{{ $t('desktop.backToFeed') }}</button>
    </section>
  </div>
</template>

<style scoped>
.desktop-reader { display: flex; height: 100vh; overflow: hidden; }
.reader-column {
  width: var(--desktop-list-width);
  flex-shrink: 0;
  display: flex; flex-direction: column;
}
.reader-column :deep(.article-list-pane) {
  width: 100%; height: auto; flex: 1; border-right: 0;
}
/* 沉浸模式：正文列放宽居中 */
.desktop-reader.immersive :deep(.reading-article) {
  max-width: 720px;
}
.reader-error {
  flex: 1; display: flex; flex-direction: column; gap: 16px;
  align-items: center; justify-content: center; color: var(--readaria-muted);
}
.back-btn {
  padding: 8px 20px; border-radius: 999px;
  border: 1px solid var(--readaria-border); background: var(--readaria-surface);
  color: var(--readaria-ink); cursor: pointer;
}
</style>
