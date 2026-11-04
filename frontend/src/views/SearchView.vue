<template>
  <div class="search-view">
    <van-nav-bar :title="$t('search.title')" fixed placeholder>
      <template #left>
        <van-icon name="arrow-left" size="18" @click="goBack" />
      </template>
    </van-nav-bar>

    <div class="search-bar">
      <van-search
        v-model="searchQuery"
        :placeholder="$t('search.inputPlaceholder')"
        show-action
        @search="onSearch"
        @clear="onClear"
      >
        <template #action>
          <div @click="onSearch">{{ $t('search.action') }}</div>
        </template>
      </van-search>
    </div>

    <div v-if="!hasSearched && searchHistory.length > 0" class="search-history">
      <div class="history-header">
        <span class="history-title">{{ $t('search.history') }}</span>
        <van-icon name="delete-o" @click="clearHistory" />
      </div>
      <div class="history-tags">
        <van-tag
          v-for="(item, index) in searchHistory"
          :key="index"
          type="primary"
          plain
          size="medium"
          @click="selectHistory(item)"
        >
          {{ item }}
        </van-tag>
      </div>
    </div>

    <div v-if="hasSearched" class="search-results">
      <div v-if="loading" class="loading-container">
        <van-loading size="24px">{{ $t('search.searching') }}</van-loading>
      </div>

      <div v-else-if="results.length > 0" class="results-list">
        <div class="results-count">{{ $t('search.resultsCount', { count: results.length }) }}</div>
        <div
          v-for="article in results"
          :key="article.url || article.title"
          class="result-card"
          @click="viewArticle(article)"
        >
          <h3 class="result-title" v-html="highlightText(article.title)"></h3>
          <div class="result-summary" v-html="highlightText(truncateSummary(article.summary || article.content))"></div>
          <div class="result-meta">
            <span v-if="article.source" class="meta-source">{{ getSourceName(article.source) }}</span>
            <span v-if="article.published || article.published_at" class="meta-time">
              {{ formatDate(article.published || article.published_at) }}
            </span>
          </div>
        </div>
      </div>

      <van-empty v-else :description="$t('search.noResults')">
        <van-button round type="primary" @click="hasSearched = false">
          {{ $t('common.back') }}
        </van-button>
      </van-empty>
    </div>

    <div v-if="!hasSearched && searchHistory.length === 0" class="empty-state">
      <van-empty :description="$t('search.emptyPrompt')" />
    </div>
  </div>
</template>

<script>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { showToast, showConfirmDialog } from 'vant'
import { searchArticles } from '@/api/feeds'
import { useFeedStore } from '@/stores/feedStore'
import { resolveSourceName } from '@/utils/sourceName'

const HISTORY_STORAGE_KEY = 'readaria_search_history'
const MAX_HISTORY_COUNT = 10

