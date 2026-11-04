import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { showToast } from 'vant'
import { usePodcastStore } from './podcastStore'
import { trackTtsFirstPlay, trackAudioCompleted, trackAudioError, trackAudioStall, trackAudioAutoResume } from '@/utils/analytics'
import { isPlaybackStagnant, shouldResumeOnForeground, classifyPause, shouldAutoResumeAfterPause } from '@/services/tts/playbackRecoveryPolicy'

const emitFirstAudioPlayed = () => {
  if (typeof window !== 'undefined' && !window.__firstAudioPlayedEmitted) {
    window.__firstAudioPlayedEmitted = true
    window.dispatchEvent(new CustomEvent('first-audio-played'))
    console.log('[PodcastPlayerStore] first-audio-played event emitted')
  }
}

// 用于去重：每个 session 中每个播客只上报一次 tts_first_play
const reportedPodcasts = new Set()
const trackPodcastFirstPlay = (podcast) => {
  const key = podcast?.id
  if (key && !reportedPodcasts.has(key)) {
    reportedPodcasts.add(key)
    trackTtsFirstPlay({ podcast_id: key })
  }
}

/**
 * 播客播放器全局状态管理
 * 管理预生成 MP3 播客的播放状态，独立于 TTS playerStore
 * Audio 对象在 JS 内存中管理（非 DOM），路由切换不会销毁
 */
