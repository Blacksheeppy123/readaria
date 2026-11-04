<script setup>
defineOptions({ name: 'ListenView' })
import { computed, ref, onMounted, nextTick } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { showToast, showConfirmDialog } from 'vant'
import { useQueueStore } from '@/stores/queueStore'
import { usePodcastStore } from '@/stores/podcastStore'
import { usePlayerStore } from '@/stores/playerStore'
import { useFeedStore } from '@/stores/feedStore'
import { resolveSourceName } from '@/utils/sourceName'

const { t } = useI18n()
const router = useRouter()
const route = useRoute()
const queueStore = useQueueStore()
const podcastStore = usePodcastStore()
const playerStore = usePlayerStore()
const feedStore = useFeedStore()

const podcastLoading = ref(false)
const generating = ref(false)
const refreshing = ref(false)
const podcastSectionRef = ref(null)

onMounted(async () => {
  podcastLoading.value = true
  try {
    await podcastStore.fetchPodcasts()
  } catch (_) {}
  finally {
    podcastLoading.value = false
  }

  if (feedStore.feeds.length === 0) {
    try { await feedStore.fetchFeeds() } catch (_) {}
  }

  if (route.query.scrollTo === 'podcast') {
    nextTick(() => {
      if (podcastSectionRef.value) {
        podcastSectionRef.value.scrollIntoView({ behavior: 'smooth', block: 'center' })
      }
      // Clean up the query param so refresh doesn't scroll again
      router.replace({ query: {} })
    })
  }
})

const queueMinutes = computed(() => Math.max(1, queueStore.length * 5))
const latestPodcast = computed(() => podcastStore.latestPodcast)
const todayPodcast = computed(() => podcastStore.todayPodcast)
const podcastActionDisabled = computed(() => generating.value || podcastStore.isTodayPodcastInProgress)
const podcastActionLoading = computed(() => generating.value || podcastStore.isTodayPodcastInProgress)
const podcastActionLabel = computed(() => {
  if (podcastStore.isTodayPodcastCompleted) return t('podcast.listenToday')
  if (podcastStore.isTodayPodcastInProgress) return t('podcast.generatingToday')
  if (podcastStore.todayPodcastStatus === 'failed') return t('podcast.retryGenerate')
  return latestPodcast.value ? t('podcast.generate') : t('podcast.generateFirst')
})

const playAll = () => {
  queueStore.playAll()
}

const openArticle = (article) => {
  if (!article?.url) return
  // 与 FeedView 保持一致：sessionStorage 备份 + state 传递，路由参数为 URL 编码后的文章地址
  try {
    sessionStorage.setItem(`article_${encodeURIComponent(article.url)}`, JSON.stringify(article))
  } catch (_) {}
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
        source: article.source
      }
    }
  })
}

const onQueuePlayButton = (article, index) => {
  // 正在播放的条目：按钮切换播放/暂停；其余条目：从该条开始播放整个队列
  if (isQueueItemPlaying(article)) {
    playerStore.togglePlayPause()
    return
  }
  playerStore.playFromList([...queueStore.queue], index)
}

const removeQueueItem = (index) => {
  queueStore.removeFromQueue(index)
}

const clearQueue = async () => {
  try {
    await showConfirmDialog({
      title: t('common.hint'),
      message: t('listen.clearQueueConfirm')
    })
    queueStore.clearQueue()
    showToast(t('common.cleared'))
  } catch (_) {}
}

const isQueueItemPlaying = (article) => {
  if (!playerStore.currentArticle) return false
  return playerStore.currentArticle.url === article.url
}

const resumePlayback = async () => {
  if (playerStore.currentArticle && !playerStore.isPlaying && !playerStore.isPaused) {
    await playerStore.playArticle(playerStore.currentArticle)
    // 如果 playArticle 失败（内容获取失败、离线等），所有状态仍为 false
    if (!playerStore.isPlaying && !playerStore.isPaused && !playerStore.isLoadingAudio) {
      showToast(t('player.resumeFailed'))
      return
    }
  } else if (playerStore.isPaused) {
    playerStore.togglePlayPause()
  }
  router.push({ name: 'player' })
}

