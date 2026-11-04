<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { showToast } from 'vant'
import { getSavedArticles } from '@/api/feeds'

const { t } = useI18n()
const router = useRouter()
const articles = ref([])
const loading = ref(false)
const finished = ref(false)
const refreshing = ref(false)
const currentPage = ref(1)
const pageSize = 20

onMounted(() => {
  onLoad()
})

const onLoad = async () => {
  if (finished.value) return
  loading.value = true
  try {
    const res = await getSavedArticles({ page: currentPage.value, size: pageSize })
    const newArticles = Array.isArray(res) ? res : (res.articles || [])
    if (newArticles.length === 0) {
      finished.value = true
    } else {
      articles.value.push(...newArticles)
      if (newArticles.length >= pageSize) {
        currentPage.value++
      } else {
        finished.value = true
      }
    }
  } catch (e) {
    console.error('Load saved failed:', e)
    showToast(t('saved.loadFailed'))
    finished.value = true
  } finally {
    loading.value = false
  }
}

const onRefresh = async () => {
  finished.value = false
  currentPage.value = 1
  articles.value = []
  await onLoad()
  refreshing.value = false
  showToast(t('common.refreshSuccess'))
}

const formatDate = (dateStr) => {
  if (!dateStr) return ''
  const d = new Date(dateStr)
  return d.toLocaleString()
}

const viewArticle = (article) => {
  const key = `article_${encodeURIComponent(article.url)}`
  sessionStorage.setItem(key, JSON.stringify(article))
  router.push({
    name: 'article-detail',
    params: { id: article.url },
    state: { article }
  })
}
</script>

<template>
  <div class="saved-view">
    <van-nav-bar :title="$t('saved.title')" fixed placeholder />

    <van-pull-refresh v-model="refreshing" @refresh="onRefresh">
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
          @click="viewArticle(article)"
        >
          <div class="article-header">
            <h3 class="article-title">{{ article.title }}</h3>
            <div class="article-meta">
              <span class="article-source">{{ $t('saved.savedLabel') }}</span>
              <span class="article-time">{{ formatDate(article.published_at) }}</span>
            </div>
          </div>
          <div class="article-summary">{{ (article.summary || '').replace(/<[^>]*>/g, '').slice(0, 120) }}</div>
        </div>
      </van-list>

      <van-empty v-if="articles.length === 0 && !loading && finished" :description="$t('saved.empty')" />
    </van-pull-refresh>
  </div>
</template>

<style scoped>
.saved-view {
  min-height: 100vh;
  background:
    radial-gradient(circle at top, rgba(199, 91, 57, 0.08), transparent 32%),
    linear-gradient(180deg, var(--readaria-paper) 0%, var(--readaria-stone) 100%);
  padding-bottom: calc(68px + env(safe-area-inset-bottom, 0px));
}

.skeleton-card,
.article-card {
  background: rgba(255, 250, 243, 0.92);
  margin: 12px;
  padding: 16px;
  border-radius: 22px;
  border: 1px solid var(--readaria-border);
  box-shadow: 0 14px 30px rgba(64, 45, 31, 0.08);
}

.article-header {
  margin-bottom: 10px;
}

.article-title {
  font-size: 17px;
  font-weight: 600;
  color: var(--readaria-ink);
  margin: 0 0 8px 0;
  line-height: 1.5;
}

.article-meta {
  display: flex;
  gap: 12px;
  font-size: 12px;
  color: var(--readaria-muted);
  flex-wrap: wrap;
}

.article-source {
  color: var(--readaria-accent);
  font-weight: 600;
}

.article-summary {
  font-size: 14px;
  color: var(--readaria-muted);
  line-height: 1.7;
  white-space: pre-line;
}
</style>
