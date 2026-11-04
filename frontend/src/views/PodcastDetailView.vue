<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { usePodcastStore } from '@/stores/podcastStore'
import { usePodcastPlayerStore } from '@/stores/podcastPlayerStore'
import { showToast } from 'vant'
import ShareSheet from '@/components/ShareSheet.vue'

const router = useRouter()
const route = useRoute()
const { t } = useI18n()
const podcastStore = usePodcastStore()
const podcastPlayer = usePodcastPlayerStore()

const podcastId = ref(route.params.id)
const podcast = ref(null)
const loading = ref(false)
const audioUrl = ref(null)
const audioError = ref(false)
const showShareSheet = ref(false)
const shareToken = ref(null)
const generatingShare = ref(false)

const shareUrl = computed(() => {
  if (shareToken.value) {
    return `${window.location.origin}/podcast-preview/${shareToken.value}`
  }
  return ''
})

// 当前播客是否正在播放
const isCurrentPodcast = computed(() =>
  podcastPlayer.currentPodcast?.id == podcastId.value
)
const playing = computed(() => isCurrentPodcast.value && podcastPlayer.isPlaying)
const paused = computed(() => isCurrentPodcast.value && podcastPlayer.isPaused)
const playerLoading = computed(() => isCurrentPodcast.value && podcastPlayer.isLoading)
const currentTime = computed(() => isCurrentPodcast.value ? podcastPlayer.currentTime : 0)
const duration = computed(() => isCurrentPodcast.value ? podcastPlayer.duration : 0)

// 进度条滑块值（0-100）
const sliderValue = computed({
  get: () => duration.value > 0 ? (currentTime.value / duration.value) * 100 : 0,
  set: () => {} // 由 onSeek 处理
})