const onGenerate = async () => {
  if (generating.value) return
  generating.value = true
  try {
    const result = await podcastStore.generatePodcast()
    if (result.status === 'completed') {
      showToast(t('podcast.alreadyGenerated'))
    } else if (result.status === 'pending' || result.status === 'generating') {
      showToast(t('podcast.generateInProgress'))
    } else {
      showToast(t('podcast.generateStarted'))
    }
  } catch (error) {
    const detail = error.response?.data?.detail
    const message = (typeof detail === 'string' ? detail : null)
      || error.response?.data?.message
      || error.detail
      || t('podcast.generateFailed')
    showToast(message)
  } finally {
    generating.value = false
  }
}

const onPodcastAction = () => {
  if (podcastStore.isTodayPodcastCompleted && todayPodcast.value) {
    viewPodcast(todayPodcast.value, true)
  } else if (podcastStore.isTodayPodcastInProgress) {
    showToast(t('podcast.generateInProgress'))
  } else {
    onGenerate()
  }
}

const viewPodcast = (podcast, autoPlay = false) => {
  if (podcast.generation_status === 'completed') {
    router.push({
      name: 'podcast-detail',
      params: { id: podcast.id },
      state: { autoPlay }
    })
  } else {
    showToast(t('podcast.statusToast', { status: getStatusText(podcast.generation_status) }))
  }
}

const getStatusText = (status) => {
  const statusMap = {
    pending: t('podcast.pending'),
    generating: t('podcast.processing'),
    completed: t('podcast.completed'),
    failed: t('podcast.failed')
  }
  return statusMap[status] || status
}

const formatDuration = (seconds) => {
  if (!seconds) return t('common.unknown')
  const minutes = Math.floor(seconds / 60)
  const secs = seconds % 60
  return `${minutes}:${secs.toString().padStart(2, '0')}`
}

