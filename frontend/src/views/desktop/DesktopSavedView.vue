<script setup>
defineOptions({ name: 'DesktopSavedView' })
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { showToast } from 'vant'
import { getSavedArticles } from '@/api/feeds'
import { openArticleInReader } from '@/utils/articleState'
import { useFeedStore } from '@/stores/feedStore'
import ArticleListPane from '@/components/desktop/ArticleListPane.vue'
import ReadingPane from '@/components/desktop/ReadingPane.vue'

const { t } = useI18n()
const router = useRouter()
const feedStore = useFeedStore()

const articles = ref([])
const loading = ref(false)
const finished = ref(false)
const currentPage = ref(1)
const pageSize = 20
const selectedUrl = ref(null)

const onLoad = async () => {
  if (finished.value || loading.value) return
  loading.value = true
  try {
    const res = await getSavedArticles({ page: currentPage.value, size: pageSize })
    const fresh = Array.isArray(res) ? res : (res.articles || [])
    if (fresh.length === 0) {
      finished.value = true
    } else {
      articles.value.push(...fresh)
      if (fresh.length >= pageSize) currentPage.value++
      else finished.value = true
    }
  } catch (e) {
    showToast(t('saved.loadFailed'))
    finished.value = true
  } finally {
    loading.value = false
  }
}

const openArticle = (article) => {
  selectedUrl.value = article.url
  openArticleInReader(router, article)
}

onMounted(async () => {
  // Direct deep links must hydrate feed metadata for source labels in the list.
  const feedPromise = feedStore.feeds.length === 0
    ? feedStore.fetchFeeds().catch(() => {})
    : Promise.resolve()
  await Promise.all([feedPromise, onLoad()])
})
</script>

<template>
  <div class="desktop-saved">
    <ArticleListPane
      :articles="articles"
      :loading="loading"
      :finished="finished"
      :selected-url="selectedUrl"
      @select="openArticle"
      @load-more="onLoad"
    >
      <template #empty>{{ $t('desktop.emptySaved') }}</template>
    </ArticleListPane>
    <ReadingPane :article="null" />
  </div>
</template>

<style scoped>
.desktop-saved { display: flex; height: 100vh; overflow: hidden; }
</style>