// 格式化时间
const formatTime = (seconds) => {
  if (!seconds || isNaN(seconds)) return '00:00'
  const mins = Math.floor(seconds / 60)
  const secs = Math.floor(seconds % 60)
  return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`
}

// 倍速选项
const rateOptions = [0.75, 1.0, 1.25, 1.5, 2.0]

// 加载播客详情
const loadPodcast = async () => {
  loading.value = true
  try {
    const data = await podcastStore.getPodcastDetail(podcastId.value)
    podcast.value = data
    try {
      audioUrl.value = await podcastStore.getPodcastAudioUrl(podcastId.value)
    } catch (audioErr) {
      console.error('加载音频 URL 失败:', audioErr)
      audioError.value = true
      showToast(t('podcast.audioLoadFailed'))
    }
  } catch (error) {
    showToast(t('common.loadFailed'))
    router.back()
  } finally {
    loading.value = false
  }
}

// 播放/暂停
const togglePlay = async () => {
  if (audioError.value) {
    showToast(t('podcast.audioUnavailable'))
    return
  }
  if (!audioUrl.value) {
    showToast(t('podcast.audioNotLoaded'))
    return
  }
  if (isCurrentPodcast.value && (playing.value || paused.value)) {
    podcastPlayer.togglePlayPause()
  } else {
    await podcastPlayer.play(podcast.value, audioUrl.value)
  }
}

// 进度条拖动
const onSeek = (value) => {
  if (!isCurrentPodcast.value || duration.value <= 0) return
  const time = (value / 100) * duration.value
  podcastPlayer.seekTo(time)
}

// 跳转到文章对应的时间点
const jumpToArticle = (article) => {
  if (article.start_time === null || article.start_time === undefined) return
  if (!isCurrentPodcast.value) {
    podcastPlayer.play(podcast.value, audioUrl.value).then(() => {
      podcastPlayer.seekTo(article.start_time)
    })
  } else {
    podcastPlayer.seekTo(article.start_time)
    if (!playing.value && !paused.value) togglePlay()
  }
}

// 查看文章详情
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

const openConversation = () => {
  router.push({ name: 'podcast-chat', params: { id: podcastId.value } })
}

const openShare = async () => {
  if (shareToken.value) {
    showShareSheet.value = true
    return
  }
  generatingShare.value = true
  try {
    const token = await podcastStore.createShareLink(podcastId.value)
    shareToken.value = token
    showShareSheet.value = true
  } catch {
    showToast(t('share.generateFailed') || 'Failed to generate share link')
  } finally {
    generatingShare.value = false
  }
}

onMounted(async () => {
  await loadPodcast()
  if (history.state?.autoPlay) {
    setTimeout(() => {
      if (!playing.value && !playerLoading.value) {
        togglePlay()
      }
    }, 300)
  }
})
</script>

<template>
  <div class="podcast-detail">
    <van-nav-bar :title="$t('podcast.detail')" left-arrow @click-left="router.back()" fixed placeholder>
      <template #right>
        <van-icon
          v-if="podcast"
          name="share-o"
          size="20"
          :class="{ 'share-loading': generatingShare }"
          @click="openShare"
        />
      </template>
    </van-nav-bar>

    <div v-if="loading" class="loading-container">
      <van-loading type="spinner">{{ $t('common.loading') }}</van-loading>
    </div>

    <div v-else-if="podcast" class="content">
      <!-- 播客信息 -->
      <div class="podcast-header">
        <div class="podcast-cover">
          <van-icon name="play-circle-o" size="60" />
        </div>
        <h2 class="podcast-title">{{ podcast.title }}</h2>
        <p class="podcast-description">{{ podcast.description }}</p>
        <div class="podcast-meta">
          <span>{{ formatTime(duration || podcast.duration) }}</span>
          <span v-if="podcast.play_count > 0">{{ $t('podcast.playCount', { count: podcast.play_count }) }}</span>
        </div>
      </div>

      <!-- 播放器 -->
      <div class="player-section">
        <div class="progress-bar">
          <span class="time">{{ formatTime(currentTime) }}</span>
          <van-slider
            :model-value="sliderValue"
            :max="100"
            @change="onSeek"
            button-size="16px"
            active-color="var(--readaria-accent)"
          />
          <span class="time">{{ formatTime(duration || podcast.duration) }}</span>
        </div>

        <!-- 主控制区 -->
        <div class="main-controls">
          <div class="control-btn" @click="podcastPlayer.skipBackward(15)">
            <van-icon name="revoke" size="28" />
            <span class="control-label">15s</span>
          </div>
          <div class="play-btn" @click="togglePlay">
            <van-loading v-if="playerLoading" type="spinner" size="32" color="#fff" />
            <van-icon v-else :name="playing ? 'pause-circle' : 'play-circle'" size="52" color="var(--readaria-accent)" />
          </div>
          <div class="control-btn" @click="podcastPlayer.skipForward(30)">
            <van-icon name="share-o" size="28" />
            <span class="control-label">30s</span>
          </div>
        </div>

        <!-- 倍速控制 -->
        <div class="speed-control">
          <span class="speed-label">{{ $t('podcast.speed') }}</span>
          <div class="speed-options">
            <span
              v-for="rate in rateOptions"
              :key="rate"
              class="speed-option"
              :class="{ active: podcastPlayer.playbackRate === rate }"
              @click="podcastPlayer.setPlaybackRate(rate)"
            >{{ rate }}x</span>
          </div>
        </div>
      </div>

      <!-- 对话按钮 -->
      <div class="conversation-button">
        <van-button type="primary" size="large" round block icon="chat-o" @click="openConversation">
          {{ $t('podcast.chatWithPodcast') }}
        </van-button>
      </div>

      <!-- 文章列表 -->
      <div class="articles-section">
        <h3 class="section-title">{{ $t('podcast.relatedArticles') }}</h3>
        <van-cell-group inset>
          <van-cell
            v-for="article in podcast.articles"
            :key="article.id"
            :title="article.title"
            is-link
            @click="viewArticle(article)"
          >
            <template #label>
              <div class="article-meta">
                <span v-if="article.feed_title">{{ article.feed_title }}</span>
                <span v-if="article.start_time !== null">{{ $t('podcast.chapter', { time: formatTime(article.start_time) }) }}</span>
              </div>
            </template>
            <template #right-icon>
              <van-button
                v-if="article.start_time !== null"
                size="small" type="primary" plain
                @click.stop="jumpToArticle(article)"
              >{{ $t('podcast.jump') }}</van-button>
            </template>
          </van-cell>
        </van-cell-group>
      </div>

      <ShareSheet
        v-model:show="showShareSheet"
        :title="podcast?.title"
        :url="shareUrl"
        type="podcast"
        :description="podcast?.description"
        :stories="podcast?.articles"
      />
    </div>
  </div>
</template>

<style scoped>
.podcast-detail { min-height: 100vh; background: linear-gradient(180deg, var(--readaria-paper) 0%, #f2eadf 100%); padding-bottom: calc(80px + env(safe-area-inset-bottom)); }
.loading-container { display: flex; justify-content: center; align-items: center; height: 60vh; }
.content { padding: 16px; }
.podcast-header { text-align: center; padding: 24px 16px; background: rgba(255, 252, 248, 0.9); border-radius: 26px; margin-bottom: 16px; border: 1px solid var(--readaria-border); }
.podcast-cover { width: 120px; height: 120px; margin: 0 auto 16px; display: flex; align-items: center; justify-content: center; background: linear-gradient(135deg, var(--readaria-accent) 0%, #b55333 100%); color: white; border-radius: 12px; }
.podcast-title { font-size: 20px; font-weight: 600; margin: 0 0 8px 0; color: var(--readaria-ink); }
.podcast-description { font-size: 14px; color: var(--readaria-muted); line-height: 1.6; margin: 0 0 12px 0; }
.podcast-meta { display: flex; justify-content: center; gap: 16px; font-size: 13px; color: var(--readaria-muted); }
.player-section { background: rgba(255, 252, 248, 0.9); border-radius: 26px; padding: 20px; margin-bottom: 16px; border: 1px solid var(--readaria-border); }
.progress-bar { display: flex; align-items: center; gap: 12px; margin-bottom: 24px; }
.time { font-size: 12px; color: var(--readaria-muted); min-width: 45px; text-align: center; }
.main-controls { display: flex; justify-content: center; align-items: center; gap: 32px; margin-bottom: 20px; }
.control-btn { display: flex; flex-direction: column; align-items: center; gap: 2px; cursor: pointer; color: var(--readaria-muted); padding: 8px; }
.control-btn:active { opacity: 0.6; }
.control-label { font-size: 11px; color: var(--readaria-muted); }
.play-btn { cursor: pointer; display: flex; align-items: center; justify-content: center; width: 64px; height: 64px; }
.play-btn:active { opacity: 0.7; }
.speed-control { display: flex; align-items: center; gap: 12px; padding-top: 16px; border-top: 1px solid var(--readaria-border); }
.speed-label { font-size: 13px; color: var(--readaria-muted); flex-shrink: 0; }
.speed-options { display: flex; gap: 8px; flex-wrap: wrap; }
.speed-option { padding: 4px 12px; border-radius: 14px; font-size: 13px; color: var(--readaria-muted); background: var(--readaria-paper); cursor: pointer; transition: all 0.2s; }
.speed-option.active { background: var(--readaria-accent); color: white; }
.speed-option:active { opacity: 0.7; }
.articles-section { margin-bottom: 16px; }
.section-title { font-size: 16px; font-weight: 600; margin: 0 0 12px 0; padding: 0 4px; color: var(--readaria-ink); }
.article-meta { display: flex; gap: 12px; font-size: 12px; color: var(--readaria-muted); margin-top: 4px; }
.conversation-button { padding: 0 16px; margin: 16px 0; }
:deep(.van-slider) { flex: 1; }
.share-loading { opacity: 0.5; pointer-events: none; }
</style>
