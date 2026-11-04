/**
 * useTTS Composable - Vue 3 语音合成组合式函数
 *
 * 提供统一的 TTS 接口，集成两层 TTS 架构：
 * - Tier 1: 云端高质量缓存 (OpenAI/Azure TTS)
 * - Tier 2: 云端实时生成 (OpenAI)
 *
 * 特性：
 * - 自动选择最佳 TTS 引擎
 * - 响应式状态管理
 * - 播放控制（播放、暂停、跳转）
 * - Media Session API 支持（iOS 后台播放）
 * - 自动降级处理
 */

import { ref, computed, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { showToast } from 'vant'
import * as ttsManager from '@/services/tts/ttsManager'
import { useFeedStore } from '@/stores/feedStore'
import {
  startTtsPrepare,
  getTtsPrepareStatus,
  getTtsPlayUrl,
  getTtsSegmentPlayUrl
} from '@/api/tts'
import { captureMessage } from '@sentry/vue'
import { trackAudioCompleted, trackAudioError, trackAudioStall, trackAudioAutoResume, trackAudioTrackHandoff } from '@/utils/analytics'
import {
  classifyPause,
  shouldAutoResumeAfterPause,
  shouldResumeOnForeground,
  isPlaybackStagnant,
  shouldPrefetchNextTrack
} from '@/services/tts/playbackRecoveryPolicy'

// ==================== 全局音频实例 ====================

// 全局共用的 Audio 实例，确保播放器单例
const globalAudio = ref(null)

// ==================== Composable ====================

export function useTTS(playerStore = null) {
  const { t } = useI18n()

  // ===== 播放状态 =====
  const isPlaying = ref(false)
  const isPaused = ref(false)
  const isLoading = ref(false)
  const loadError = ref(null)
  const currentTier = ref(null)

  // ===== 当前内容 =====
  const currentArticle = ref(null)
  const currentAudioUrl = ref(null)

  // ===== 播放进度 =====
  const currentTime = ref(0)
  const totalTime = ref(0)
  const progress = computed(() =>
    totalTime.value > 0 ? (currentTime.value / totalTime.value) * 100 : 0
  )

  // ===== 播放设置 =====
  const playbackRate = ref(1.0)

  // ===== 内部状态 =====
  let manualPause = false
  let audioCleanupFn = null
  let cloudPollTimer = null
  let cloudSessionId = 0
  let cloudRecoveryAttempts = 0
  let isRecoveringCloudPlayback = false
  let isCheckingNearEndTransition = false
  let isPrimingAudio = false
  let hasPrimedAudioGesture = false
  let nextSegmentPreloader = null
  let lastCloudPlaybackError = null
  let internalPauseReason = null
  let audioLoadToken = 0
  let isAudioSourceLoadPending = false
  const currentCloudSource = ref(null)
  const cloudPlaybackMode = ref(null) // null | preparing | segmented | final
  const cloudPrepareStatus = ref(null)
  const currentSegmentIndex = ref(null)
  const segmentStartOffset = ref(0)
  const pendingSeekTime = ref(null)
  const prefetchedNextSegmentIndex = ref(null)
  const prefetchedNextSegmentUrl = ref(null)

  // ===== 后台连播预取状态（Fix 1，见 docs/bugs/20260721） =====
  let nextTrackPrefetch = null // { articleId, article, finalUrl?, segment0Url?, segment0End?, duration?, voice }
  let nextTrackPrefetchInFlight = false
  let nextTrackPrefetchAttemptAt = 0
  let nextTrackPreloaderAudio = null
  let finalWarmPreloader = null // 分段播放中 final 就绪后预热整篇 MP3 字节
  let warmedFinalForArticle = null

  // ===== 断流/中断恢复状态（Fix 2） =====
  let suppressAutoResume = false // 自然结束/用户停止后禁止自动恢复
  let isStalled = false // stalled/waiting 已触发且尚未恢复
  let lastStallAt = 0
  let playbackStartedThisSource = false // 当前音频源已成功进入过播放（区分初始加载与中途断流）
  let stallWatchdogId = null
  let watchdogLastTime = 0
  let stagnantTicks = 0
  let lifecycleListenersBound = false // visibilitychange/online 只绑定一次

  // 浏览器 audio.duration 与后端 end_offset_sec 的允许偏差（秒）
  // 实测某些 MP3 的浏览器解码时长比 pydub 短 1~2 秒，取 3 秒以覆盖 VBR/编码差异
  const SEGMENT_END_TOLERANCE_SEC = 3.0

  // ===== 后台连播 / 断流恢复常量 =====
  // 下一篇预取：剩余多少秒（媒体时间）内开始客户端预取签名 URL + 预热字节
  const NEXT_TRACK_PREFETCH_THRESHOLD_SEC = 75
  const NEXT_TRACK_PREFETCH_RETRY_MS = 10000
  // 断流看门狗：采样间隔 × 连续无进展次数 ≈ 10s 判定停滞
  const STALL_WATCHDOG_INTERVAL_MS = 5000
  const STALL_RECOVER_AFTER_TICKS = 2
  // 非预期暂停后的自动恢复尝试延迟（仅前台，见 playbackRecoveryPolicy）
  const UNINTENDED_PAUSE_RESUME_DELAYS_MS = [0, 2000]

  // ==================== 初始化 ====================

  /**
   * 初始化 TTS 系统
   */
  const initialize = async () => {
    try {
      await ttsManager.initialize()
      console.log('[useTTS] TTS system initialized')
    } catch (error) {
      console.error('[useTTS] Initialization failed:', error)
    }
  }

  // 自动初始化
  initialize()

  const clearCloudPolling = () => {
    if (cloudPollTimer) {
      clearTimeout(cloudPollTimer)
      cloudPollTimer = null
    }
  }

  const getCloudPreparePollDelay = (status = cloudPrepareStatus.value) => {
    if (!status?.first_playable_ready) {
      return 250
    }
    if (!status?.final_ready) {
      return 1000
    }
    return 1500
  }

  const resetCloudPlaybackState = () => {
    clearCloudPolling()
    cloudRecoveryAttempts = 0
    isRecoveringCloudPlayback = false
    isCheckingNearEndTransition = false
    internalPauseReason = null
    isAudioSourceLoadPending = false
    audioLoadToken += 1
    if (nextSegmentPreloader) {
      try {
        nextSegmentPreloader.pause()
        nextSegmentPreloader.src = ''
      } catch (error) {
        console.warn('[useTTS] Failed to cleanup next segment preloader:', error)
      }
      nextSegmentPreloader = null
    }
    currentCloudSource.value = null
    cloudPlaybackMode.value = null
    cloudPrepareStatus.value = null
    currentSegmentIndex.value = null
    segmentStartOffset.value = 0
    pendingSeekTime.value = null
    prefetchedNextSegmentIndex.value = null
    prefetchedNextSegmentUrl.value = null
    lastCloudPlaybackError = null
    if (finalWarmPreloader) {
      try {
        finalWarmPreloader.pause()
        finalWarmPreloader.removeAttribute('src')
      } catch (error) {
        console.warn('[useTTS] Failed to cleanup final warm preloader:', error)
      }
      finalWarmPreloader = null
    }
    warmedFinalForArticle = null
    cloudSessionId += 1
  }

  const beginInternalAudioTransition = (reason) => {
    internalPauseReason = reason
    if (!manualPause) {
      isPaused.value = false
      isLoading.value = true
    }
    console.log(`[useTTS] Internal audio transition started: ${reason}`)
  }

  const endInternalAudioTransition = (reason = 'completed') => {
    if (!internalPauseReason) return
    console.log(`[useTTS] Internal audio transition cleared: ${internalPauseReason} -> ${reason}`)
    internalPauseReason = null
  }

  const createAudioLoadSupersededError = () => {
    const error = new Error('audio_load_superseded')
    error.code = 'AUDIO_LOAD_SUPERSEDED'
    return error
  }

  const createAudioSourceNotReadyError = () => new Error('audio_source_not_ready')

  const isAudioLoadSupersededError = (error) => (
    error?.code === 'AUDIO_LOAD_SUPERSEDED' ||
    error?.message === 'audio_load_superseded'
  )

  const startAudioSourceLoad = (reason) => {
    audioLoadToken += 1
    isAudioSourceLoadPending = true
    beginInternalAudioTransition(reason)
    return audioLoadToken
  }

  const finishAudioSourceLoad = (token) => {
    if (token === audioLoadToken) {
      isAudioSourceLoadPending = false
    }
  }

  const isStaleAudioLoadToken = (token) => token !== audioLoadToken

  const getReadySegments = () => {
    const status = cloudPrepareStatus.value
    return Array.isArray(status?.segments)
      ? status.segments.filter(segment => segment.status === 'ready')
      : []
  }

  const getReadyDuration = () => {
    if (cloudPrepareStatus.value?.final_ready && cloudPrepareStatus.value?.total_duration_sec) {
      return cloudPrepareStatus.value.total_duration_sec
    }
    return cloudPrepareStatus.value?.ready_duration_sec || 0
  }

  const getActiveGlobalTime = () => {
    if (!globalAudio.value) return currentTime.value || 0
    if (cloudPlaybackMode.value === 'segmented') {
      return (segmentStartOffset.value || 0) + (globalAudio.value.currentTime || 0)
    }
    return globalAudio.value.currentTime || 0
  }

  const findSegmentForTime = (targetTime) => {
    const readySegments = getReadySegments()
    return readySegments.find(segment => {
      const start = segment.start_offset_sec ?? 0
      const end = segment.end_offset_sec ?? start
      return targetTime >= start && targetTime < end
    }) || null
  }

  const shouldPrimeAudioForIos = () => {
    if (hasPrimedAudioGesture || typeof navigator === 'undefined') {
      return false
    }

    const ua = navigator.userAgent || ''
    const isIosDevice = /iPhone|iPad|iPod/i.test(ua)
    const isIpadDesktopMode = navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1

    return isIosDevice || isIpadDesktopMode
  }

  const ensurePlaybackRateApplied = (reason = 'unknown') => {
    if (!globalAudio.value) return

    const targetRate = playbackRate.value || 1.0
    const actualRate = globalAudio.value.playbackRate || 1.0
    if (Math.abs(actualRate - targetRate) <= 0.01) {
      return
    }

    globalAudio.value.playbackRate = targetRate
    console.log(`[useTTS] Re-applied playbackRate (${reason}): ${actualRate} -> ${targetRate}`)
  }

  // ==================== 音频实例管理 ====================

  /**
   * 确保 Audio 实例存在
   */
  const ensureAudioInstance = () => {
    if (!globalAudio.value) {
      globalAudio.value = new Audio()
      globalAudio.value.preload = 'auto'
      globalAudio.value.playsInline = true
      globalAudio.value.crossOrigin = 'anonymous'
      setupAudioListeners()
    }
    ensurePlaybackRateApplied('ensure-instance')
  }

  const createSegmentPreloader = () => {
    const audio = new Audio()
    audio.preload = 'auto'
    audio.crossOrigin = 'anonymous'
    return audio
  }

  const primeAudioForUserGesture = async () => {
    if (!shouldPrimeAudioForIos()) {
      return
    }

    ensureAudioInstance()
    if (!globalAudio.value) {
      return
    }

    const audio = globalAudio.value
    const previousMuted = audio.muted
    const previousSrc = audio.getAttribute('src') || ''

    isPrimingAudio = true
    try {
      audio.muted = true
      audio.src = '/demo/tts-en-sample.mp3'
      audio.load()
      await audio.play()
      audio.pause()
      audio.currentTime = 0
      hasPrimedAudioGesture = true
      console.log('[useTTS] Primed iOS audio element for later playback')
    } catch (error) {
      console.warn('[useTTS] Failed to prime audio element for iOS playback:', error)
    } finally {
      audio.muted = previousMuted
      audio.pause()
      audio.removeAttribute('src')
      audio.src = previousSrc
      audio.load()
      ensurePlaybackRateApplied('prime-reset')
      isPrimingAudio = false
    }
  }

  /**
   * 清理音频资源
   */
  const cleanupAudio = () => {
    resetCloudPlaybackState()
    clearNextTrackPrefetch()
    suppressAutoResume = true // 显式清理（stop/换篇）后禁止自动恢复
    playbackStartedThisSource = false
    if (audioCleanupFn) {
      audioCleanupFn()
      audioCleanupFn = null
    }
    // 释放 Blob URL 避免内存泄漏
    if (currentAudioUrl.value && currentAudioUrl.value.startsWith('blob:')) {
      URL.revokeObjectURL(currentAudioUrl.value)
    }
    if (globalAudio.value) {
      globalAudio.value.pause()
      globalAudio.value.src = ''
      globalAudio.value.load()
    }
    currentAudioUrl.value = null
  }

  // ==================== 音频事件监听 ====================

  const setupAudioListeners = () => {
    if (!globalAudio.value) return

    // 时长元数据加载
    globalAudio.value.addEventListener('loadedmetadata', () => {
      if (isPrimingAudio) return

      ensurePlaybackRateApplied('loadedmetadata')
      if (cloudPlaybackMode.value === 'segmented') {
        totalTime.value = Math.max(getReadyDuration(), totalTime.value || 0)
      } else {
        totalTime.value = globalAudio.value.duration || totalTime.value || 0
      }
      console.log('[useTTS] Duration:', totalTime.value)

      // 同步到 playerStore
      if (playerStore?.updateProgress) {
        playerStore.updateProgress(currentTime.value, totalTime.value)
      }
    })

    // 播放进度更新
    globalAudio.value.addEventListener('timeupdate', () => {
      if (isPrimingAudio) return

      currentTime.value = getActiveGlobalTime()

      if (cloudPlaybackMode.value === 'segmented') {
        totalTime.value = Math.max(getReadyDuration(), totalTime.value || 0)
      }

      // 同步到 playerStore
      if (playerStore?.updateProgress) {
        playerStore.updateProgress(currentTime.value, totalTime.value)
      }

      // 更新 Media Session
      updateMediaSessionPositionState()

      if (cloudPlaybackMode.value === 'segmented') {
        maybePrepareNextSegment().catch((error) => {
          console.warn('[useTTS] Failed to prepare next segment near end:', error)
        })
      }

      // Fix 1: 接近曲目结尾时预取下一篇签名 URL + 预热字节（后台连播关键）
      maybePrefetchNextTrack().catch((error) => {
        console.warn('[useTTS] Next track prefetch check failed:', error)
      })
    })

    // 播放开始
    globalAudio.value.addEventListener('play', () => {
      if (isPrimingAudio) return

      endInternalAudioTransition('play')
      ensurePlaybackRateApplied('play')
      isPlaying.value = true
      isPaused.value = false
      manualPause = false
      suppressAutoResume = false // 新一轮真实播放开始，解除自然结束抑制
      isStalled = false
      stagnantTicks = 0
      playbackStartedThisSource = true
      setMediaSessionPlaybackState('playing')
      if (currentCloudSource.value) {
        cloudRecoveryAttempts = 0
      }
    })

    // 暂停
    globalAudio.value.addEventListener('pause', () => {
      if (isPrimingAudio) return

      setMediaSessionPlaybackState('paused')

      if (internalPauseReason && !manualPause) {
        isPlaying.value = false
        isPaused.value = false
        isLoading.value = true
        console.log(`[useTTS] Suppressed pause during internal transition: ${internalPauseReason}`)
        return
      }

      isPlaying.value = false
      // 用 audio.ended 属性区分自然结束与暂停，避免 currentTime/totalTime 边界竞态
      // 造成 isPlaying=false && isPaused=false 的僵尸态（会被 store idle 轮询清空会话）
      if (!globalAudio.value.ended) {
        isPaused.value = true
      }

      // 非预期暂停（系统中断/焦点被抢/路由切换）→ 前台内快速自动恢复
      // 后台不自动恢复：可能是其他 app 正在播放，不抢音频焦点
      const classification = classifyPause({
        manualPause,
        internalTransition: Boolean(internalPauseReason),
        ended: globalAudio.value.ended
      })
      if (classification === 'unintended') {
        scheduleUnintendedPauseResume()
      }
    })

    // 播放结束
    globalAudio.value.addEventListener('ended', async () => {
      if (isPrimingAudio) return

      if (cloudPlaybackMode.value === 'segmented') {
        // 分段切换期间维持 active 状态，避免外层 store 误判为播放结束
        isLoading.value = true
        try {
          await handleCloudSegmentEnded()
        } catch (error) {
          console.error('[useTTS] Cloud segment transition failed:', error)
          endInternalAudioTransition('transition-error')
          if (currentCloudSource.value && cloudRecoveryAttempts < 2) {
            recoverCloudPlayback().catch((recoverError) => {
              console.error('[useTTS] Cloud playback recovery failed after transition error:', recoverError)
              loadError.value = recoverError.message || error.message || 'cloud_transition_failed'
              isLoading.value = false
            })
            return
          }
          loadError.value = error.message || 'cloud_transition_failed'
          isLoading.value = false
        }
        return
      }

      // ✅ Fix 1（iOS 后台连播）：优先走预取命中后的同步交接
      // ended → 换 src + play() 必须在同一事件回合约内完成，否则 iOS 挂起进程
      if (tryFastNextTrackHandoff()) {
        return
      }

      suppressAutoResume = true // 自然结束：阻止 stall/前台 reconcile 误恢复
      isPlaying.value = false
      isPaused.value = false
      currentTime.value = 0

      // 通知 playerStore
      if (playerStore?.onPlaybackEnd) {
        playerStore.onPlaybackEnd()
      }
    })

    // 错误处理
    globalAudio.value.addEventListener('error', (e) => {
      if (isPrimingAudio) return

      const audioError = globalAudio.value?.error
      const audioErrorContext = {
        code: audioError?.code,
        message: audioError?.message,
        networkState: globalAudio.value?.networkState,
        readyState: globalAudio.value?.readyState,
        currentTime: globalAudio.value?.currentTime,
        duration: globalAudio.value?.duration,
        mode: cloudPlaybackMode.value,
        segmentIndex: currentSegmentIndex.value,
        sourceArticleId: currentCloudSource.value?.articleId
      }
      console.error('[useTTS] Audio error:', audioErrorContext)
      if (isAudioSourceLoadPending && currentCloudSource.value) {
        lastCloudPlaybackError = createAudioSourceNotReadyError()
        console.warn('[useTTS] Audio source error during pending transition; defer recovery to active transition flow')
        return
      }
      if (['segmented', 'final'].includes(cloudPlaybackMode.value || '') && currentCloudSource.value) {
        const activeIndex = currentSegmentIndex.value
        const detail = audioError?.message || `segment_${activeIndex}_playback_failed`
        endInternalAudioTransition('audio-error')
        if (cloudRecoveryAttempts < 2) {
          loadError.value = null
          isLoading.value = true
          recoverCloudPlayback().catch((error) => {
            console.error('[useTTS] Cloud playback recovery failed:', error)
            loadError.value = error.message || detail
            trackAudioError({
              article_id: currentArticle.value?.id || currentArticle.value?.url,
              error_code: audioError?.code,
              error_message: error.message || detail,
            })
          })
          return
        }
        loadError.value = detail
        isAudioSourceLoadPending = false
        trackAudioError({
          article_id: currentArticle.value?.id || currentArticle.value?.url,
          error_code: audioError?.code,
          error_message: detail,
        })
      } else {
        loadError.value = t('tts.audioPlaybackFailed')
        isAudioSourceLoadPending = false
        trackAudioError({
          article_id: currentArticle.value?.id || currentArticle.value?.url,
          error_code: audioError?.code,
          error_message: audioError?.message || loadError.value,
        })
      }
      isPlaying.value = false
      isLoading.value = false
    })

    // ==================== Fix 2: 断流/中断恢复监听 ====================

    // 网络断流开始（iOS 常静默断流不触发 error，只能靠这些事件 + 看门狗兜底）
    globalAudio.value.addEventListener('stalled', () => {
      if (isPrimingAudio) return
      markStalled('stalled')
    })

    globalAudio.value.addEventListener('waiting', () => {
      if (isPrimingAudio) return
      // seek/分段切换期间也会触发 waiting，由 internalPauseReason 过滤
      if (internalPauseReason) return
      markStalled('waiting')
    })

    // 数据恢复：非手动暂停且元素处于暂停态 → 自动续播（Chrome 通常自行恢复，Safari 需要显式 play）
    globalAudio.value.addEventListener('canplay', () => {
      if (isPrimingAudio) return
      const wasStalled = isStalled
      isStalled = false
      if (
        wasStalled &&
        playbackStartedThisSource && // 仅中途断流恢复；初始加载的 canplay 不触发（避免与 loadAudio 的 play() 竞争）
        !manualPause &&
        !internalPauseReason &&
        !suppressAutoResume &&
        globalAudio.value.paused &&
        !globalAudio.value.ended &&
        (currentCloudSource.value || currentAudioUrl.value)
      ) {
        console.log('[useTTS] Auto-resuming after stall (canplay)')
        globalAudio.value.play().then(() => {
          trackAudioAutoResume({ article_id: currentArticle.value?.id || currentArticle.value?.url, trigger: 'canplay' })
        }).catch(() => {})
      }
    })

    globalAudio.value.addEventListener('playing', () => {
      if (isPrimingAudio) return
      isStalled = false
      stagnantTicks = 0
    })

    // 页面生命周期监听（回前台 reconcile + 网络恢复）只绑定一次
    bindLifecycleListeners()
    startStallWatchdog()
  }

  const markStalled = (trigger) => {
    if (!isStalled) {
      trackAudioStall({
        article_id: currentArticle.value?.id || currentArticle.value?.url,
        trigger,
        mode: cloudPlaybackMode.value,
        current_time: Math.round(currentTime.value)
      })
    }
    isStalled = true
    lastStallAt = Date.now()
  }

  /**
   * 无进展看门狗：元素自认为在播放（!paused && !ended）但 currentTime 长期不前进，
   * 覆盖 iOS 静默断流（不触发 stalled/error/pause 任何事件）的卡死场景。
   * 注意：依赖 setInterval，仅前台有效；后台冻结由 visibilitychange reconcile 兜底。
   */
  const startStallWatchdog = () => {
    if (stallWatchdogId) return
    stallWatchdogId = setInterval(() => {
      const audio = globalAudio.value
      if (!audio || isPrimingAudio) return

      const online = typeof navigator === 'undefined' ? true : navigator.onLine
      const stagnant = isPlaybackStagnant({
        paused: audio.paused,
        ended: audio.ended,
        manualPause,
        internalTransition: Boolean(internalPauseReason),
        seeking: pendingSeekTime.value != null,
        recovering: isRecoveringCloudPlayback,
        hasSession: Boolean(currentCloudSource.value || currentAudioUrl.value),
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
        console.warn('[useTTS] Playback stagnant while supposed to be playing, recovering')
        trackAudioStall({
          article_id: currentArticle.value?.id || currentArticle.value?.url,
          trigger: 'watchdog',
          mode: cloudPlaybackMode.value,
          current_time: Math.round(currentTime.value)
        })
        recoverFromStall()
      }
    }, STALL_WATCHDOG_INTERVAL_MS)
  }

  const recoverFromStall = () => {
    if (isRecoveringCloudPlayback || manualPause || suppressAutoResume) return

    // 云端播放：复用现有恢复链路（重取状态 → 断点续播），次数预算由 cloudRecoveryAttempts 控制
    if (currentCloudSource.value && ['segmented', 'final'].includes(cloudPlaybackMode.value || '')) {
      if (cloudRecoveryAttempts >= 2) {
        // 放弃自动恢复：落为可手动恢复的暂停态，避免无限重试
        console.warn('[useTTS] Stall recovery budget exhausted, falling back to paused state')
        isPlaying.value = false
        isPaused.value = true
        return
      }
      recoverCloudPlayback().catch((error) => {
        console.warn('[useTTS] Stall recovery failed:', error)
      })
      return
    }

    // 非云端（直链 URL）：重载 src + 断点 seek + play
    const audio = globalAudio.value
    const url = currentAudioUrl.value
    if (!audio || !url) return
    try {
      playbackStartedThisSource = false // 重载期间屏蔽 canplay 自动恢复，由下方 play() 主导
      const resumeTime = currentTime.value
      audio.src = url
      audio.load()
      audio.addEventListener('loadedmetadata', () => {
        try { audio.currentTime = resumeTime } catch (e) { /* ignore */ }
      }, { once: true })
      audio.play().catch(() => {})
    } catch (error) {
      console.warn('[useTTS] Direct URL stall recovery failed:', error)
    }
  }

  /**
   * 非预期暂停后的快速自动恢复（仅前台；后台交给回前台 reconcile）
   * 设计见 docs/bugs/20260721-tts_background_playback_failures.md
   */
  const scheduleUnintendedPauseResume = () => {
    UNINTENDED_PAUSE_RESUME_DELAYS_MS.forEach((delay, attemptIndex) => {
      setTimeout(() => {
        const audio = globalAudio.value
        if (!audio || !audio.paused || audio.ended) return
        if (manualPause || internalPauseReason || suppressAutoResume) return
        if (isLoading.value || isAudioSourceLoadPending) return // 新源加载中，避免与 loadAudio 的 play() 竞争
        if (!currentCloudSource.value && !currentAudioUrl.value) return

        const allowed = shouldAutoResumeAfterPause({
          classification: 'unintended',
          visibilityState: typeof document !== 'undefined' ? document.visibilityState : 'visible',
          online: typeof navigator === 'undefined' ? true : navigator.onLine
        })
        if (!allowed) return

        console.log(`[useTTS] Auto-resuming after unintended pause (attempt ${attemptIndex + 1})`)
        audio.play().then(() => {
          trackAudioAutoResume({
            article_id: currentArticle.value?.id || currentArticle.value?.url,
            trigger: 'unintended_pause',
            attempt: attemptIndex + 1
          })
        }).catch(() => {})
      }, delay)
    })
  }

  /**
   * 韧性恢复：元素损坏/中断后先重载再续播，而非裸 play()
   * 供 Media Session play、store togglePlayPause、前台 reconcile、online 事件共用
   */
  const resumePlaybackResilient = async (trigger = 'unknown') => {
    const audio = globalAudio.value
    if (!audio || (!currentCloudSource.value && !currentAudioUrl.value)) {
      play()
      return
    }

    // 用户主动触发的恢复：重置恢复次数预算 + 解除手动暂停标记
    cloudRecoveryAttempts = 0
    manualPause = false

    const isCloudMode = currentCloudSource.value && ['segmented', 'final'].includes(cloudPlaybackMode.value || '')
    const wedged = Boolean(audio.error) || audio.readyState === 0 || audio.networkState === 3 // NETWORK_NO_SOURCE

    try {
      // 分段模式下元素已 ended：说明边界切换链条曾冻结，走恢复链路重定位断点
      if (audio.ended && isCloudMode && cloudPlaybackMode.value === 'segmented') {
        await recoverCloudPlayback()
        trackAudioAutoResume({ article_id: currentArticle.value?.id || currentArticle.value?.url, trigger, wedged: true })
        return
      }
      // final 模式自然结束后 suppressAutoResume 会拦截；走到这里的 ended 视为无需恢复
      if (audio.ended && cloudPlaybackMode.value === 'final') {
        return
      }

      if (wedged && isCloudMode) {
        await recoverCloudPlayback()
        trackAudioAutoResume({ article_id: currentArticle.value?.id || currentArticle.value?.url, trigger, wedged: true })
        return
      }

      if (wedged && currentAudioUrl.value) {
        playbackStartedThisSource = false // 重载期间屏蔽 canplay 自动恢复，由下方 play() 主导
        const resumeTime = currentTime.value
        audio.src = currentAudioUrl.value
        audio.load()
        audio.addEventListener('loadedmetadata', () => {
          try { audio.currentTime = resumeTime } catch (e) { /* ignore */ }
        }, { once: true })
      }

      await audio.play()
      ensurePlaybackRateApplied('resilient-resume')
      if (trigger !== 'watchdog') {
        trackAudioAutoResume({ article_id: currentArticle.value?.id || currentArticle.value?.url, trigger, wedged })
      }
    } catch (error) {
      console.warn(`[useTTS] Resilient resume failed (trigger=${trigger}):`, error)
      showToast(t('tts.playFailed'))
    }
  }

  const handleForegroundReconcile = () => {
    const audio = globalAudio.value
    const allowed = shouldResumeOnForeground({
      manualPause,
      suppressAutoResume,
      hasSession: Boolean(currentArticle.value) && Boolean(currentCloudSource.value || currentAudioUrl.value),
      elementStopped: audio ? (audio.paused || audio.ended) : false,
      online: typeof navigator === 'undefined' ? true : navigator.onLine
    })
    if (!allowed) return

    console.log('[useTTS] Reconciling playback after foreground return')
    resumePlaybackResilient('foreground')
  }

  const handleOnlineRecovery = () => {
    const audio = globalAudio.value
    if (!audio || manualPause || suppressAutoResume) return
    if (!audio.paused || audio.ended) return
    if (!currentCloudSource.value && !currentAudioUrl.value) return

    console.log('[useTTS] Network back online, resuming playback')
    resumePlaybackResilient('online')
  }

  const bindLifecycleListeners = () => {
    if (lifecycleListenersBound || typeof document === 'undefined') return
    lifecycleListenersBound = true

    document.addEventListener('visibilitychange', () => {
      if (document.visibilityState === 'visible') {
        handleForegroundReconcile()
      }
    })
    window.addEventListener('online', handleOnlineRecovery)
  }

  // ==================== Fix 1: 下一篇预取 + 同步交接 ====================

  const clearNextTrackPrefetch = () => {
    if (nextTrackPreloaderAudio) {
      try {
        nextTrackPreloaderAudio.pause()
        nextTrackPreloaderAudio.removeAttribute('src')
      } catch (error) {
        console.warn('[useTTS] Failed to clear next track preloader:', error)
      }
      nextTrackPreloaderAudio = null
    }
    nextTrackPrefetch = null
    nextTrackPrefetchInFlight = false
    nextTrackPrefetchAttemptAt = 0
  }

  const warmNextTrackBytes = (url) => {
    try {
      if (!nextTrackPreloaderAudio) {
        nextTrackPreloaderAudio = createSegmentPreloader()
      }
      nextTrackPreloaderAudio.src = url
      nextTrackPreloaderAudio.load()
    } catch (error) {
      console.warn('[useTTS] Next track byte warm-up failed:', error)
    }
  }

  /**
   * 当前曲目接近结束时，客户端预取下一篇的签名播放 URL 并预热字节。
   * 目标：ended 事件触发时无需任何网络请求即可换 src + play()。
   * （服务端生成预热由 playerStore.preloadNextArticle 在播放开始 5s 后触发，
   *   到这里通常已 final_ready，只需取 URL。）
   */
  const maybePrefetchNextTrack = async () => {
    if (!playerStore) return

    // 注意：playerStore 是 Pinia setup-store 代理，ref 已自动解包，直接读属性（不能用 .value）
    const playlist = playerStore.playlist || []
    const nextIndex = (playerStore.currentIndex ?? -1) + 1
    const next = playlist[nextIndex]

    if (!shouldPrefetchNextTrack({
      currentTime: currentTime.value,
      totalTime: totalTime.value,
      hasNext: Boolean(next?.id),
      // 预取结果必须与"当前下一篇"匹配才算命中，防止列表变更后旧预取阻塞新预取
      prefetched: Boolean(
        nextTrackPrefetch &&
        nextTrackPrefetch.articleId === next?.id &&
        (nextTrackPrefetch.finalUrl || nextTrackPrefetch.segment0Url)
      ),
      inFlight: nextTrackPrefetchInFlight,
      lastAttemptAt: nextTrackPrefetchAttemptAt,
      now: Date.now(),
      thresholdSec: NEXT_TRACK_PREFETCH_THRESHOLD_SEC,
      retryMs: NEXT_TRACK_PREFETCH_RETRY_MS
    })) {
      return
    }

    nextTrackPrefetchInFlight = true
    nextTrackPrefetchAttemptAt = Date.now()

    try {
      const voice = currentCloudSource.value?.voice || null
      const status = await getTtsPrepareStatus(next.id, { voice })

      // 每个 await 后都校验下一篇身份：预取期间用户可能切歌/重排列表
      const stillNext = () => (playerStore.playlist || [])[(playerStore.currentIndex ?? -1) + 1]
      if (!stillNext() || stillNext().id !== next.id) return

      if (status?.final_ready) {
        const finalUrl = await getTtsPlayUrl(next.id, { voice })
        if (!stillNext() || stillNext().id !== next.id) return
        nextTrackPrefetch = {
          articleId: next.id,
          article: stillNext(),
          finalUrl,
          duration: status.total_duration_sec || 0,
          voice
        }
        warmNextTrackBytes(finalUrl)
        console.log(`[useTTS] Prefetched next track final audio: ${next.id}`)
      } else if (Array.isArray(status?.segments)) {
        const seg0 = status.segments.find(s => s.index === 0 && s.status === 'ready')
        if (seg0) {
          const segment0Url = await getTtsSegmentPlayUrl(next.id, 0, { voice })
          if (!stillNext() || stillNext().id !== next.id) return
          nextTrackPrefetch = {
            articleId: next.id,
            article: stillNext(),
            segment0Url,
            segment0End: seg0.end_offset_sec || 0,
            voice
          }
          warmNextTrackBytes(segment0Url)
          console.log(`[useTTS] Prefetched next track segment 0: ${next.id}`)
        }
      }
      // 未就绪：保持未预取状态，shouldPrefetchNextTrack 的 retryMs 控制下次尝试
    } catch (error) {
      console.warn('[useTTS] Next track prefetch failed:', error)
    } finally {
      nextTrackPrefetchInFlight = false
    }
  }

  /**
   * ended 事件内的同步快速交接：预取命中时直接换 src + play()。
   * 不经过 cleanupAudio/loadAudio（不拆音频会话、零网络请求），
   * 是 iOS 后台连播成功的关键路径。返回 true 表示已接管。
   */
  const tryFastNextTrackHandoff = () => {
    if (!playerStore || !nextTrackPrefetch) return false

    // playerStore 是 Pinia 代理，ref 已解包，直接读属性
    const playlist = playerStore.playlist || []
    const nextIndex = (playerStore.currentIndex ?? -1) + 1
    const next = playlist[nextIndex]
    if (!next || next.id !== nextTrackPrefetch.articleId) {
      // 列表已变化：丢弃过期预取，让 maybePrefetchNextTrack 重新预取正确的下一篇
      clearNextTrackPrefetch()
      return false
    }

    const prefetch = nextTrackPrefetch
    nextTrackPrefetch = null // 消费预取结果
    nextTrackPrefetchAttemptAt = 0

    const url = prefetch.finalUrl || prefetch.segment0Url
    if (!url) return false

    // ---------- 同步临界区：同一元素换 src + play()，禁止任何 await ----------
    ensureAudioInstance()
    const audio = globalAudio.value

    // 作废上一篇的挂起异步链（轮询/恢复/waitForAudioReady 均按 token/session 自检退出）
    clearCloudPolling()
    cloudSessionId += 1
    audioLoadToken += 1
    cloudRecoveryAttempts = 0
    isRecoveringCloudPlayback = false
    internalPauseReason = null
    clearNextSegmentPrefetch()

    const useFinal = Boolean(prefetch.finalUrl)
    currentCloudSource.value = {
      type: 'cloud_v2',
      articleId: prefetch.articleId,
      voice: prefetch.voice || null,
      apiBaseUrl: currentCloudSource.value?.apiBaseUrl || ''
    }
    cloudPlaybackMode.value = useFinal ? 'final' : 'segmented'
    cloudPrepareStatus.value = null // 新曲目状态未知，交由轮询刷新
    currentSegmentIndex.value = useFinal ? null : 0
    segmentStartOffset.value = 0
    currentArticle.value = prefetch.article

    audio.src = url
    currentAudioUrl.value = url
    audio.playbackRate = playbackRate.value
    const playPromise = audio.play()

    currentTime.value = 0
    totalTime.value = prefetch.duration || prefetch.segment0End || 0
    isPlaying.value = false // 'play' 事件到达后翻转
    isPaused.value = false
    isLoading.value = true
    loadError.value = null
    suppressAutoResume = false
    playbackStartedThisSource = false // 新源，'play' 事件到达后置真

    // 锁屏 Now Playing 立即切到新曲目，避免系统认为会话已死
    setupMediaSession(prefetch.article, resolveFeedName(prefetch.article))

    if (!useFinal) {
      scheduleCloudPolling(currentCloudSource.value, cloudSessionId)
    }
    // ---------- 临界区结束 ----------

    // store 簿记（index 前进/完成上报/状态保存/N+2 服务端预热）异步进行，不阻塞交接
    if (playerStore?.onNextTrackHandoff) {
      playerStore.onNextTrackHandoff(prefetch.article)
    }

    playPromise.then(() => {
      isLoading.value = false
      lastCloudPlaybackError = null
      trackAudioTrackHandoff({
        article_id: prefetch.articleId,
        success: true,
        mode: cloudPlaybackMode.value
      })
    }).catch((error) => {
      // 播放被拒（如 iOS 会话已被系统回收）：落为"下一篇已暂停"的可恢复态
      console.warn('[useTTS] Fast handoff play() rejected:', error)
      isLoading.value = false
      isPaused.value = true
      trackAudioTrackHandoff({
        article_id: prefetch.articleId,
        success: false,
        mode: cloudPlaybackMode.value,
        error_message: error?.message || 'handoff_play_rejected'
      })
    })

    console.log(`[useTTS] Fast handoff to next track ${prefetch.articleId} (${useFinal ? 'final' : 'segment0'})`)
    return true
  }

  const resolveFeedName = (article) => {
    try {
      const feedStore = useFeedStore()
      if (feedStore?.feeds?.length > 0 && article?.source) {
        const feed = feedStore.feeds.find(f => f.feed_url === article.source)
        if (feed) return feed.feed_name
      }
    } catch (e) {
      // 忽略 feedStore 获取失败
    }
    return null
  }

  const setMediaSessionPlaybackState = (state) => {
    if (!('mediaSession' in navigator)) return
    try {
      navigator.mediaSession.playbackState = state
    } catch (error) {
      // 忽略旧版本浏览器的错误
    }
  }

  // ==================== Media Session API ====================

  const setupMediaSession = (article, feedName = null) => {
    if (!('mediaSession' in navigator)) return

    try {
      // 智能选择 artist：优先使用作者名，其次使用 feed 名称，最后回退到 Readaria
      const artist = article.author?.trim() || feedName || 'Readaria'
      navigator.mediaSession.metadata = new MediaMetadata({
        title: article.title || t('tts.nowPlaying'),
        artist: artist,
        album: article.source || 'Readaria RSS Reader',
        artwork: [
          { src: '/apple-touch-icon.png', sizes: '180x180', type: 'image/png' }
        ]
      })

      navigator.mediaSession.setActionHandler('play', () => {
        // 锁屏/控制中心恢复：元素可能已被中断损坏，需要韧性恢复而非裸 play()
        resumePlaybackResilient('media_session')
      })

      navigator.mediaSession.setActionHandler('pause', () => {
        pause()
      })

      navigator.mediaSession.setActionHandler('seekbackward', (details) => {
        const skipTime = details.seekOffset || 15
        backward(skipTime)
      })

      navigator.mediaSession.setActionHandler('seekforward', (details) => {
        const skipTime = details.seekOffset || 15
        forward(skipTime)
      })

      navigator.mediaSession.setActionHandler('seekto', (details) => {
        if (details.seekTime !== undefined) {
          seekTo(details.seekTime)
        }
      })

      navigator.mediaSession.setActionHandler('previoustrack', () => {
        if (playerStore?.playPrevious) {
          playerStore.playPrevious()
        }
      })

      navigator.mediaSession.setActionHandler('nexttrack', () => {
        if (playerStore?.playNext) {
          playerStore.playNext()
        }
      })
    } catch (error) {
      console.warn('[useTTS] Media Session setup failed:', error)
    }
  }

  const updateMediaSessionPositionState = () => {
    if (!('mediaSession' in navigator) || !globalAudio.value) return

    try {
      navigator.mediaSession.setPositionState({
        duration: totalTime.value || 0,
        playbackRate: globalAudio.value.playbackRate || 1.0,
        position: currentTime.value || 0
      })
    } catch (error) {
      // 忽略旧版本浏览器的错误
    }
  }

  const clearMediaSession = () => {
    if (!('mediaSession' in navigator)) return

    try {
      navigator.mediaSession.metadata = null
      const actions = ['play', 'pause', 'seekbackward', 'seekforward', 'seekto', 'nexttrack', 'previoustrack']
      actions.forEach(action => {
        try {
          navigator.mediaSession.setActionHandler(action, null)
        } catch (e) {}
      })
    } catch (error) {
      console.warn('[useTTS] Clear Media Session failed:', error)
    }
  }

  /**
   * 将服务端返回的 TTS 错误信息解析为用户友好的 i18n 消息
   * 支持两种格式：
   * - 新格式：英文错误码（如 "segment_0_failed: quota_exhausted"）
   * - 旧格式：中文错误信息（向后兼容）
   */
  const _resolveTtsError = (errorInfo, tFn) => {
    if (!errorInfo) return tFn('tts.audioGenerationFailed')

    // 提取错误码：支持 "segment_0_failed: quota_exhausted" 或 "quota_exhausted"
    const codeMatch = errorInfo.match(/(?:segment_\d+_failed:\s*)?(\w+)$/)
    const code = codeMatch ? codeMatch[1] : null

    // 错误码到 i18n key 的映射
    const CODE_MAP = {
      'quota_exhausted': 'tts.quotaExhausted',
      'rate_limited': 'tts.rateLimited',
      'service_misconfigured': 'tts.serviceMisconfigured',
      'generation_timeout': 'tts.generationTimeout',
      'network_error': 'tts.networkError',
      'content_not_allowed': 'tts.contentNotAllowed',
      'generation_failed': 'tts.serviceUnavailable'
    }

    if (code && CODE_MAP[code]) {
      return tFn(CODE_MAP[code])
    }

    // 兼容旧的中文错误信息格式（包含中文字符）
    if (/[\u4e00-\u9fa5]/.test(errorInfo)) {
      return errorInfo
    }

    // 兜底提示
    return tFn('tts.serviceUnavailable')
  }

  const wait = (ms) => new Promise(resolve => setTimeout(resolve, ms))

  const waitForAudioReady = (timeoutMs = 15000) => {
    const expectedToken = audioLoadToken
    if (!globalAudio.value) {
      return Promise.resolve()
    }

    if (isStaleAudioLoadToken(expectedToken)) {
      return Promise.reject(createAudioLoadSupersededError())
    }

    if (globalAudio.value.readyState >= 1) {
      return Promise.resolve()
    }

    return new Promise((resolve, reject) => {
      let settled = false
      const startTime = performance.now()
      const finish = ({ didTimeout = false, loadError = null } = {}) => {
        if (settled) return
        settled = true
        globalAudio.value?.removeEventListener('loadedmetadata', onReady)
        globalAudio.value?.removeEventListener('canplay', onReady)
        globalAudio.value?.removeEventListener('error', onError)
        globalAudio.value?.removeEventListener('emptied', onAbort)
        globalAudio.value?.removeEventListener('abort', onAbort)
        clearTimeout(timer)
        if (isStaleAudioLoadToken(expectedToken)) {
          reject(createAudioLoadSupersededError())
          return
        }
        if (didTimeout) {
          reject(createAudioSourceNotReadyError())
          return
        }
        if (loadError) {
          reject(loadError)
          return
        }
        const elapsed = performance.now() - startTime
        if (elapsed > 10000) {
          captureMessage('TTS audio ready slow (>10s)', {
            level: 'warning',
            extra: { elapsedMs: Math.round(elapsed), articleId: currentCloudSource.value?.articleId }
          })
        }
        resolve()
      }
      const onReady = () => finish()
      const onError = () => finish({ loadError: createAudioSourceNotReadyError() })
      const onAbort = (event) => {
        if (isStaleAudioLoadToken(expectedToken)) {
          finish()
          return
        }
        // HTMLMediaElement can emit abort/emptied during a normal src swap
        // before the new resource becomes ready. Treat it as superseded only
        // when a newer load token has already taken ownership.
        console.log(
          `[useTTS] Ignoring transient ${event?.type || 'abort'} while waiting for active audio source`
        )
      }
      const timer = setTimeout(() => finish({ didTimeout: true }), timeoutMs)
      globalAudio.value.addEventListener('loadedmetadata', onReady, { once: true })
      globalAudio.value.addEventListener('canplay', onReady, { once: true })
      globalAudio.value.addEventListener('error', onError, { once: true })
      globalAudio.value.addEventListener('emptied', onAbort)
      globalAudio.value.addEventListener('abort', onAbort)
    })
  }

  const hasReadySegment = (status, targetTime = 0) => {
    return Boolean(findSegmentInStatus(status, targetTime) || findSegmentInStatus(status, 0))
  }

  const applyCloudPrepareStatus = (status) => {
    cloudPrepareStatus.value = status
    if (status?.final_ready && status?.total_duration_sec) {
      totalTime.value = status.total_duration_sec
    } else if (status?.ready_duration_sec) {
      totalTime.value = Math.max(totalTime.value || 0, status.ready_duration_sec)
    }
  }

  const fetchCloudPrepareStatus = async (source, sessionId = cloudSessionId) => {
    const status = await getTtsPrepareStatus(source.articleId, { voice: source.voice })
    if (sessionId !== cloudSessionId) {
      return null
    }
    applyCloudPrepareStatus(status)
    return status
  }

  const scheduleCloudPolling = (source, sessionId = cloudSessionId, delayMs = 1000) => {
    clearCloudPolling()
    cloudPollTimer = setTimeout(async () => {
      try {
        if (sessionId !== cloudSessionId || !currentCloudSource.value) {
          return
        }

        const status = await fetchCloudPrepareStatus(source, sessionId)
        if (!status) return
        maybeWarmFinalAudio(source, status)
      } catch (error) {
        console.warn('[useTTS] Cloud polling failed:', error)
      } finally {
        if (sessionId === cloudSessionId && currentCloudSource.value && cloudPlaybackMode.value !== 'final') {
          scheduleCloudPolling(source, sessionId, getCloudPreparePollDelay(cloudPrepareStatus.value) || delayMs)
        }
      }
    }, delayMs)
  }

  /**
   * 分段播放期间一旦 final 整篇就绪，立即取签名 URL 并预热字节。
   * 这样分段边界切到 final（需要 seek，无法跳过 metadata 等待）时，
   * loadedmetadata 能命中 HTTP 缓存快速到达，提高 iOS 后台切换存活率。
   */
  const maybeWarmFinalAudio = async (source, status) => {
    if (!status?.final_ready) return
    if (cloudPlaybackMode.value !== 'segmented') return
    if (warmedFinalForArticle === source.articleId) return

    warmedFinalForArticle = source.articleId
    try {
      const finalUrl = await getTtsPlayUrl(source.articleId, { voice: source.voice })
      if (warmedFinalForArticle !== source.articleId) return // 已切走
      if (!finalWarmPreloader) {
        finalWarmPreloader = createSegmentPreloader()
      }
      finalWarmPreloader.src = finalUrl
      finalWarmPreloader.load()
      console.log(`[useTTS] Warmed final audio bytes for article ${source.articleId}`)
    } catch (error) {
      console.warn('[useTTS] Final audio warm-up failed:', error)
    }
  }

  const findSegmentInStatus = (status, targetTime) => {
    if (!Array.isArray(status?.segments)) return null
    return status.segments.find(segment => (
      segment.status === 'ready' &&
      targetTime >= (segment.start_offset_sec ?? 0) &&
      targetTime < (segment.end_offset_sec ?? 0)
    )) || null
  }

  const getNextReadySegment = (status, index) => {
    if (!Array.isArray(status?.segments)) return null
    return status.segments.find(segment => (
      segment.index === index + 1 && segment.status === 'ready'
    )) || null
  }

  const clearNextSegmentPrefetch = () => {
    if (nextSegmentPreloader) {
      try {
        nextSegmentPreloader.pause()
        nextSegmentPreloader.src = ''
      } catch (error) {
        console.warn('[useTTS] Failed to clear next segment prefetch:', error)
      }
      nextSegmentPreloader = null
    }
    prefetchedNextSegmentIndex.value = null
    prefetchedNextSegmentUrl.value = null
  }

  const prefetchNextSegment = async (source, segment) => {
    if (!source || !segment) return
    if (prefetchedNextSegmentIndex.value === segment.index) return

    clearNextSegmentPrefetch()
    try {
      const audioUrl = await getTtsSegmentPlayUrl(source.articleId, segment.index, { voice: source.voice })
      prefetchedNextSegmentUrl.value = audioUrl
      prefetchedNextSegmentIndex.value = segment.index

      nextSegmentPreloader = createSegmentPreloader()
      nextSegmentPreloader.src = audioUrl
      nextSegmentPreloader.load()
    } catch (error) {
      console.warn('[useTTS] Next segment preload failed:', error)
      prefetchedNextSegmentUrl.value = null
      prefetchedNextSegmentIndex.value = null
      nextSegmentPreloader = null
    }
  }

  const maybePrepareNextSegment = async () => {
    if (
      cloudPlaybackMode.value !== 'segmented' ||
      !currentCloudSource.value ||
      currentSegmentIndex.value == null ||
      !globalAudio.value ||
      isCheckingNearEndTransition
    ) {
      return
    }

    const activeSegment = findSegmentInStatus(
      cloudPrepareStatus.value,
      getActiveGlobalTime()
    )
    const activeEnd = activeSegment?.end_offset_sec
    if (activeEnd == null) return

    const remaining = activeEnd - getActiveGlobalTime()
    if (remaining > 5) return
    if (prefetchedNextSegmentIndex.value === (currentSegmentIndex.value ?? -1) + 1) return

    isCheckingNearEndTransition = true
    try {
      const status = await fetchCloudPrepareStatus(currentCloudSource.value, cloudSessionId)
      if (!status || cloudPlaybackMode.value !== 'segmented') {
        return
      }

      const nextSegment = getNextReadySegment(status, currentSegmentIndex.value)
      if (nextSegment) {
        await prefetchNextSegment(currentCloudSource.value, nextSegment)
      }
    } catch (error) {
      console.warn('[useTTS] Near-end next segment check failed:', error)
    } finally {
      isCheckingNearEndTransition = false
    }
  }

  const playSegmentByTime = async (source, targetTime = 0, options = {}) => {
    const { autoPlay = true, sessionId = cloudSessionId } = options
    const status = cloudPrepareStatus.value
    const segment = findSegmentInStatus(status, targetTime) || findSegmentInStatus(status, 0)

    if (!segment) {
      throw new Error('segment_not_ready')
    }

    ensureAudioInstance()
    currentCloudSource.value = source
    cloudPlaybackMode.value = 'segmented'
    currentSegmentIndex.value = segment.index
    segmentStartOffset.value = segment.start_offset_sec || 0
    if (prefetchedNextSegmentIndex.value !== segment.index) {
      clearNextSegmentPrefetch()
    }

    const localOffset = Math.max(0, targetTime - (segment.start_offset_sec || 0))
    const audioUrl = prefetchedNextSegmentIndex.value === segment.index && prefetchedNextSegmentUrl.value
      ? prefetchedNextSegmentUrl.value
      : await getTtsSegmentPlayUrl(source.articleId, segment.index, { voice: source.voice })
    const loadToken = startAudioSourceLoad(`segment-${segment.index}`)
    globalAudio.value.src = audioUrl
    currentAudioUrl.value = audioUrl
    globalAudio.value.load()

    // 重新设置播放速率（浏览器改变 src 后可能重置 playbackRate）
    globalAudio.value.playbackRate = playbackRate.value

    // 快速路径：顺序切换到本地偏移 0 的分段（ended 边界/恢复起点）时跳过
    // waitForAudioReady 直接 play()。等待仅在需要 seek 时必要（定位要 metadata），
    // 跳过可消除 ended→play 之间的事件往返，是 iOS 后台分段切换存活的关键。
    const needsSeek = localOffset > 0

    if (needsSeek) {
      try {
        await waitForAudioReady()
      } catch (error) {
        finishAudioSourceLoad(loadToken)
        if (isAudioLoadSupersededError(error)) {
          return
        }
        throw error
      }

      if (sessionId !== cloudSessionId || isStaleAudioLoadToken(loadToken)) {
        finishAudioSourceLoad(loadToken)
        return
      }

      try {
        globalAudio.value.currentTime = localOffset
      } catch (error) {
        console.warn('[useTTS] Failed to seek inside segment:', error)
      }
    }

    currentTime.value = (segment.start_offset_sec || 0) + (globalAudio.value.currentTime || 0)
    totalTime.value = Math.max(getReadyDuration(), segment.end_offset_sec || 0)
    // 快速路径下保持 isLoading 直至 play() 落定，避免外层 store idle 轮询误判结束
    if (needsSeek || !autoPlay) {
      isLoading.value = false
    }
    if (prefetchedNextSegmentIndex.value === segment.index) {
      clearNextSegmentPrefetch()
    }

    if (autoPlay) {
      try {
        await globalAudio.value.play()
      } catch (error) {
        finishAudioSourceLoad(loadToken)
        isLoading.value = false
        if (isAudioLoadSupersededError(error) || (error?.name === 'AbortError' && isStaleAudioLoadToken(loadToken))) {
          return
        }
        endInternalAudioTransition('segment-play-failed')
        throw error
      }
      finishAudioSourceLoad(loadToken)
      isLoading.value = false
      cloudRecoveryAttempts = 0
      lastCloudPlaybackError = null
    } else {
      finishAudioSourceLoad(loadToken)
      endInternalAudioTransition('segment-ready')
    }
  }

  const playFinalAudio = async (source, targetTime = 0, options = {}) => {
    const { autoPlay = true, sessionId = cloudSessionId } = options
    ensureAudioInstance()
    currentCloudSource.value = source
    cloudPlaybackMode.value = 'final'
    currentSegmentIndex.value = null
    segmentStartOffset.value = 0
    clearNextSegmentPrefetch()

    const audioUrl = await getTtsPlayUrl(source.articleId, { voice: source.voice })
    const loadToken = startAudioSourceLoad('final-audio')
    globalAudio.value.src = audioUrl
    currentAudioUrl.value = audioUrl
    globalAudio.value.load()

    // 重新设置播放速率（浏览器改变 src 后可能重置 playbackRate）
    globalAudio.value.playbackRate = playbackRate.value

    try {
      await waitForAudioReady()
    } catch (error) {
      finishAudioSourceLoad(loadToken)
      if (isAudioLoadSupersededError(error)) {
        return
      }
      lastCloudPlaybackError = error
      const status = cloudPrepareStatus.value || await fetchCloudPrepareStatus(source, sessionId)
      if (sessionId !== cloudSessionId) return
      if (hasReadySegment(status, targetTime)) {
        console.warn('[useTTS] Final audio not ready, falling back to segmented playback')
        await playSegmentByTime(source, targetTime, { autoPlay, sessionId })
        return
      }
      throw error
    }

    if (sessionId !== cloudSessionId || isStaleAudioLoadToken(loadToken)) {
      finishAudioSourceLoad(loadToken)
      return
    }

    if (targetTime > 0) {
      try {
        globalAudio.value.currentTime = targetTime
      } catch (error) {
        console.warn('[useTTS] Failed to seek final audio:', error)
      }
    }

    currentTime.value = globalAudio.value.currentTime || targetTime || 0
    totalTime.value = globalAudio.value.duration || cloudPrepareStatus.value?.total_duration_sec || totalTime.value
    isLoading.value = false

    if (autoPlay) {
      try {
        await globalAudio.value.play()
      } catch (error) {
        finishAudioSourceLoad(loadToken)
        if (isAudioLoadSupersededError(error) || (error?.name === 'AbortError' && isStaleAudioLoadToken(loadToken))) {
          return
        }
        endInternalAudioTransition('final-play-failed')
        console.error('[useTTS] Final audio autoplay failed:', error)
        const status = cloudPrepareStatus.value || await fetchCloudPrepareStatus(source, sessionId)
        if (sessionId !== cloudSessionId) return
        if (hasReadySegment(status, targetTime)) {
          console.warn('[useTTS] Final autoplay failed, falling back to segmented playback')
          await playSegmentByTime(source, targetTime, { autoPlay, sessionId })
          return
        }
        throw error
      }
      finishAudioSourceLoad(loadToken)
      cloudRecoveryAttempts = 0
      lastCloudPlaybackError = null
    } else {
      finishAudioSourceLoad(loadToken)
      endInternalAudioTransition('final-ready')
    }
  }

  const recoverCloudPlayback = async () => {
    if (
      isRecoveringCloudPlayback ||
      !currentCloudSource.value ||
      !['segmented', 'final'].includes(cloudPlaybackMode.value || '')
    ) {
      return
    }

    if (cloudRecoveryAttempts >= 2) {
      return
    }

    // 避免在分段切换过程中触发恢复，防止与 handleCloudSegmentEnded 竞争 audio.src
    if (internalPauseReason && internalPauseReason.startsWith('segment-')) {
      console.log(`[useTTS] Suppressing recovery during active segment transition: ${internalPauseReason}`)
      return
    }

    isRecoveringCloudPlayback = true
    cloudRecoveryAttempts += 1
    isLoading.value = true

    try {
      const resumeTime = currentTime.value || getActiveGlobalTime()
      const source = currentCloudSource.value
      const status = await fetchCloudPrepareStatus(source, cloudSessionId)

      if (!status) {
        throw new Error('recover_status_unavailable')
      }

      if (status.status === 'failed') {
        throw new Error(_resolveTtsError(status.error_info, t))
      }

      if (status.final_ready) {
        await playFinalAudio(source, resumeTime, { autoPlay: true, sessionId: cloudSessionId })
        return
      }

      const targetSegment = findSegmentInStatus(status, resumeTime)
      if (targetSegment) {
        // Recovery path uses a smaller tolerance than the ended-transition path,
        // because recovery is usually triggered by real playback errors, not
        // browser/pydub duration drift. We should not skip content silently.
        const RECOVERY_NEAR_END_TOLERANCE = 1.0
        const nearEnd = (targetSegment.end_offset_sec ?? 0) - resumeTime < RECOVERY_NEAR_END_TOLERANCE
        if (targetSegment.index === currentSegmentIndex.value && cloudPlaybackMode.value === 'segmented' && nearEnd) {
          const nextSeg = getNextReadySegment(status, targetSegment.index)
          if (nextSeg) {
            await playSegmentByTime(source, nextSeg.start_offset_sec || 0, { autoPlay: true, sessionId: cloudSessionId })
            return
          }
          // Next segment not ready — delegate to polling instead of replaying current segment tail
          await waitForCloudPlayable(source, resumeTime, { autoPlay: true, sessionId: cloudSessionId })
          return
        }
        await playSegmentByTime(source, resumeTime, { autoPlay: true, sessionId: cloudSessionId })
        return
      }

      await waitForCloudPlayable(source, resumeTime, { autoPlay: true, sessionId: cloudSessionId })
    } finally {
      isRecoveringCloudPlayback = false
      isLoading.value = false
    }
  }

  const waitForCloudPlayable = async (source, targetTime = 0, options = {}) => {
    const { autoPlay = true, sessionId = cloudSessionId } = options
    const targetLabel = targetTime > 0 ? t('tts.preparingTargetAudio') : t('tts.generating')
    let notifiedTargetWait = false

    while (sessionId === cloudSessionId) {
      const status = await fetchCloudPrepareStatus(source, sessionId)
      if (!status) return

      if (status.status === 'failed') {
        throw new Error(_resolveTtsError(status.error_info, t))
      }

      if (status.final_ready) {
        await playFinalAudio(source, targetTime, { autoPlay, sessionId })
        scheduleCloudPolling(source, sessionId)
        return
      }

      const readySegment = findSegmentInStatus(status, targetTime)
      if (readySegment && status.first_playable_ready) {
        // Avoid replaying the same segment that just ended. Browser-reported
        // audio duration can be slightly less than backend-computed end_offset_sec,
        // causing targetTime to still fall within the current segment's bounds.
        const nearEnd = (readySegment.end_offset_sec ?? 0) - targetTime < SEGMENT_END_TOLERANCE_SEC
        if (readySegment.index === currentSegmentIndex.value && cloudPlaybackMode.value === 'segmented' && nearEnd) {
          const nextSeg = getNextReadySegment(status, readySegment.index)
          if (nextSeg) {
            await playSegmentByTime(source, nextSeg.start_offset_sec || 0, { autoPlay, sessionId })
            scheduleCloudPolling(source, sessionId)
            return
          }
          // Next segment not ready yet — keep waiting instead of replaying current
          await wait(getCloudPreparePollDelay(status))
          continue
        }
        await playSegmentByTime(source, targetTime, { autoPlay, sessionId })
        scheduleCloudPolling(source, sessionId)
        return
      }

      if (!notifiedTargetWait) {
        showToast({
          message: targetLabel,
          duration: 1500
        })
        notifiedTargetWait = true
      }

      cloudPlaybackMode.value = 'preparing'
      isLoading.value = true
      await wait(getCloudPreparePollDelay(status))
    }
  }

  const handleCloudSegmentEnded = async () => {
    const source = currentCloudSource.value
    if (!source) {
      return
    }

    const sessionId = cloudSessionId
    const finishedTime = getActiveGlobalTime()
    isPlaying.value = false
    isPaused.value = false
    isLoading.value = true
    currentTime.value = finishedTime

    const status = cloudPrepareStatus.value || await fetchCloudPrepareStatus(source, sessionId)
    if (!status || sessionId !== cloudSessionId) {
      return
    }

    if (status.final_ready) {
      await playFinalAudio(source, finishedTime, { autoPlay: true, sessionId })
      scheduleCloudPolling(source, sessionId)
      return
    }

    const nextSegment = Array.isArray(status.segments)
      ? status.segments.find(segment => segment.index === (currentSegmentIndex.value ?? -1) + 1 && segment.status === 'ready')
      : null

    if (nextSegment) {
      await playSegmentByTime(source, nextSegment.start_offset_sec || 0, { autoPlay: true, sessionId })
      scheduleCloudPolling(source, sessionId)
      return
    }

    isLoading.value = true
    await waitForCloudPlayable(source, finishedTime, { autoPlay: true, sessionId })
  }

  const startCloudPlayback = async (source, startTime = 0) => {
    currentCloudSource.value = source
    const sessionId = cloudSessionId
    isLoading.value = true
    loadError.value = null
    cloudPlaybackMode.value = 'preparing'

    const initialStatus = await startTtsPrepare(source.articleId, { voice: source.voice })
    if (sessionId !== cloudSessionId) {
      return
    }

    applyCloudPrepareStatus(initialStatus)
    await waitForCloudPlayable(source, startTime, { autoPlay: true, sessionId })
  }

  // ==================== 核心播放 API ====================

  /**
   * 加载并播放文章
   * @param {Object} article - 文章对象
   * @param {Object} options - 播放选项
   */
  const loadAudio = async (article, options = {}) => {
    const { startTime = 0, rate = 1.0, onTierChange: externalOnTierChange } = options

    if (!article || !article.id) {
      throw new Error('Invalid article')
    }

    try {
      isLoading.value = true
      loadError.value = null
      currentArticle.value = article
      playbackRate.value = rate

      // 停止之前的播放
      cleanupAudio()
      await primeAudioForUserGesture()

      // 使用 TTS Manager 选择最佳引擎并播放
      const result = await ttsManager.playArticle(article, {
        autoPlay: true,
        startTime,
        requireHighQuality: options.requireHighQuality,
        onTierChange: (tier, reason) => {
          currentTier.value = tier
          console.log(`[useTTS] Tier changed to ${tier}, reason: ${reason}`)

          // 转发到外部回调
          if (externalOnTierChange) {
            externalOnTierChange(tier, reason)
          }
        },
        onProgress: (progressData) => {
          if (progressData.status === 'loading') {
            isLoading.value = true
          } else if (progressData.status === 'synthesizing') {
            isLoading.value = true
          } else if (progressData.status === 'complete') {
            isLoading.value = false
          }
        },
        onError: (error) => {
          console.error('[useTTS] TTS error:', error)
          loadError.value = error.message
        }
      })

      // 保存当前层级
      currentTier.value = result.tier

      // 云端播放 - 使用 prepare + final/segments 稳定播放
      await playCloudAudio(result.audioUrl, startTime)

      // 配置 Media Session（尝试从 feedStore 解析 feed 名称作为 author 备选）
      setupMediaSession(article, resolveFeedName(article))

      // 预加载下一篇
      if (playerStore?.preloadNextArticle) {
        setTimeout(() => {
          playerStore.preloadNextArticle()
        }, 5000)
      }

      return true
    } catch (error) {
      console.error('[useTTS] Load audio failed:', error)
      if (error?.name === 'NotAllowedError') {
        isPlaying.value = false
        isPaused.value = true
        loadError.value = null
      } else {
        loadError.value = error.message
      }
      isLoading.value = false

      throw error
    }
  }

  /**
   * 播放云端音频
   */
  const playCloudAudio = async (audioUrl, startTime) => {
    if (audioUrl && typeof audioUrl === 'object' && audioUrl.type === 'cloud_v2') {
      await startCloudPlayback(audioUrl, startTime)
      console.log('[useTTS] Cloud V2 audio playing')
      return
    }

    ensureAudioInstance()
    globalAudio.value.src = audioUrl
    currentAudioUrl.value = audioUrl

    // 重新设置播放速率（浏览器改变 src 后可能重置 playbackRate）
    globalAudio.value.playbackRate = playbackRate.value

    if (startTime > 0) {
      globalAudio.value.currentTime = startTime
    }

    await globalAudio.value.play()
    isLoading.value = false

    console.log('[useTTS] Cloud audio playing')
  }

  // ==================== 播放控制 ====================

  /**
   * 播放
   */
  const play = async () => {
    if (!globalAudio.value) {
      showToast(t('tts.pleaseLoadAudioFirst'))
      return
    }

    try {
      await globalAudio.value.play()
      ensurePlaybackRateApplied('manual-play')
    } catch (error) {
      console.error('[useTTS] Play failed:', error)
      showToast(t('tts.playFailed'))
    }
  }

  /**
   * 暂停
   */
  const pause = () => {
    if (globalAudio.value) {
      manualPause = true
      globalAudio.value.pause()
    }
  }

  /**
   * 停止
   */
  const stop = () => {
    cleanupAudio()
    isPlaying.value = false
    isPaused.value = false
    currentTime.value = 0
    totalTime.value = 0
    clearMediaSession()
  }

  /**
   * 跳转到指定时间
   */
  const seekTo = (time) => {
    if (!globalAudio.value) return

    const duration = totalTime.value || globalAudio.value.duration || 0
    const targetTime = Math.max(0, Math.min(time, duration))

    if (cloudPlaybackMode.value === 'segmented') {
      const targetSegment = findSegmentForTime(targetTime)
      if (!targetSegment) {
        showToast({
          message: t('tts.targetPositionGenerating'),
          type: 'warning',
          duration: 2000
        })
        return
      }

      pendingSeekTime.value = targetTime
      isLoading.value = true
      playSegmentByTime(currentCloudSource.value, targetTime, {
        autoPlay: !globalAudio.value.paused
      }).catch((error) => {
        console.error('[useTTS] Segmented seek failed:', error)
        loadError.value = error.message
      }).finally(() => {
        pendingSeekTime.value = null
      })
      return
    }

    globalAudio.value.currentTime = targetTime
    currentTime.value = targetTime
    updateMediaSessionPositionState()
  }

  /**
   * 快进
   */
  const forward = (seconds = 15) => {
    if (!globalAudio.value) return
    seekTo(getActiveGlobalTime() + seconds)
  }

  /**
   * 快退
   */
  const backward = (seconds = 15) => {
    if (!globalAudio.value) return
    seekTo(getActiveGlobalTime() - seconds)
  }

  /**
   * 设置播放速度
   */
  const setRate = (rate) => {
    playbackRate.value = rate
    if (globalAudio.value) {
      globalAudio.value.playbackRate = rate
      updateMediaSessionPositionState()
    }
  }

  // ==================== 状态查询 ====================

  /**
   * 获取当前 TTS 层级
   */
  const getCurrentTier = () => currentTier.value

  /**
   * 获取 TTS 状态
   */
  const getTierStatus = () => ttsManager.getTierStatus()

  // ==================== 组件清理 ====================

  onUnmounted(() => {
    // 注意：不清理全局音频实例，因为它是单例
    // 只清理当前组件相关的状态
  })

  // ==================== 返回接口 ====================

  return {
    // 状态
    isPlaying,
    isPaused,
    isLoading,
    loadError,
    currentArticle,
    currentTier,
    cloudPlaybackMode,

    // 进度
    currentTime,
    totalTime,
    progress,
    playbackRate,

    // 核心方法
    loadAudio,
    play,
    pause,
    stop,
    seekTo,
    forward,
    backward,
    setRate,
    resumePlayback: resumePlaybackResilient, // 韧性恢复（锁屏/中断/断流后）

    // 状态查询
    getCurrentTier,
    getTierStatus,

    // 工具方法
    cleanup: stop
  }
}

export default useTTS
