<script setup>
defineOptions({ name: 'ArticleListPane' })
import { ref, watch, onMounted, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useFeedStore } from '@/stores/feedStore'
import { resolveSourceName } from '@/utils/sourceName'
import { plainExcerpt } from '@/utils/articleContent'

const props = defineProps({
  articles: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
  finished: { type: Boolean, default: false },
  selectedUrl: { type: String, default: null }
})
const emit = defineEmits(['select', 'load-more'])

const { t } = useI18n()
const feedStore = useFeedStore()
const sentinel = ref(null)
let observer = null

const sourceName = (article) =>
  resolveSourceName(feedStore.feeds, article.source) || t('common.unknownSource')

const formatDate = (dateStr) => {
  if (!dateStr) return ''
  const date = new Date(dateStr)
  const diff = Date.now() - date.getTime()
  const days = Math.floor(diff / 86400000)
  if (days === 0) {
    const hours = Math.floor(diff / 3600000)
    if (hours === 0) {
      const minutes = Math.floor(diff / 60000)
      return minutes === 0 ? t('common.justNow') : t('common.minutesAgo', { n: minutes })
    }
    return t('common.hoursAgo', { n: hours })
  }
  if (days === 1) return t('common.yesterday')
  if (days < 7) return t('common.daysAgo', { n: days })
  return date.toLocaleDateString()
}

onMounted(() => {
  observer = new IntersectionObserver((entries) => {
    if (entries[0]?.isIntersecting && !props.loading && !props.finished) {
      emit('load-more')
    }
  }, { root: sentinel.value?.parentElement, rootMargin: '200px' })
  if (sentinel.value) observer.observe(sentinel.value)
})

onUnmounted(() => { observer?.disconnect() })

watch(() => props.selectedUrl, (url) => {
  if (!url) return
  const el = document.querySelector(`[data-article-url="${CSS.escape(url)}"]`)
  el?.scrollIntoView({ block: 'nearest' })
})
</script>

<template>
  <section class="article-list-pane">
    <div v-if="articles.length === 0 && !loading" class="list-empty">
      <slot name="empty">{{ $t('common.noData') }}</slot>
    </div>
    <article
      v-for="item in articles"
      :key="item.url"
      :data-article-url="item.url"
      class="list-item"
      :class="{ selected: item.url === selectedUrl, read: item.is_read || item.read_at }"
      @click="emit('select', item)"
    >
      <div class="item-source">{{ sourceName(item) }}</div>
      <h3 class="item-title">{{ item.title }}</h3>
      <p class="item-summary">{{ plainExcerpt(item.summary) }}</p>
      <div class="item-time">{{ formatDate(item.published_at) }}</div>
    </article>
    <div ref="sentinel" class="list-sentinel" />
    <div v-if="loading" class="list-status">{{ $t('common.loading') }}</div>
    <div v-else-if="finished && articles.length > 0" class="list-status">{{ $t('common.noMore') }}</div>
  </section>
</template>

<style scoped>
.article-list-pane {
  width: var(--desktop-list-width);
  flex-shrink: 0;
  height: 100vh;
  overflow-y: auto;
  border-right: 1px solid var(--readaria-border);
  background: var(--readaria-paper);
}
.list-empty {
  padding: 60px 20px; text-align: center; color: var(--readaria-muted); font-size: 14px;
}
.list-item {
  padding: 16px 20px;
  border-bottom: 1px solid var(--readaria-border);
  cursor: pointer;
  border-left: 3px solid transparent;
}
.list-item:hover { background: rgba(255, 250, 243, 0.8); }
.list-item.selected {
  background: var(--readaria-surface);
  border-left-color: var(--readaria-accent);
}
.list-item.read .item-title { color: var(--readaria-muted); }
.item-source {
  font-size: 12px; font-weight: 600; color: var(--readaria-accent); margin-bottom: 4px;
}
.item-title {
  font-size: 15px; font-weight: 600; color: var(--readaria-ink);
  line-height: 1.4; margin: 0 0 6px;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
}
.item-summary {
  font-size: 13px; color: var(--readaria-muted); line-height: 1.6; margin: 0 0 6px;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
}
.item-time { font-size: 12px; color: var(--readaria-muted); }
.list-sentinel { height: 1px; }
.list-status {
  padding: 16px; text-align: center; font-size: 13px; color: var(--readaria-muted);
}
</style>
