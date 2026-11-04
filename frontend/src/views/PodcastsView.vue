<script setup>
import { computed, ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { usePodcastStore } from '@/stores/podcastStore'
import { showToast, showConfirmDialog } from 'vant'

const { t } = useI18n()
const router = useRouter()
const podcastStore = usePodcastStore()

const loading = ref(false)
const refreshing = ref(false)
const generating = ref(false)
const generateButtonDisabled = computed(() => generating.value || podcastStore.isTodayPodcastInProgress)
const generateButtonLoading = computed(() => generating.value || podcastStore.isTodayPodcastInProgress)
const generateButtonLabel = computed(() => {
  if (podcastStore.isTodayPodcastCompleted) return t('podcast.listenToday')
  if (podcastStore.isTodayPodcastInProgress) return t('podcast.generatingToday')
  if (podcastStore.todayPodcastStatus === 'failed') return t('podcast.retryGenerate')
  return t('podcast.generate')
})

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

  return date.toLocaleDateString(undefined, {
    month: 'short',
    day: 'numeric'
  })
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

const getStatusColor = (status) => {
  const colorMap = {
    pending: '#ff9800',
    generating: '#2196f3',
    completed: '#4caf50',
    failed: '#f44336'
  }
  return colorMap[status] || '#999'
}

const loadPodcasts = async () => {
  loading.value = true
  try {
    await podcastStore.fetchPodcasts()
  } catch (error) {
    showToast(t('podcast.loadFailed'))
  } finally {
    loading.value = false
  }
}

const onRefresh = async () => {
  refreshing.value = true
  try {
    await podcastStore.fetchPodcasts()
    showToast(t('common.refreshSuccess'))
  } catch (error) {
    showToast(t('common.refreshFailed'))
  } finally {
    refreshing.value = false
  }
}

const onGenerate = async () => {
  if (podcastStore.isTodayPodcastCompleted && podcastStore.todayPodcast) {
    router.push({ name: 'podcast-detail', params: { id: podcastStore.todayPodcast.id } })
    return
  }
  if (generating.value || podcastStore.isTodayPodcastInProgress) return
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
    const detail = error.response?.data?.detail || error.detail || t('podcast.generateFailed')
    showToast(detail)
  } finally {
    generating.value = false
  }
}

let longPressTimer = null
const longPressTriggered = ref(false)

const onTouchStart = (podcast) => {
  longPressTriggered.value = false
  longPressTimer = setTimeout(() => {
    longPressTriggered.value = true
    onLongPress(podcast)
  }, 600)
}

const onTouchEnd = () => {
  clearTimeout(longPressTimer)
}

const onTouchMove = () => {
  clearTimeout(longPressTimer)
}

const viewPodcast = (podcast) => {
  if (longPressTriggered.value) {
    longPressTriggered.value = false
    return
  }
  if (podcast.generation_status === 'completed') {
    router.push({
      name: 'podcast-detail',
      params: { id: podcast.id }
    })
  } else {
    showToast(t('podcast.statusToast', { status: getStatusText(podcast.generation_status) }))
  }
}

const onLongPress = (podcast) => {
  showConfirmDialog({
    title: t('podcast.deleteConfirmTitle'),
    message: t('podcast.deleteConfirmMessage', { title: podcast.title }),
    confirmButtonColor: '#f44336',
  }).then(async () => {
    try {
      await podcastStore.deletePodcast(podcast.id)
      showToast(t('common.deleted'))
    } catch {
      showToast(t('common.deleteFailed'))
    }
  }).catch(() => {})
}

onMounted(() => {
  loadPodcasts()
})
</script>

<template>
  <div class="podcasts-view">
    <van-nav-bar :title="$t('podcast.title')" fixed placeholder>
      <template #right>
        <van-button
          type="primary"
          size="small"
          @click="onGenerate"
          :loading="generateButtonLoading"
          :disabled="generateButtonDisabled"
          :loading-text="$t('podcast.generatingToday')"
        >
          {{ generateButtonLabel }}
        </van-button>
      </template>
    </van-nav-bar>

    <van-pull-refresh v-model="refreshing" @refresh="onRefresh">
      <div class="content">
        <van-empty
          v-if="!loading && podcastStore.podcasts.length === 0"
          :description="$t('podcast.empty')"
        >
          <van-button
            type="primary"
            :loading="generateButtonLoading"
            :disabled="generateButtonDisabled"
            :loading-text="$t('podcast.generatingToday')"
            @click="onGenerate"
          >
            {{ $t('podcast.generateFirst') }}
          </van-button>
        </van-empty>

        <div v-else class="podcast-list">
          <van-card
            v-for="podcast in podcastStore.podcasts"
            :key="podcast.id"
            :title="podcast.title"
            :desc="podcast.description"
            @click="viewPodcast(podcast)"
            @touchstart="onTouchStart(podcast)"
            @touchend="onTouchEnd"
            @touchmove="onTouchMove"
            class="podcast-card"
          >
            <template #thumb>
              <div class="podcast-thumb">
                <van-icon name="play-circle-o" size="40" />
              </div>
            </template>

            <template #tags>
              <van-tag
                :color="getStatusColor(podcast.generation_status)"
                size="medium"
              >
                {{ getStatusText(podcast.generation_status) }}
              </van-tag>
            </template>

            <template #footer>
              <div class="podcast-meta">
                <span v-if="podcast.duration" class="meta-item">
                  <van-icon name="clock-o" />
                  {{ formatDuration(podcast.duration) }}
                </span>
                <span class="meta-item">
                  <van-icon name="calendar-o" />
                  {{ formatDate(podcast.created_at) }}
                </span>
                <span v-if="podcast.play_count > 0" class="meta-item">
                  <van-icon name="play-circle-o" />
                  {{ $t('podcast.playCount', { count: podcast.play_count }) }}
                </span>
              </div>
            </template>
          </van-card>
        </div>

        <van-loading
          v-if="loading && podcastStore.podcasts.length === 0"
          class="loading"
          type="spinner"
        >
          {{ $t('common.loading') }}
        </van-loading>
      </div>
    </van-pull-refresh>
  </div>
</template>

<style scoped>
.podcasts-view {
  height: 100vh;
  display: flex;
  flex-direction: column;
  background-color: #f5f5f5;
}

.content {
  flex: 1;
  overflow-y: auto;
  -webkit-overflow-scrolling: touch;
}

.podcast-list {
  padding: 12px;
  padding-bottom: calc(50px + env(safe-area-inset-bottom, 0px) + 20px);
}

.podcast-card {
  margin-bottom: 12px;
  border-radius: 8px;
  overflow: hidden;
  cursor: pointer;
  transition: transform 0.2s;
}

.podcast-card:active {
  transform: scale(0.98);
}

.podcast-thumb {
  width: 80px;
  height: 80px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  border-radius: 8px;
}

.podcast-meta {
  display: flex;
  gap: 12px;
  font-size: 12px;
  color: #999;
  margin-top: 8px;
}

.meta-item {
  display: flex;
  align-items: center;
  gap: 4px;
}

.loading {
  display: flex;
  justify-content: center;
  padding: 40px 0;
}

:deep(.van-card__title) {
  font-size: 16px;
  font-weight: 600;
  margin-bottom: 4px;
}

:deep(.van-card__desc) {
  font-size: 13px;
  color: #666;
  line-height: 1.5;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
</style>
