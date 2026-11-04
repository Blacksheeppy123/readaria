<script setup>
defineOptions({ name: 'DesktopFeedView' })
import { computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { showToast } from 'vant'
import { useFeedStore } from '@/stores/feedStore'
import { useDesktopArticleStore } from '@/stores/desktopArticleStore'
import { useDesktopShortcuts } from '@/composables/useDesktopShortcuts'
import { useDesktopLayout } from '@/composables/useDesktopLayout'
import { saveArticleByUrl, unsaveArticleByUrl, isArticleSaved } from '@/api/feeds'
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
const { listWidth, setListWidth, persistLayout } = useDesktopLayout()

// 中栏拖拽调宽
let listDragStart = 0
const onListDragStart = () => { listDragStart = listWidth.value }
const onListDrag = (delta) => setListWidth(listDragStart + delta)

const openArticle = (article) => {
  store.setSelected(article.url)
  store.markLocalRead(article.url)
  openArticleInReader(router, article)
}

// s 键：保存/取消收藏选中的列表项（先查状态再切换，与帮助浮层语义一致）
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

const currentFeedName = computed(() => {
  if (store.selectedFeedId === null) return t('desktop.allFeeds')
  return feedStore.feeds.find(f => f.id === store.selectedFeedId)?.feed_name || t('desktop.allFeeds')
})

const toggleSort = () => {
  store.setSort(store.sortField === 'updated_at' ? 'published_at' : 'updated_at').catch(() => {})
}

const loadMore = () => store.loadMore().catch(() => {})

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
  // 兼容移动端契约：/feed?source=<id>（来自订阅管理页点击源名称）
  const sourceId = route.query.source
  if (sourceId && feedStore.feeds.some(f => f.id === Number(sourceId))) {
    await store.selectFeed(Number(sourceId))
    router.replace({ query: {} })
  } else if (store.articles.length === 0) {
    try { await store.loadMore() } catch (_) {}
  }
})
</script>

<template>
  <div class="desktop-feed">
    <div class="feed-column">
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
    <PaneDivider @dragstart="onListDragStart" @drag="onListDrag" @dragend="persistLayout" />
    <ReadingPane :article="null" />
  </div>
</template>

<style scoped>
.desktop-feed { display: flex; height: 100vh; overflow: hidden; }
.feed-column {
  width: var(--desktop-list-width);
  flex-shrink: 0;
  display: flex; flex-direction: column;
}
.feed-column :deep(.article-list-pane) {
  width: 100%; height: auto; flex: 1; border-right: 0;
}
</style>
