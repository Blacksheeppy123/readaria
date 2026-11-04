<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { usePodcastStore } from '@/stores/podcastStore'
import { usePodcastPlayerStore } from '@/stores/podcastPlayerStore'
import ConversationPanel from '@/components/ConversationPanel.vue'
import { showToast } from 'vant'

const router = useRouter()
const route = useRoute()
const { t } = useI18n()
const podcastStore = usePodcastStore()
const podcastPlayer = usePodcastPlayerStore()

const podcastId = ref(route.params.id)
const podcast = ref(null)
const activeCollapse = ref([])

// 是否有浮动播放器显示
const hasFloatingPlayer = computed(() =>
  podcastPlayer.isPlaying || podcastPlayer.isPaused
)

onMounted(async () => {
  try {
    podcast.value = await podcastStore.getPodcastDetail(podcastId.value)
  } catch {
    // podcast detail is optional for chat
  }
})

const viewArticle = (article) => {
  if (!article.url) { showToast(t('podcast.articleLinkUnavailable')); return }
  const articleState = {
    id: article.id,
    title: article.title,
    url: article.url,
    source: article.source,
    source_name: article.feed_title
  }
  try {
    sessionStorage.setItem(`article_${encodeURIComponent(article.url)}`, JSON.stringify(articleState))
  } catch (_) {}
  router.push({
    name: 'article-detail',
    params: { id: encodeURIComponent(article.url) },
    state: { article: articleState }
  })
}

// 用户开始输入时自动收起文章列表
const onChatInput = () => {
  if (activeCollapse.value.length) {
    activeCollapse.value = []
  }
}
</script>

<template>
  <div class="podcast-chat-view">
    <van-nav-bar
      :title="$t('podcast.chatWithPodcast')"
      left-arrow
      @click-left="router.back()"
    />

    <!-- 可折叠文章列表 -->
    <van-collapse
      v-if="podcast?.articles?.length"
      v-model="activeCollapse"
      class="articles-collapse"
    >
      <van-collapse-item
        :title="$t('podcast.relatedArticles')"
        name="articles"
        :value="$t('podcast.articlesCount', { count: podcast.articles.length })"
      >
        <div class="articles-scroll">
          <van-cell
            v-for="article in podcast.articles"
            :key="article.id"
            :title="article.title"
            is-link
            @click="viewArticle(article)"
          >
            <template #label>
              <span v-if="article.feed_title" class="article-source">{{ article.feed_title }}</span>
            </template>
          </van-cell>
        </div>
      </van-collapse-item>
    </van-collapse>

    <ConversationPanel
      :podcast-id="podcastId"
      :podcast="podcast"
      class="chat-body"
      :class="{ 'with-floating-player': hasFloatingPlayer }"
      @input="onChatInput"
    />
  </div>
</template>

<style scoped>
.podcast-chat-view {
  min-height: 100%;
  display: flex;
  flex-direction: column;
  background-color: #f5f5f5;
}

.articles-collapse {
  flex-shrink: 0;
}

.articles-scroll {
  max-height: 23vh;
  overflow-y: auto;
  -webkit-overflow-scrolling: touch;
}

.article-source {
  font-size: 12px;
  color: #999;
}

.chat-body {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.chat-body.with-floating-player {
  padding-bottom: 92px;
}
</style>