export default {
  name: 'SearchView',
  setup() {
    const router = useRouter()
    const feedStore = useFeedStore()
    const { t } = useI18n()

    const searchQuery = ref('')
    const results = ref([])
    const loading = ref(false)
    const hasSearched = ref(false)
    const searchHistory = ref([])

    onMounted(async () => {
      loadSearchHistory()
      try {
        if (feedStore.feeds.length === 0) {
          await feedStore.fetchFeeds()
        }
      } catch (_) {}
    })

    const loadSearchHistory = () => {
      try {
        const history = localStorage.getItem(HISTORY_STORAGE_KEY)
        if (history) {
          searchHistory.value = JSON.parse(history)
        }
      } catch (error) {
        console.error('Load search history failed:', error)
      }
    }

    const saveSearchHistory = (query) => {
      if (!query.trim()) return

      const filteredHistory = searchHistory.value.filter(item => item !== query)
      filteredHistory.unshift(query)

      if (filteredHistory.length > MAX_HISTORY_COUNT) {
        filteredHistory.pop()
      }

      searchHistory.value = filteredHistory

      try {
        localStorage.setItem(HISTORY_STORAGE_KEY, JSON.stringify(filteredHistory))
      } catch (error) {
        console.error('Save search history failed:', error)
      }
    }

    const clearHistory = () => {
      showConfirmDialog({
        title: t('common.hint'),
        message: t('search.clearHistoryConfirm')
      })
        .then(() => {
          searchHistory.value = []
          localStorage.removeItem(HISTORY_STORAGE_KEY)
          showToast(t('common.cleared'))
        })
        .catch(() => {})
    }

    const selectHistory = (item) => {
      searchQuery.value = item
      onSearch()
    }

    const onSearch = async () => {
      const query = searchQuery.value.trim()
      if (!query) {
        showToast(t('search.inputRequired'))
        return
      }

      loading.value = true
      hasSearched.value = true
      results.value = []

      try {
        const response = await searchArticles(query)
        console.log('Search results:', response)

        results.value = Array.isArray(response) ? response : []

        saveSearchHistory(query)

        if (results.value.length === 0) {
          showToast(t('search.noResults'))
        }
      } catch (error) {
        console.error('Search failed:', error)
        showToast(t('search.searchFailedRetry'))
      } finally {
        loading.value = false
      }
    }

    const onClear = () => {
      results.value = []
      hasSearched.value = false
    }

    const goBack = () => {
      router.back()
    }

    const viewArticle = (article) => {
      const articleKey = `article_${encodeURIComponent(article.url || article.title)}`
      sessionStorage.setItem(articleKey, JSON.stringify(article))

      router.push({
        name: 'article-detail',
        params: {
          id: encodeURIComponent(article.url || article.title)
        },
        state: {
          article: article
        }
      })
    }

    // 转义正则特殊字符，防止 ReDoS 和异常正则
    const escapeRegExp = (string) => {
      return string.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
    }

    // 剥离 HTML 标签，防止 XSS
    const stripHtmlTags = (html) => {
      if (!html) return ''
      return html.replace(/<[^>]*>/g, '')
    }

    const highlightText = (text) => {
      if (!text || !searchQuery.value) return stripHtmlTags(text)

      const query = searchQuery.value.trim()
      // 空搜索词直接返回剥离 HTML 后的文本
      if (!query) return stripHtmlTags(text)

      // 先剥离输入文本中的 HTML 标签，防止 XSS
      const safeText = stripHtmlTags(text)
      // 转义搜索词中的正则特殊字符，防止 ReDoS
      const safeQuery = escapeRegExp(query)
      const regex = new RegExp(`(${safeQuery})`, 'gi')
      return safeText.replace(regex, '<span class="highlight">$1</span>')
    }

    const getSourceName = (sourceUrl) => {
      if (!sourceUrl) return t('common.unknownSource')
      const name = resolveSourceName(feedStore.feeds, sourceUrl)
      if (name) return name
      try { const u = new URL(sourceUrl); return u.hostname } catch (_) { return sourceUrl }
    }

    const truncateSummary = (text, maxLength = 100) => {
      if (!text) return t('search.noSummary')

      const plainText = text.replace(/<[^>]*>/g, '').trim()
      if (plainText.length <= maxLength) return plainText
      return plainText.substring(0, maxLength) + '...'
    }

    const formatDate = (dateStr) => {
      if (!dateStr) return ''

      const date = new Date(dateStr)
      const now = new Date()
      const diff = now - date

      if (diff < 86400000) {
        const hours = Math.floor(diff / 3600000)
        if (hours === 0) {
          const minutes = Math.floor(diff / 60000)
          return minutes === 0 ? t('common.justNow') : t('common.minutesAgo', { n: minutes })
        }
        return t('common.hoursAgo', { n: hours })
      }

      if (diff < 604800000) {
        return t('common.daysAgo', { n: Math.floor(diff / 86400000) })
      }

      return date.toLocaleDateString()
    }

    return {
      searchQuery,
      results,
      loading,
      hasSearched,
      searchHistory,
      onSearch,
      onClear,
      goBack,
      viewArticle,
      highlightText,
      getSourceName,
      truncateSummary,
      formatDate,
      clearHistory,
      selectHistory
    }
  }
}
</script>

<style scoped>
.search-view {
  min-height: 100vh;
  background: #f7f8fa;
}

.search-bar {
  background: white;
  padding-bottom: 8px;
}

.search-history {
  background: white;
  margin-top: 8px;
  padding: 16px;
}

.history-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.history-title {
  font-size: 14px;
  font-weight: 600;
  color: #323233;
}

.history-header .van-icon {
  color: #969799;
  cursor: pointer;
}

.history-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.history-tags .van-tag {
  cursor: pointer;
}

.search-results {
  padding: 12px;
}

.loading-container {
  display: flex;
  justify-content: center;
  padding: 40px 0;
}

.results-count {
  font-size: 14px;
  color: #646566;
  margin-bottom: 12px;
  padding: 0 4px;
}

.results-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.result-card {
  background: white;
  padding: 16px;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.3s;
}

.result-card:active {
  background: #f7f8fa;
}

.result-title {
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

.result-summary {
  font-size: 14px;
  color: #646566;
  line-height: 1.6;
  margin-bottom: 8px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  white-space: pre-line;
}

.result-meta {
  display: flex;
  gap: 12px;
  font-size: 12px;
  color: #969799;
}

.meta-source {
  color: #1989fa;
  font-weight: 500;
}

.result-title :deep(.highlight),
.result-summary :deep(.highlight) {
  color: #ee0a24;
  background-color: #fff3e0;
  padding: 0 2px;
  border-radius: 2px;
  font-weight: 600;
}

.empty-state {
  padding-top: 60px;
}
</style>
