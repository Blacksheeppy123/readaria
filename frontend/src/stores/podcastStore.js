import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { showToast } from 'vant'
import api from '@/api/request'
import i18n from '@/i18n'
import { trackPodcastGenerated } from '@/utils/analytics'

export const usePodcastStore = defineStore('podcast', () => {
  // 状态
  const podcasts = ref([])
  const selectedPodcast = ref(null)
  const loading = ref(false)
  const generationStatus = ref({})
  let statusPollTimer = null
  let statusPollAttempts = 0
  const STATUS_POLL_INTERVAL_MS = 5000
  const STATUS_POLL_MAX_ATTEMPTS = 120

  // 计算属性
  const completedPodcasts = computed(() => {
    return podcasts.value.filter(p => p.generation_status === 'completed')
  })

  const pendingPodcasts = computed(() => {
    return podcasts.value.filter(p =>
      p.generation_status === 'pending' || p.generation_status === 'generating'
    )
  })

  const latestPodcast = computed(() => podcasts.value[0] || null)

  const todayPodcast = computed(() => {
    const today = new Date().toDateString()
    return podcasts.value.find(p => {
      if (!p?.created_at) return false
      if (p.source === 'onboarding_cache') return false
      return new Date(p.created_at).toDateString() === today
    }) || null
  })

  const onboardingCachePodcast = computed(() => {
    return podcasts.value.find(p => p.source === 'onboarding_cache') || null
  })

  const todayPodcastStatus = computed(() => todayPodcast.value?.generation_status || 'none')
  const isTodayPodcastCompleted = computed(() => todayPodcastStatus.value === 'completed')
  const isTodayPodcastInProgress = computed(() =>
    todayPodcastStatus.value === 'pending' || todayPodcastStatus.value === 'generating'
  )

  let pendingIdsBeforePoll = new Set()

  const stopPodcastStatusPolling = () => {
    if (statusPollTimer) {
      clearInterval(statusPollTimer)
      statusPollTimer = null
    }
    statusPollAttempts = 0
    pendingIdsBeforePoll.clear()
  }

  const startPodcastStatusPolling = (options = {}) => {
    if (statusPollTimer) return
    const intervalMs = options.intervalMs || STATUS_POLL_INTERVAL_MS
    const maxAttempts = options.maxAttempts || STATUS_POLL_MAX_ATTEMPTS

    // 记录当前 pending 的播客 ID，用于后续检测完成状态
    pendingIdsBeforePoll = new Set(
      podcasts.value
        .filter(p => p.generation_status === 'pending' || p.generation_status === 'generating')
        .map(p => p.id)
    )

    statusPollTimer = setInterval(async () => {
      statusPollAttempts += 1
      try {
        // 轮询上下文跳过 syncPollingWithCurrentState，避免提前清除 pendingIdsBeforePoll
        await fetchPodcasts({ syncPolling: false })
      } catch (error) {
        console.warn('[PodcastStore] status polling failed:', error)
      }

      // 检测是否有之前 pending 的播客变为 completed
      const newlyCompleted = podcasts.value.filter(
        p => p.generation_status === 'completed' && pendingIdsBeforePoll.has(p.id)
      )
      if (newlyCompleted.length > 0) {
        showToast({
          message: i18n.global.t('podcast.generateSuccess') || 'Podcast ready!',
          icon: 'success',
          duration: 3000
        })
        pendingIdsBeforePoll.clear()
      } else if (pendingPodcasts.value.length > 0) {
        // 更新 pending ID 集合
        pendingIdsBeforePoll = new Set(
          pendingPodcasts.value.map(p => p.id)
        )
      }

      if (pendingPodcasts.value.length === 0 || statusPollAttempts >= maxAttempts) {
        stopPodcastStatusPolling()
      }
    }, intervalMs)
  }

  const syncPollingWithCurrentState = () => {
    if (pendingPodcasts.value.length > 0) {
      startPodcastStatusPolling()
    } else {
      stopPodcastStatusPolling()
    }
  }

  // 获取播客列表
  const fetchPodcasts = async (options = {}) => {
    loading.value = true
    try {
      const response = await api.get('/api/v1/podcasts', { silent: true, headers: { 'X-Silent': '1' } })
      // 响应拦截器已经返回 response.data，所以直接访问 podcasts
      podcasts.value = response.podcasts || []
      if (options.syncPolling !== false) {
        syncPollingWithCurrentState()
      }
      return podcasts.value
    } catch (error) {
      console.error('获取播客列表失败:', error)
      throw error
    } finally {
      loading.value = false
    }
  }

  // 生成播客（异步，不等待完成）
  const generatePodcast = async (options = {}) => {
    try {
      const language = i18n.global.locale.value || localStorage.getItem('locale') || 'zh'
      const response = await api.post('/api/v1/podcasts/generate', {
        style: options.style || 'deep_dive',
        time_range_hours: options.time_range_hours || 24,
        max_articles: options.max_articles || 10,
        language: language === 'en' ? 'en' : 'zh'
      })
      // 响应拦截器已经返回 response.data
      const podcastId = response.podcast_id

      // 立即刷新列表，显示 pending/generating/completed 状态的播客
      await fetchPodcasts()

      trackPodcastGenerated({ podcast_id: podcastId, article_count: options.max_articles || 10 })

      return {
        podcastId,
        alreadyGenerated: !!response.already_generated,
        status: response.status || todayPodcastStatus.value
      }
    } catch (error) {
      console.error('生成播客失败:', error)
      throw error
    }
  }

  // 获取播客详情
  const getPodcastDetail = async (podcastId) => {
    loading.value = true
    try {
      const response = await api.get(`/api/v1/podcasts/${podcastId}`)
      // 响应拦截器已经返回 response.data，直接访问 podcast
      const podcastData = response.podcast || response
      selectedPodcast.value = podcastData
      return podcastData
    } catch (error) {
      console.error('获取播客详情失败:', error)
      throw error
    } finally {
      loading.value = false
    }
  }

  // 获取播客音频 URL（带签名）
  const getPodcastAudioUrl = async (podcastId) => {
    try {
      const response = await api.get(`/api/v1/podcasts/${podcastId}/audio-url`)
      // 响应拦截器已经返回 response.data
      if (response.success) {
        return `${import.meta.env.VITE_API_BASE_URL || ''}${response.audio_url}`
      }
      throw new Error('Failed to get audio URL')
    } catch (error) {
      console.error('获取音频 URL 失败:', error)
      throw error
    }
  }

  // 保存播放进度
  const saveProgress = async (podcastId, currentTime, totalTime) => {
    try {
      await api.post(`/api/v1/podcasts/${podcastId}/progress`, {
        current_time: Math.floor(currentTime),
        total_time: Math.floor(totalTime),
        progress_percentage: (currentTime / totalTime) * 100,
        is_completed: currentTime >= totalTime * 0.95
      })
    } catch (error) {
      console.error('保存播放进度失败:', error)
    }
  }

  // 清空选中的播客
  const clearSelectedPodcast = () => {
    selectedPodcast.value = null
  }

  // 创建分享链接
  const createShareLink = async (podcastId) => {
    try {
      const response = await api.post(`/api/v1/podcasts/${podcastId}/share`)
      if (response.success) {
        return response.share_token
      }
      throw new Error('Failed to create share link')
    } catch (error) {
      console.error('创建分享链接失败:', error)
      throw error
    }
  }

  // 删除播客
  const deletePodcast = async (podcastId) => {
    try {
      await api.delete(`/api/v1/podcasts/${podcastId}`)
      podcasts.value = podcasts.value.filter(p => p.id !== podcastId)
    } catch (error) {
      console.error('删除播客失败:', error)
      throw error
    }
  }

  const clearAll = () => {
    podcasts.value = []
    selectedPodcast.value = null
    generationStatus.value = {}
    loading.value = false
    stopPodcastStatusPolling()
  }

  return {
    // 状态
    podcasts,
    selectedPodcast,
    loading,
    generationStatus,

    // 计算属性
    completedPodcasts,
    pendingPodcasts,
    latestPodcast,
    todayPodcast,
    onboardingCachePodcast,
    todayPodcastStatus,
    isTodayPodcastCompleted,
    isTodayPodcastInProgress,

    // 方法
    fetchPodcasts,
    generatePodcast,
    startPodcastStatusPolling,
    stopPodcastStatusPolling,
    getPodcastDetail,
    getPodcastAudioUrl,
    saveProgress,
    createShareLink,
    clearSelectedPodcast,
    deletePodcast,
    clearAll
  }
})