export const usePodcastPlayerStore = defineStore('podcastPlayer', () => {
  const { t } = useI18n()
  // ===== 播放状态 =====
  const isPlaying = ref(false)
  const isPaused = ref(false)
  const isLoading = ref(false)
  const currentPodcast = ref(null) // { id, title, description, articles, ... }
  const audioUrl = ref(null)

  // ===== 播放进度 =====
  const currentTime = ref(0)
  const duration = ref(0)
  const progress = computed(() =>
    duration.value > 0 ? (currentTime.value / duration.value) * 100 : 0
  )

  // ===== 播放设置 =====
  const playbackRate = ref(1.0)

  // ===== Audio 实例（JS 内存，非 DOM） =====
  let audio = null
  let progressSaveInterval = null
  let listenersAttached = false
  let playCancelled = false // 用于区分用户主动停止和真正的播放错误

  // ===== 断流/中断恢复状态（Fix 2，见 docs/bugs/20260721） =====
  let manualPause = false
  let isStalled = false
  let playbackStartedThisSource = false // 当前源已进入过播放（区分初始加载与中途断流）
  let stallWatchdogId = null
  let watchdogLastTime = 0
  let stagnantTicks = 0
  let recoveryAttempts = 0
  let lifecycleBound = false
  const STALL_WATCHDOG_INTERVAL_MS = 5000
  const STALL_RECOVER_AFTER_TICKS = 2
  const MAX_RECOVERY_ATTEMPTS = 2
  // 非预期暂停后的自动恢复尝试延迟（仅前台，见 playbackRecoveryPolicy）
  const UNINTENDED_PAUSE_RESUME_DELAYS_MS = [0, 2000]

  // ===== 辅助方法 =====

  const formatTime = (seconds) => {
    if (!seconds || isNaN(seconds)) return '00:00'
    const mins = Math.floor(seconds / 60)
    const secs = Math.floor(seconds % 60)
    return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`
  }

  /**
   * 停止 TTS 播放器（互斥）
   */
  const stopTtsPlayer = async () => {
    try {
      const { usePlayerStore } = await import('./playerStore')
      const ttsPlayer = usePlayerStore()
      if (ttsPlayer.isPlaying || ttsPlayer.isPaused || ttsPlayer.isLoadingAudio) {
        ttsPlayer.stop()
      }
    } catch (e) {
      // playerStore 未加载时忽略
    }
  }

  /**
   * 绑定 Audio 事件监听器
   */
  const attachListeners = () => {
    if (!audio || listenersAttached) return
    listenersAttached = true

    audio.addEventListener('play', () => {
      isPlaying.value = true
      isPaused.value = false
      manualPause = false
      isStalled = false
      stagnantTicks = 0
      recoveryAttempts = 0
      playbackStartedThisSource = true
    })

    audio.addEventListener('pause', () => {
      isPlaying.value = false
      // 用 audio.ended 区分自然结束，避免边界竞态造成僵尸态
      if (audio && !audio.ended) {
        isPaused.value = true
      }
      // 暂停时保存进度，防止用户暂停后离开丢失进度
      if (currentPodcast.value && currentTime.value > 0) {
        localStorage.setItem('podcast_progress', JSON.stringify({
          podcastId: currentPodcast.value.id,
          currentTime: currentTime.value,
          duration: duration.value,
          timestamp: Date.now()
        }))
      }

      // 非预期暂停（系统中断/焦点被抢）→ 前台内快速自动恢复
      // 后台不自动恢复：可能是其他 app 正在播放，不抢音频焦点
      const classification = classifyPause({ manualPause, ended: audio.ended })
      if (classification === 'unintended') {
        scheduleUnintendedPauseResume()
      }
    })

    // 断流监听（Fix 2）：iOS 静默断流不触发 error，靠这些事件 + 看门狗兜底
    audio.addEventListener('stalled', () => {
      markStalled('stalled')
    })

    audio.addEventListener('waiting', () => {
      markStalled('waiting')
    })

    audio.addEventListener('canplay', () => {
      const wasStalled = isStalled
      isStalled = false
      // 数据恢复且非手动暂停 → 自动续播（Safari 需要显式 play）
      // playbackStartedThisSource：仅中途断流；初始加载的 canplay 不触发，避免与 play() 竞争
      if (wasStalled && playbackStartedThisSource && !manualPause && audio && audio.paused && !audio.ended && currentPodcast.value) {
        audio.play().then(() => {
          trackAudioAutoResume({ podcast_id: currentPodcast.value?.id, trigger: 'canplay' })
        }).catch(() => {})
      }
    })

    audio.addEventListener('playing', () => {
      isStalled = false
      stagnantTicks = 0
    })

    audio.addEventListener('timeupdate', () => {
      if (audio) {
        currentTime.value = audio.currentTime
        updateMediaSessionPosition()
      }
    })

    audio.addEventListener('loadedmetadata', () => {
      if (audio) {
        duration.value = audio.duration
        // 恢复播放速率
        audio.playbackRate = playbackRate.value
      }
    })

    audio.addEventListener('ended', () => {
      isPlaying.value = false
      isPaused.value = false
      currentTime.value = 0
      clearProgressSave()
      clearMediaSession()
      // 保存完成状态
      if (currentPodcast.value) {
        const podcastStore = usePodcastStore()
        podcastStore.saveProgress(currentPodcast.value.id, duration.value, duration.value)
        trackAudioCompleted({ podcast_id: currentPodcast.value.id })
      }
    })

    audio.addEventListener('error', (e) => {
      isLoading.value = false
      isPlaying.value = false
      isPaused.value = false
      clearProgressSave()
      if (!playCancelled) {
        showToast(t('podcast.audioPlaybackFailed'))
      }
      if (currentPodcast.value) {
        trackAudioError({
          podcast_id: currentPodcast.value.id,
          error_code: audio?.error?.code,
          error_message: audio?.error?.message || 'podcast_playback_failed',
        })
      }
    })
  }

  /**
   * 确保 Audio 实例存在
   */
  const ensureAudio = () => {
    if (!audio) {
      audio = new Audio()
      listenersAttached = false
      attachListeners()
    }
    bindLifecycleListeners()
    startStallWatchdog()
    return audio
  }

  // ===== 断流/中断恢复（Fix 2） =====

  const markStalled = (trigger) => {
    if (!isStalled) {
      trackAudioStall({
        podcast_id: currentPodcast.value?.id,
        trigger,
        current_time: Math.round(currentTime.value)
      })
    }
    isStalled = true
  }

  /**
   * 重载音频源并从断点续播（元素损坏/断流后）
   */
  const reloadAndResume = (trigger) => {
    const a = audio
    if (!a || !audioUrl.value || !currentPodcast.value) return

    playbackStartedThisSource = false // 重载期间屏蔽 canplay 自动恢复，由下方 play() 主导
    isLoading.value = true // 同时屏蔽非预期暂停的自动恢复调度
    const resumeTime = currentTime.value
    a.src = audioUrl.value
    a.load()
    a.addEventListener('loadedmetadata', () => {
      try { a.currentTime = resumeTime } catch (e) { /* */ }
    }, { once: true })
    a.playbackRate = playbackRate.value
    a.play().then(() => {
      isLoading.value = false
      recoveryAttempts = 0
      trackAudioAutoResume({ podcast_id: currentPodcast.value?.id, trigger, wedged: true })
    }).catch(() => {
      isLoading.value = false
    })
  }

  /**
   * 非预期暂停后的快速自动恢复（仅前台；后台交给回前台 reconcile）
   */
  const scheduleUnintendedPauseResume = () => {
    UNINTENDED_PAUSE_RESUME_DELAYS_MS.forEach((delay) => {
      setTimeout(() => {
        if (!audio || !audio.paused || audio.ended) return
        if (manualPause || isLoading.value || !currentPodcast.value) return

        const allowed = shouldAutoResumeAfterPause({
          classification: 'unintended',
          visibilityState: typeof document !== 'undefined' ? document.visibilityState : 'visible',
          online: typeof navigator === 'undefined' ? true : navigator.onLine
        })
        if (!allowed) return

        resumePodcastResilient('unintended_pause')
      }, delay)
    })
  }

  /**
   * 韧性恢复：元素损坏时先重载再续播，而非裸 play()
   */
  const resumePodcastResilient = (trigger) => {
    const a = audio
    if (!a || !currentPodcast.value) return
    if (a.ended) return // 自然结束不恢复

    manualPause = false
    recoveryAttempts = 0

    const wedged = a.error || a.readyState === 0 || a.networkState === 3 // NETWORK_NO_SOURCE
    if (wedged) {
      reloadAndResume(trigger)
      return
    }

    a.play().then(() => {
      try { navigator.mediaSession.playbackState = 'playing' } catch (e) { /* */ }
      trackAudioAutoResume({ podcast_id: currentPodcast.value?.id, trigger, wedged: false })
    }).catch(() => {})
  }

  /**
   * 无进展看门狗：元素自认为在播但进度长期不前进（iOS 静默断流）时重载续播。
   * 仅前台有效（setInterval）；后台冻结由 visibilitychange reconcile 兜底。
   */
  const startStallWatchdog = () => {
    if (stallWatchdogId) return
    stallWatchdogId = setInterval(() => {
      if (!audio || !currentPodcast.value) return

      const online = typeof navigator === 'undefined' ? true : navigator.onLine
      const stagnant = isPlaybackStagnant({
        paused: audio.paused,
        ended: audio.ended,
        manualPause,
        hasSession: Boolean(audioUrl.value),
        currentTime: audio.currentTime || 0,
        lastTime: watchdogLastTime,
        online
      })
      watchdogLastTime = audio.currentTime || 0

      if (!stagnant) {
        stagnantTicks = 0
        return
      }

      stagnantTicks += 1
      if (stagnantTicks >= STALL_RECOVER_AFTER_TICKS) {
        stagnantTicks = 0
        if (recoveryAttempts >= MAX_RECOVERY_ATTEMPTS) {
          // 放弃自动恢复：落为可手动恢复的暂停态
          isPlaying.value = false
          isPaused.value = true
          return
        }
        recoveryAttempts += 1
        console.warn('[Podcast] Playback stagnant, reloading and resuming')
        trackAudioStall({ podcast_id: currentPodcast.value?.id, trigger: 'watchdog', current_time: Math.round(currentTime.value) })
        reloadAndResume('watchdog')
      }
    }, STALL_WATCHDOG_INTERVAL_MS)
  }

  const bindLifecycleListeners = () => {
    if (lifecycleBound || typeof document === 'undefined') return
    lifecycleBound = true

    document.addEventListener('visibilitychange', () => {
      if (document.visibilityState !== 'visible') return
      const allowed = shouldResumeOnForeground({
        manualPause,
        hasSession: Boolean(currentPodcast.value) && Boolean(audioUrl.value),
        elementStopped: audio ? (audio.paused || audio.ended) : false,
        online: typeof navigator === 'undefined' ? true : navigator.onLine
      })
      if (allowed) {
        resumePodcastResilient('foreground')
      }
    })

    window.addEventListener('online', () => {
      if (!audio || manualPause) return
      if (!audio.paused || audio.ended) return
      if (!currentPodcast.value) return
      resumePodcastResilient('online')
    })
  }

  // ===== Media Session API =====

  const setupMediaSession = (podcast) => {
    if (!('mediaSession' in navigator)) return

    try {
      navigator.mediaSession.metadata = new MediaMetadata({
        title: podcast.title || t('podcast.nowPlaying'),
        artist: 'Readaria Podcast',
        album: 'Readaria',
        artwork: [
          { src: '/apple-touch-icon.png', sizes: '180x180', type: 'image/png' }
        ]
      })

      navigator.mediaSession.setActionHandler('play', async () => {
        if (!audio) return
        // 中断后元素可能已损坏，走韧性恢复而非裸 play()
        resumePodcastResilient('media_session')
      })

      navigator.mediaSession.setActionHandler('pause', () => {
        if (audio) {
          manualPause = true
          audio.pause()
          try { navigator.mediaSession.playbackState = 'paused' } catch (e) { /* */ }
        }
      })

      navigator.mediaSession.setActionHandler('seekbackward', (details) => {
        skipBackward(details.seekOffset || 15)
      })

      navigator.mediaSession.setActionHandler('seekforward', (details) => {
        skipForward(details.seekOffset || 30)
      })

      navigator.mediaSession.setActionHandler('seekto', (details) => {
        if (details.seekTime !== undefined) {
          seekTo(details.seekTime)
        }
      })

      console.log('[Podcast] Media Session configured:', podcast.title)
    } catch (error) {
      console.error('[Podcast] Media Session setup failed:', error)
    }
  }

  const updateMediaSessionPosition = () => {
    if (!('mediaSession' in navigator) || !audio) return
    try {
      const dur = audio.duration
      const pos = audio.currentTime
      if (!isFinite(dur) || dur <= 0 || isNaN(pos) || pos < 0 || pos > dur) return
      navigator.mediaSession.setPositionState({
        duration: dur,
        playbackRate: audio.playbackRate,
        position: pos
      })
    } catch (e) {
      // iOS 旧版本可能不支持
    }
  }

  const clearMediaSession = () => {
    if (!('mediaSession' in navigator)) return
    try {
      navigator.mediaSession.metadata = null
      const actions = ['play', 'pause', 'seekbackward', 'seekforward', 'seekto']
      actions.forEach(action => {
        try { navigator.mediaSession.setActionHandler(action, null) } catch (e) { /* */ }
      })
    } catch (e) { /* */ }
  }

  // ===== 核心播放方法 =====

  /**
   * 播放播客
   * @param {Object} podcast - 播客对象 { id, title, description, articles, ... }
   * @param {string} url - 音频 URL
   */
  const play = async (podcast, url) => {
    if (!podcast || !url) {
      showToast(t('podcast.invalidData'))
      return
    }

    // 互斥：停止 TTS 播放器
    stopTtsPlayer()

    playCancelled = false
    manualPause = false
    isLoading.value = true

    try {
      const a = ensureAudio()

      // 如果是同一个播客且已暂停，直接恢复
      if (currentPodcast.value?.id === podcast.id && isPaused.value && a.src) {
        await a.play()
        isLoading.value = false
        setupMediaSession(podcast)
        return
      }

      // 新播客：设置源并播放
      currentPodcast.value = podcast
      audioUrl.value = url
      currentTime.value = 0
      duration.value = 0
      playbackStartedThisSource = false

      a.src = url
      a.playbackRate = playbackRate.value

      // 尝试恢复进度
      const savedTime = getSavedProgress(podcast.id)
      if (savedTime > 0) {
        // 等待 metadata 加载后再 seek
        await new Promise((resolve) => {
          if (a.readyState >= 1) { resolve(); return }
          const onMeta = () => { a.removeEventListener('loadedmetadata', onMeta); resolve() }
          a.addEventListener('loadedmetadata', onMeta)
          setTimeout(() => { a.removeEventListener('loadedmetadata', onMeta); resolve() }, 3000)
        })
        try { a.currentTime = savedTime } catch (e) { /* */ }
      }

      await a.play()
      emitFirstAudioPlayed()
      trackPodcastFirstPlay(podcast)
      setupMediaSession(podcast)
      startProgressSave()
    } catch (error) {
      if (!playCancelled) {
        console.error('[Podcast] Play failed:', error)
        showToast(t('podcast.playFailedRetry'))
      }
    } finally {
      isLoading.value = false
    }
  }

  const togglePlayPause = () => {
    if (!audio) return

    if (isPaused.value) {
      resumePodcastResilient('store_toggle')
    } else if (isPlaying.value) {
      manualPause = true
      audio.pause()
      try { navigator.mediaSession.playbackState = 'paused' } catch (e) { /* */ }
    }
  }

  const seekTo = (time) => {
    if (!audio || !isFinite(audio.duration)) return
    const target = Math.max(0, Math.min(time, audio.duration))
    audio.currentTime = target
    currentTime.value = target
    updateMediaSessionPosition()
  }

  const skipForward = (seconds = 30) => {
    if (!audio) return
    seekTo(audio.currentTime + seconds)
  }

  const skipBackward = (seconds = 15) => {
    if (!audio) return
    seekTo(audio.currentTime - seconds)
  }

  const setPlaybackRate = (rate) => {
    const newRate = Math.max(0.5, Math.min(2.0, rate))
    playbackRate.value = newRate
    if (audio) {
      audio.playbackRate = newRate
    }
    saveSettings()
  }

  const stop = ({ persistProgress = true } = {}) => {
    playCancelled = true
    manualPause = true // 显式停止后禁止任何自动恢复
    if (audio) {
      audio.pause()
      audio.src = ''
    }
    // 保存最后进度
    if (persistProgress && currentPodcast.value && currentTime.value > 0) {
      const podcastStore = usePodcastStore()
      podcastStore.saveProgress(currentPodcast.value.id, currentTime.value, duration.value)
    }

    isPlaying.value = false
    isPaused.value = false
    isLoading.value = false
    currentTime.value = 0
    duration.value = 0
    currentPodcast.value = null
    audioUrl.value = null

    clearProgressSave()
    clearMediaSession()
  }

  // ===== 进度持久化 =====

  const startProgressSave = () => {
    clearProgressSave()
    progressSaveInterval = setInterval(() => {
      if (isPlaying.value && currentPodcast.value && currentTime.value > 0) {
        // localStorage 即时保存
        localStorage.setItem('podcast_progress', JSON.stringify({
          podcastId: currentPodcast.value.id,
          currentTime: currentTime.value,
          duration: duration.value,
          timestamp: Date.now()
        }))
        // API 保存
        const podcastStore = usePodcastStore()
        podcastStore.saveProgress(currentPodcast.value.id, currentTime.value, duration.value)
      }
    }, 10000) // 每 10 秒
  }

  const clearProgressSave = () => {
    if (progressSaveInterval) {
      clearInterval(progressSaveInterval)
      progressSaveInterval = null
    }
  }

  const getSavedProgress = (podcastId) => {
    try {
      const data = JSON.parse(localStorage.getItem('podcast_progress') || 'null')
      if (!data || data.podcastId !== podcastId) return 0
      // 24 小时过期
      if (Date.now() - data.timestamp > 24 * 60 * 60 * 1000) return 0
      return data.currentTime || 0
    } catch (e) {
      return 0
    }
  }

  const saveSettings = () => {
    localStorage.setItem('podcast_player_settings', JSON.stringify({
      playbackRate: playbackRate.value
    }))
  }

  const restoreSettings = () => {
    try {
      const data = JSON.parse(localStorage.getItem('podcast_player_settings') || 'null')
      if (data?.playbackRate) {
        playbackRate.value = data.playbackRate
      }
    } catch (e) { /* */ }
  }

  // 启动时恢复设置
  restoreSettings()

  const clearAnalyticsDedupe = () => {
    reportedPodcasts.clear()
  }

  return {
    // 状态
    isPlaying,
    isPaused,
    isLoading,
    currentPodcast,
    audioUrl,
    currentTime,
    duration,
    progress,
    playbackRate,

    // 方法
    play,
    togglePlayPause,
    seekTo,
    skipForward,
    skipBackward,
    setPlaybackRate,
    stop,
    formatTime,
    getSavedProgress,
    clearAnalyticsDedupe
  }
})
