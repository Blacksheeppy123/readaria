<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { showToast } from 'vant'
import api from '@/api/request'

const route = useRoute()
const router = useRouter()
const { t } = useI18n()
const shareToken = route.params.token

const podcast = ref(null)
const loading = ref(true)
const error = ref(null)
const audioUrl = ref(null)
const isPlaying = ref(false)
const currentTime = ref(0)
const duration = ref(0)
const audioRef = ref(null)
const showRegisterModal = ref(false)

const PREVIEW_SECONDS = 120
const STORAGE_KEY = `podcast_preview_${shareToken}`

const cumulativeListened = ref(0)
try {
  const stored = sessionStorage.getItem(STORAGE_KEY)
  if (stored) cumulativeListened.value = parseInt(stored, 10) || 0
} catch (_) {}

const isPreviewExpired = computed(() => cumulativeListened.value >= PREVIEW_SECONDS)

let lastTimeUpdate = 0

const formatTime = (seconds) => {
  if (!seconds || isNaN(seconds)) return '00:00'
  const mins = Math.floor(seconds / 60)
  const secs = Math.floor(seconds % 60)
  return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`
}

const formatDate = (dateStr) => {
  if (!dateStr) return ''
  const d = new Date(dateStr)
  return d.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })
}

const loadPodcast = async () => {
  loading.value = true
  error.value = null
  try {
    const response = await api.get(`/api/v1/share/podcast-meta/${shareToken}`, { silent: true })
    podcast.value = response
  } catch (err) {
    console.error('Failed to load podcast meta:', err)
    error.value = t('sharePodcast.notFound')
  } finally {
    loading.value = false
  }
}

const loadAudioUrl = async () => {
  try {
    const response = await api.get(`/api/v1/share/podcast-audio/${shareToken}`, { silent: true })
    if (response.audio_url) {
      const baseUrl = import.meta.env.VITE_API_BASE_URL || ''
      audioUrl.value = `${baseUrl}${response.audio_url}`
    }
  } catch (err) {
    console.error('Failed to load audio URL:', err)
  }
}

const togglePlay = () => {
  if (!audioRef.value) return

  if (isPreviewExpired.value) {
    showRegisterModal.value = true
    return
  }

  if (isPlaying.value) {
    audioRef.value.pause()
  } else {
    audioRef.value.play().catch(() => {})
  }
}

const onTimeUpdate = () => {
  if (!audioRef.value) return
  const current = audioRef.value.currentTime || 0
  currentTime.value = current

  if (lastTimeUpdate > 0 && current > lastTimeUpdate) {
    const delta = current - lastTimeUpdate
    cumulativeListened.value += delta
    try {
      sessionStorage.setItem(STORAGE_KEY, String(Math.floor(cumulativeListened.value)))
    } catch (_) {}

    if (cumulativeListened.value >= PREVIEW_SECONDS && isPlaying.value) {
      audioRef.value.pause()
      showRegisterModal.value = true
    }
  }
  lastTimeUpdate = current
}

const onPlay = () => {
  isPlaying.value = true
  lastTimeUpdate = audioRef.value?.currentTime || 0
}

const onPause = () => {
  isPlaying.value = false
  lastTimeUpdate = 0
}

const onLoadedMetadata = () => {
  duration.value = audioRef.value?.duration || 0
}

const onSeek = (value) => {
  if (!audioRef.value || duration.value <= 0) return
  const time = (value / 100) * duration.value
  audioRef.value.currentTime = time
}

const onEnded = () => {
  isPlaying.value = false
  currentTime.value = 0
  lastTimeUpdate = 0
}

const goToApp = () => {
  router.push('/')
}

const goToRegister = () => {
  window.open('https://github.com/Blacksheeppy123/readaria', '_blank', 'noopener')
}

const closeRegisterModal = () => {
  showRegisterModal.value = false
}

onMounted(() => {
  if (!shareToken) {
    error.value = t('sharePodcast.invalidLink')
    loading.value = false
    return
  }
  loadPodcast()
  loadAudioUrl()
})

onUnmounted(() => {
  if (audioRef.value) {
    audioRef.value.pause()
  }
})

const sliderValue = computed(() => {
  if (duration.value <= 0) return 0
  return (currentTime.value / duration.value) * 100
})

const metaLabel = computed(() => {
  if (!podcast.value) return ''
  const parts = []
  parts.push(t('sharePodcast.dailyDigest'))
  if (podcast.value.created_at) {
    parts.push(formatDate(podcast.value.created_at))
  }
  if (podcast.value.duration) {
    parts.push(formatTime(podcast.value.duration))
  }
  return parts.join(' · ')
})
</script>

<template>
  <div class="share-podcast-page">
    <div class="sp-header">
      <div class="sp-logo" @click="goToApp">
        <span class="sp-logo-icon">◆</span>
        <span class="sp-logo-text">Readaria</span>
      </div>
    </div>

    <div v-if="loading" class="sp-loading">
      <van-loading type="spinner" size="32" />
    </div>

    <div v-else-if="error" class="sp-error">
      <van-icon name="warning-o" size="48" color="#999" />
      <p>{{ error }}</p>
      <van-button type="primary" round @click="goToApp">{{ $t('sharePodcast.openApp') }}</van-button>
    </div>

    <div v-else-if="podcast" class="sp-content">
      <div class="sp-cover-wrap">
        <div class="sp-cover">
          <van-icon v-if="!podcast.cover_art_url" name="play-circle-o" size="60" />
          <img v-else :src="podcast.cover_art_url" alt="Podcast cover" />
        </div>
      </div>

      <div class="sp-info">
        <h1 class="sp-title">{{ podcast.title }}</h1>
        <p class="sp-meta">{{ metaLabel }}</p>
        <p v-if="podcast.description" class="sp-desc">{{ podcast.description }}</p>
      </div>

      <div class="sp-player">
        <audio
          ref="audioRef"
          :src="audioUrl"
          preload="metadata"
          @play="onPlay"
          @pause="onPause"
          @timeupdate="onTimeUpdate"
          @loadedmetadata="onLoadedMetadata"
          @ended="onEnded"
        />

        <div class="sp-progress">
          <span class="sp-time">{{ formatTime(currentTime) }}</span>
          <van-slider
            :model-value="sliderValue"
            :max="100"
            @change="onSeek"
            button-size="14px"
            active-color="var(--readaria-accent)"
            :disabled="!audioUrl"
          />
          <span class="sp-time">{{ formatTime(duration || podcast.duration) }}</span>
        </div>

        <div class="sp-controls">
          <div class="sp-play-btn" @click="togglePlay">
            <van-icon
              :name="isPlaying ? 'pause-circle' : 'play-circle'"
              size="56"
              color="var(--readaria-accent)"
            />
          </div>
        </div>

        <div v-if="isPreviewExpired" class="sp-preview-badge">
          {{ $t('sharePodcast.previewLimit') }}
        </div>
      </div>

      <div v-if="podcast.stories?.length" class="sp-stories">
        <h3 class="sp-section-title">{{ $t('sharePodcast.storiesTitle') }}</h3>
        <div class="sp-story-list">
          <a
            v-for="(story, idx) in podcast.stories"
            :key="idx"
            class="sp-story-item"
            :href="story.article_url"
            target="_blank"
            rel="noopener noreferrer"
          >
            <span class="sp-story-num">{{ idx + 1 }}</span>
            <span class="sp-story-title">{{ story.title }}</span>
            <van-icon name="arrow" size="14" class="sp-story-arrow" />
          </a>
        </div>
      </div>
    </div>

    <div class="sp-cta-bar">
      <van-button
        type="primary"
        round
        block
        icon="play-circle-o"
        @click="goToRegister"
      >
        {{ $t('sharePodcast.selfhostButton') }}
      </van-button>
    </div>

    <van-dialog
      v-model:show="showRegisterModal"
      :title="$t('sharePodcast.selfhostTitle')"
      show-cancel-button
      :confirm-button-text="$t('sharePodcast.selfhostButton')"
      :cancel-button-text="$t('sharePodcast.modalCancel')"
      @confirm="goToRegister"
      @cancel="closeRegisterModal"
    >
      <div class="sp-modal-body">
        <p>{{ $t('sharePodcast.selfhostBody') }}</p>
      </div>
    </van-dialog>
  </div>
</template>

<style scoped>
.share-podcast-page {
  min-height: 100vh;
  background: linear-gradient(180deg, var(--readaria-paper) 0%, #f2eadf 100%);
  padding-bottom: calc(80px + env(safe-area-inset-bottom));
}
.sp-header {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 16px;
}
.sp-logo {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
}
.sp-logo-icon {
  font-size: 20px;
  color: var(--readaria-accent);
}
.sp-logo-text {
  font-size: 18px;
  font-weight: 700;
  color: var(--readaria-ink);
}
.sp-loading {
  display: flex;
  justify-content: center;
  align-items: center;
  height: 60vh;
}
.sp-error {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 60vh;
  gap: 16px;
  padding: 24px;
  text-align: center;
  color: var(--readaria-muted);
}
.sp-content {
  padding: 0 20px 24px;
}
.sp-cover-wrap {
  display: flex;
  justify-content: center;
  padding: 16px 0 24px;
}
.sp-cover {
  width: 160px;
  height: 160px;
  border-radius: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, var(--readaria-accent) 0%, #b55333 100%);
  color: white;
  overflow: hidden;
  box-shadow: 0 8px 24px rgba(0,0,0,0.12);
}
.sp-cover img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.sp-info {
  text-align: center;
  margin-bottom: 24px;
}
.sp-title {
  font-size: 22px;
  font-weight: 700;
  margin: 0 0 8px;
  color: var(--readaria-ink);
  line-height: 1.3;
}
.sp-meta {
  font-size: 13px;
  color: var(--readaria-muted);
  margin: 0 0 12px;
}
.sp-desc {
  font-size: 14px;
  color: var(--readaria-muted);
  line-height: 1.6;
  margin: 0;
}
.sp-player {
  background: rgba(255, 252, 248, 0.9);
  border-radius: 20px;
  padding: 20px;
  margin-bottom: 24px;
  border: 1px solid var(--readaria-border);
}
.sp-progress {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
}
.sp-time {
  font-size: 12px;
  color: var(--readaria-muted);
  min-width: 40px;
  text-align: center;
  font-variant-numeric: tabular-nums;
}
.sp-controls {
  display: flex;
  justify-content: center;
}
.sp-play-btn {
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 64px;
  height: 64px;
}
.sp-play-btn:active {
  opacity: 0.7;
}
.sp-preview-badge {
  text-align: center;
  font-size: 12px;
  color: var(--readaria-accent);
  margin-top: 12px;
  font-weight: 500;
}
.sp-stories {
  margin-bottom: 24px;
}
.sp-section-title {
  font-size: 16px;
  font-weight: 600;
  margin: 0 0 12px;
  color: var(--readaria-ink);
}
.sp-story-list {
  background: rgba(255, 252, 248, 0.9);
  border-radius: 16px;
  border: 1px solid var(--readaria-border);
  overflow: hidden;
}
.sp-story-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 16px;
  border-bottom: 1px solid rgba(0,0,0,0.04);
  text-decoration: none;
  cursor: pointer;
  transition: background 0.15s;
}
.sp-story-item:last-child {
  border-bottom: none;
}
.sp-story-item:active {
  background: rgba(0,0,0,0.03);
}
.sp-story-arrow {
  color: var(--readaria-muted);
  flex-shrink: 0;
}
.sp-story-num {
  font-size: 13px;
  font-weight: 700;
  color: var(--readaria-accent);
  min-width: 24px;
  text-align: center;
}
.sp-story-title {
  font-size: 14px;
  color: var(--readaria-ink);
  line-height: 1.4;
  flex: 1;
}
.sp-cta-bar {
  position: fixed;
  bottom: 0;
  left: 0;
  right: 0;
  padding: 12px 20px calc(12px + env(safe-area-inset-bottom));
  background: rgba(255, 252, 248, 0.95);
  backdrop-filter: blur(12px);
  border-top: 1px solid var(--readaria-border);
  z-index: 100;
}
.sp-modal-body {
  padding: 8px 24px 24px;
  text-align: center;
  color: var(--readaria-muted);
  font-size: 14px;
  line-height: 1.6;
}
:deep(.van-slider) {
  flex: 1;
}
</style>