const formatDate = (dateString) => {
  if (!dateString) return t('common.unknown')
  const date = new Date(dateString)
  const now = new Date()
  const diff = now - date
  const days = Math.floor(diff / (1000 * 60 * 60 * 24))
  if (days === 0) return t('common.today')
  if (days === 1) return t('common.yesterday')
  if (days < 7) return t('common.daysAgo', { n: days })
  return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

const getSourceName = (sourceUrl) => {
  if (!sourceUrl) return ''
  return resolveSourceName(feedStore.feeds, sourceUrl) || ''
}

const onRefresh = async () => {
  refreshing.value = true
  try {
    await podcastStore.fetchPodcasts()
    showToast(t('common.refreshSuccess'))
  } catch (_) {}
  finally {
    refreshing.value = false
  }
}
</script>

<template>
  <div class="listen-view">
    <van-nav-bar :title="$t('nav.listen')" fixed placeholder />

    <van-pull-refresh v-model="refreshing" @refresh="onRefresh">
      <main class="listen-content">
        <section class="listen-hero">
          <p class="section-kicker">{{ $t('listen.continueKicker') }}</p>
          <h1>{{ playerStore.currentArticle?.title || $t('listen.readyHeadline') }}</h1>
          <p>
            {{ playerStore.currentArticle ? $t('listen.elapsedLabel', { time: formatDuration(Math.floor(playerStore.currentTime)) }) : $t('listen.noCurrentArticleCopy') }}
          </p>
          <div class="hero-actions">
            <van-button
              round
              type="primary"
              :disabled="!playerStore.currentArticle"
              @click="resumePlayback"
            >
              {{ playerStore.currentArticle ? $t('podcast.resume') : $t('listen.openPlayer') }}
            </van-button>
            <van-button round plain class="soft-button" @click="router.push({ name: 'feed' })">
              {{ $t('listen.addFromFeed') }}
            </van-button>
          </div>
        </section>

        <section class="listen-card">
          <div class="card-head">
            <div>
              <p class="section-kicker">{{ $t('listen.yourQueue') }}</p>
              <h2>{{ $t('listen.queueSummary', { count: queueStore.length, minutes: queueMinutes }) }}</h2>
            </div>
            <van-button v-if="!queueStore.isEmpty" size="small" round type="primary" @click="playAll">
              {{ $t('listen.playAll') }}
            </van-button>
          </div>

          <div v-if="queueStore.isEmpty" class="empty-state">
            <p>{{ $t('listen.queueEmptyHint') }}</p>
            <van-button round plain class="soft-button" @click="router.push({ name: 'feed' })">
              {{ $t('listen.browseFeed') }}
            </van-button>
          </div>

          <div v-else class="queue-list">
            <van-swipe-cell
              v-for="(article, index) in queueStore.queue"
              :key="article.url"
            >
              <div
                class="queue-item"
                :class="{ playing: isQueueItemPlaying(article) }"
                @click="openArticle(article)"
              >
                <span class="queue-index">{{ index + 1 }}</span>
                <div class="queue-body">
                  <strong>{{ article.title }}</strong>
                  <span v-if="getSourceName(article.source)">{{ getSourceName(article.source) }}</span>
                </div>
                <button
                  class="queue-play-btn"
                  :aria-label="$t('listen.playFromHere')"
                  @click.stop="onQueuePlayButton(article, index)"
                >
                  <van-icon
                    :name="isQueueItemPlaying(article) && playerStore.isPlaying ? 'pause' : 'play'"
                    size="18"
                  />
                </button>
              </div>
              <template #right>
                <van-button square type="danger" class="queue-delete-btn" @click="removeQueueItem(index)">
                  {{ $t('common.delete') }}
                </van-button>
              </template>
            </van-swipe-cell>
            <button class="clear-button" @click="clearQueue">{{ $t('listen.clearQueue') }}</button>
          </div>
        </section>

        <section ref="podcastSectionRef" class="listen-card listen-card--accent">
          <div class="card-head">
            <div>
              <p class="section-kicker">{{ $t('listen.todaysRecap') }}</p>
              <h2>{{ $t('listen.recapHeadline') }}</h2>
            </div>
          </div>

          <div v-if="latestPodcast" class="podcast-highlight" @click="viewPodcast(latestPodcast)">
            <div class="podcast-mark">▶</div>
            <div>
              <strong>{{ latestPodcast.title }}</strong>
              <p>
                {{ getStatusText(latestPodcast.generation_status) }}
                <span v-if="latestPodcast.duration"> · {{ formatDuration(latestPodcast.duration) }}</span>
                · {{ formatDate(latestPodcast.created_at) }}
              </p>
            </div>
          </div>

          <div v-else class="empty-state">
            <p>{{ $t('podcast.empty') }}</p>
          </div>

          <van-button
            round
            type="primary"
            :loading="podcastActionLoading"
            :disabled="podcastActionDisabled"
            :loading-text="$t('podcast.generatingToday')"
            @click="onPodcastAction"
          >
            {{ podcastActionLabel }}
          </van-button>
        </section>

        <section v-if="podcastStore.podcasts.length > 1" class="listen-card">
          <p class="section-kicker">{{ $t('listen.earlier') }}</p>
          <div class="earlier-list">
            <div
              v-for="podcast in podcastStore.podcasts.slice(1, 4)"
              :key="podcast.id"
              class="earlier-item"
              @click="viewPodcast(podcast)"
            >
              <strong>{{ podcast.title }}</strong>
              <span>{{ formatDate(podcast.created_at) }}</span>
            </div>
          </div>
        </section>

        <van-loading v-if="podcastLoading && podcastStore.podcasts.length === 0" class="loading" type="spinner">
          {{ $t('common.loading') }}
        </van-loading>
      </main>
    </van-pull-refresh>
  </div>
</template>

<style scoped>
.listen-view {
  min-height: 100vh;
  background: linear-gradient(180deg, var(--readaria-paper) 0%, #f2eadf 100%);
  padding-bottom: calc(50px + env(safe-area-inset-bottom, 0px) + 20px);
  color: var(--readaria-ink);
}

.listen-content {
  padding: 14px 12px 24px;
  display: grid;
  gap: 14px;
}

.listen-hero,
.listen-card {
  border: 1px solid var(--readaria-border);
  border-radius: 26px;
  background: rgba(255, 252, 248, 0.9);
  box-shadow: 0 16px 34px rgba(66, 49, 33, 0.08);
  padding: 18px;
}

.listen-card--accent {
  background: linear-gradient(180deg, rgba(199, 91, 57, 0.12), rgba(255, 252, 248, 0.92));
}

.section-kicker {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.14em;
  color: #9a674f;
  margin: 0 0 8px;
}

.listen-hero h1,
.listen-card h2 {
  font-family: var(--readaria-serif);
  font-weight: 600;
  color: var(--readaria-ink);
}

.listen-hero h1 {
  font-size: 32px;
  line-height: 1.05;
  margin: 0 0 10px;
}

.listen-card h2 {
  font-size: 24px;
  line-height: 1.12;
  margin: 0;
}

.listen-hero p,
.empty-state p,
.podcast-highlight p {
  color: var(--readaria-muted);
  line-height: 1.6;
  margin: 0;
}

.hero-actions,
.card-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  flex-wrap: wrap;
}

.hero-actions {
  margin-top: 16px;
}

.soft-button {
  background: rgba(255, 252, 248, 0.76) !important;
  border-color: var(--readaria-border) !important;
  color: var(--readaria-navy) !important;
}

.empty-state {
  display: grid;
  gap: 12px;
  margin-top: 12px;
}

.queue-list,
.earlier-list {
  display: grid;
  gap: 10px;
  margin-top: 14px;
}

.queue-item,
.earlier-item,
.podcast-highlight {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 0;
  border-bottom: 1px solid rgba(23, 33, 48, 0.08);
}

/* 滑动删除时遮挡底层操作按钮，需要不透明背景 */
.queue-list .queue-item {
  background: #fdf9f3;
}

.queue-play-btn {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  border: 1px solid var(--readaria-border);
  background: rgba(255, 252, 248, 0.9);
  color: var(--readaria-accent);
  display: grid;
  place-items: center;
  flex-shrink: 0;
  cursor: pointer;
  padding: 0;
}

.queue-delete-btn {
  height: 100%;
}

.queue-item.playing {
  color: var(--readaria-accent);
}

.queue-index {
  width: 22px;
  color: #9a674f;
  flex-shrink: 0;
}

.queue-body {
  flex: 1;
  display: grid;
  gap: 4px;
  min-width: 0;
}

.queue-body strong,
.earlier-item strong,
.podcast-highlight strong {
  color: var(--readaria-ink);
  line-height: 1.35;
}

.queue-body span,
.earlier-item span {
  color: var(--readaria-muted);
  font-size: 12px;
}

.clear-button {
  border: 0;
  background: transparent;
  color: #9a674f;
  font-size: 13px;
  width: fit-content;
  padding: 8px 0;
}

.podcast-mark {
  width: 44px;
  height: 44px;
  border-radius: 999px;
  background: var(--readaria-accent-soft);
  color: #b55333;
  display: grid;
  place-items: center;
  flex-shrink: 0;
}

.podcast-highlight {
  margin: 12px 0;
}

.earlier-item {
  justify-content: space-between;
}

.loading {
  margin: 20px auto;
}
</style>
