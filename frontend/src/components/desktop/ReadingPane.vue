<script setup>
defineOptions({ name: 'ReadingPane' })
import { ref, computed, watch, nextTick } from 'vue'
import { useI18n } from 'vue-i18n'
import { showToast } from 'vant'
import { useFeedStore } from '@/stores/feedStore'
import { resolveSourceName } from '@/utils/sourceName'
import { sanitizeArticleContent, estimateReadingMinutes } from '@/utils/articleContent'
import { useDesktopLayout } from '@/composables/useDesktopLayout'
import { saveArticleByUrl, unsaveArticleByUrl, isArticleSaved } from '@/api/feeds'
import ArticleSummaryCard from '@/components/ArticleSummaryCard.vue'

const props = defineProps({
  article: { type: Object, default: null },
  loading: { type: Boolean, default: false }
})

const { t } = useI18n()
const feedStore = useFeedStore()
const { immersive, toggleImmersive } = useDesktopLayout()
const saved = ref(false)
let savedRequestGen = 0

watch(() => props.article?.url, async (url) => {
  const gen = ++savedRequestGen
  saved.value = false
  // The pane is its own scroll container; every new article starts at the top.
  await nextTick()
  if (gen === savedRequestGen) {
    document.querySelector('.reading-pane')?.scrollTo({ top: 0, behavior: 'auto' })
  }
  if (!url) return
  try {
    const status = await isArticleSaved(url)
    if (gen === savedRequestGen && props.article?.url === url) {
      saved.value = status?.saved === true
    }
  } catch (_) {}
}, { immediate: true, flush: 'post' })

const body = computed(() => sanitizeArticleContent(props.article?.content))
const minutes = computed(() => estimateReadingMinutes(props.article?.content))
const sourceName = computed(() =>
  props.article ? (resolveSourceName(feedStore.feeds, props.article.source) || t('common.unknownSource')) : ''
)
const publishedAt = computed(() => {
  const d = props.article?.published_at
  return d ? new Date(d).toLocaleDateString() : ''
})

const toggleSave = async () => {
  const url = props.article?.url
  if (!url) return
  // 点击后失焦，避免焦点驻留按钮导致 Enter 双触发（保存 + 打开选中文章）
  document.activeElement?.blur?.()
  const gen = ++savedRequestGen
  try {
    if (saved.value) {
      await unsaveArticleByUrl(url)
      if (gen === savedRequestGen && props.article?.url === url) saved.value = false
      showToast({ message: t('articleDetail.unsaveSuccess'), icon: 'info' })
    } else {
      await saveArticleByUrl(url)
      if (gen === savedRequestGen && props.article?.url === url) saved.value = true
      showToast({ message: t('articleDetail.saveSuccess'), icon: 'success' })
    }
  } catch (_) {
    showToast(t('common.operationFailed'))
  }
}

const openOriginal = () => {
  document.activeElement?.blur?.()
  if (props.article?.url) window.open(props.article.url, '_blank')
}

// 沉浸阅读：隐藏侧栏与中栏，仅保留正文
const onToggleImmersive = () => {
  document.activeElement?.blur?.()
  toggleImmersive()
}
</script>

<template>
  <section class="reading-pane">
    <div v-if="loading" class="pane-status">{{ $t('common.loading') }}</div>

    <div v-else-if="!article" class="pane-empty">
      <p>{{ $t('desktop.selectArticle') }}</p>
    </div>

    <article v-else class="reading-article" :key="article.url">
      <header class="reading-header">
        <h1 class="reading-title">{{ article.title }}</h1>
        <div class="reading-meta">
          <span class="meta-source">{{ sourceName }}</span>
          <span v-if="publishedAt"> · {{ publishedAt }}</span>
          <span> · {{ $t('desktop.readingMinutes', { n: minutes }) }}</span>
        </div>
        <div class="reading-actions">
          <button class="action-btn" :class="{ active: saved }" @click="toggleSave">
            {{ saved ? $t('desktop.saved') : $t('desktop.save') }}
          </button>
          <button class="action-btn" @click="openOriginal">{{ $t('desktop.openOriginal') }}</button>
          <button class="action-btn" :class="{ active: immersive }" @click="onToggleImmersive">
            ⤢ {{ $t('desktop.focusMode') }}
          </button>
        </div>
      </header>
      <ArticleSummaryCard :summary="article.summary" />
      <div class="reading-body" v-html="body" />
    </article>
  </section>
</template>

<style scoped>
.reading-pane {
  flex: 1;
  min-width: 0;
  height: 100vh;
  overflow-y: auto;
  background: var(--readaria-paper);
}
.pane-status, .pane-empty {
  display: flex; align-items: center; justify-content: center;
  height: 60vh; color: var(--readaria-muted); font-size: 15px;
}
.pane-empty p { font-family: var(--reading-serif); font-size: 18px; }
.reading-article {
  max-width: var(--reading-measure);
  margin: 0 auto;
  padding: 56px 32px 120px;
}
.reading-title {
  font-family: var(--reading-serif);
  font-size: 32px;
  font-weight: 700;
  line-height: 1.3;
  color: var(--readaria-ink);
  margin: 0 0 14px;
}
.reading-meta {
  font-size: 13px; color: var(--readaria-muted); margin-bottom: 18px;
}
.meta-source { color: var(--readaria-accent); font-weight: 600; }
.reading-actions {
  display: flex; gap: 10px;
  padding-bottom: 24px; margin-bottom: 32px;
  border-bottom: 1px solid var(--readaria-border);
}
.action-btn {
  padding: 7px 16px; border-radius: 999px;
  border: 1px solid var(--readaria-border);
  background: var(--readaria-surface);
  font-size: 13px; color: var(--readaria-ink); cursor: pointer;
}
.action-btn:hover { border-color: var(--readaria-accent); }
.action-btn.active {
  background: var(--readaria-accent-soft);
  border-color: var(--readaria-accent);
  color: var(--readaria-accent);
  font-weight: 600;
}
.reading-body {
  font-family: var(--reading-serif);
  font-size: var(--reading-font-size);
  line-height: var(--reading-line-height);
  color: var(--readaria-ink);
  word-wrap: break-word;
}
.reading-body :deep(p) { margin: 0 0 var(--reading-paragraph-gap); }
.reading-body :deep(img) {
  max-width: 100%; height: auto; border-radius: 10px; margin: 16px 0;
}
.reading-body :deep(a) { color: var(--readaria-accent); text-decoration: none; }
.reading-body :deep(h1), .reading-body :deep(h2), .reading-body :deep(h3) {
  font-family: var(--reading-serif); margin: 1.4em 0 0.6em; line-height: 1.4;
}
.reading-body :deep(h1) { font-size: 24px; }
.reading-body :deep(h2) { font-size: 21px; }
.reading-body :deep(h3) { font-size: 19px; }
.reading-body :deep(ul), .reading-body :deep(ol) { padding-left: 1.4em; margin: 0 0 1em; }
.reading-body :deep(li) { margin: 0.4em 0; }
.reading-body :deep(blockquote) {
  margin: 1.2em 0; padding: 4px 0 4px 16px;
  border-left: 3px solid var(--readaria-accent);
  color: var(--readaria-muted);
}
.reading-body :deep(pre) {
  background: var(--readaria-stone); border-radius: 8px;
  padding: 14px; overflow-x: auto; font-size: 14px;
}
.reading-body :deep(code) { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
</style>
