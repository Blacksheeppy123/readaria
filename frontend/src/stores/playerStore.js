import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { showToast } from 'vant'
import { checkTtsCache } from '@/api/tts'
import { getPlaybackState, updatePlaybackState } from '@/api/playbackState'
import * as ttsManager from '@/services/tts/ttsManager'
import { trackTtsFirstPlay, trackAudioCompleted, trackAudioError } from '@/utils/analytics'
import {
  serializePlaylist,
  shouldHydrateArticleForTts
} from './playerPersistence'
import { shouldPreserveAsPaused } from '@/services/tts/playbackRecoveryPolicy'

const emitFirstAudioPlayed = () => {
  if (typeof window !== 'undefined' && !window.__firstAudioPlayedEmitted) {
    window.__firstAudioPlayedEmitted = true
    window.dispatchEvent(new CustomEvent('first-audio-played'))
    console.log('[PlayerStore] first-audio-played event emitted')
  }
}

// 用于去重：每个 session 中每篇文章只上报一次 tts_first_play
const reportedArticles = new Set()
const PROGRESS_SAVE_INTERVAL_MS = 5000
const PLAYBACK_STATE_SYNC_INTERVAL_MS = 10000
const RESUME_INTENT_KEY = 'tts_resume_intent'
const RESUME_INTENT_MAX_AGE_MS = 30 * 60 * 1000
const trackArticleFirstPlay = (article) => {
  const key = article?.id || article?.url
  if (key && !reportedArticles.has(key)) {
    reportedArticles.add(key)
    trackTtsFirstPlay({ article_id: key })
  }
}

const isTtsQuotaExceededError = (error) => (
  error?.response?.status === 429 ||
  error?.status === 429 ||
  (error?.message || '').includes('Daily TTS limit reached') ||
  (error?.message || '').includes('quota_exhausted') ||
  (error?.response?.data?.error || '').includes('Daily TTS limit reached') ||
  (error?.response?.data?.detail?.error || '').includes('Daily TTS limit reached')
)

/**
 * TTS 播放器全局状态管理
 * 负责管理播放状态、播放列表、进度等
 * 支持两层 TTS 架构：
 * - Tier 1: 云端高质量缓存 (OpenAI/Azure TTS)
 * - Tier 2: 云端实时生成 (OpenAI) / Web Speech API (降级)
 */
export const usePlayerStore = defineStore('player', () => {
  const { t } = useI18n()

  // ===== 播放状态 =====
  const isPlaying = ref(false) // 是否正在播放
  const isPaused = ref(false) // 是否暂停
  const isLoadingAudio = ref(false) // 是否正在加载音频（OpenAI TTS）
  const audioLoadError = ref(null) // 音频加载错误信息
  const useFallback = ref(false) // 是否使用 Web Speech API 降级
  const isActivatingFallback = ref(false) // Web Speech API 正在激活中
  const currentArticle = ref(null) // 当前播放文章 { url, title, content, source, ... }
  const pendingFallbackRequest = ref(null)

  // ===== 播放列表 =====
  const playlist = ref([]) // 文章队列
  const currentIndex = ref(0) // 当前播放位置索引

  // ===== 播放进度 =====
  const currentTime = ref(0) // 当前播放时间 (秒)
  const totalTime = ref(0) // 总时长 (秒)
  const progress = computed(() =>
    totalTime.value > 0 ? (currentTime.value / totalTime.value) * 100 : 0
  )

  // ===== 播放设置 =====
  const playbackRate = ref(1.0) // 播放速度 (0.75 - 2.0)
  const volume = ref(1.0) // 音量 (0 - 1)

  // ===== TTS 实例引用 =====
  let openAITts = null // useOpenAITts 返回的实例（优先，兼容旧代码）
  let legacyTts = null // useSpeechSynthesis 返回的实例（降级）
  let newTts = null // useTTS 返回的新 TTS 实例（新架构）

  // ===== 状态同步 interval 引用 =====
  let statusSyncIntervalId = null // 用于清理跨切换的 interval
  let idleSyncTicks = 0 // 避免分段切换时短暂 idle 被误判为播放结束
  let legacyPlaybackErrored = false // Web Speech 合成错误标记：让 idle 轮询区分"自然结束"与"运行时失败"
  let lastProgressSaveAt = 0
  let resumeAttemptInFlight = false

  // ===== 服务端同步状态 =====
  let lastPlaybackSyncAt = 0
  let playbackSyncTimer = null
  let playbackSyncInFlight = false
  let pendingPlaybackSync = false

  // ===== TTS 层级状态 =====
  const currentTier = ref(null) // 当前使用的 TTS 层级
  const tierStatus = ref({
    cloud_cached: { available: true },
    cloud_realtime: { available: true }
  })

  /**
   * 读取指定文章的本地进度
   */
  const getSavedProgressForArticle = (article) => {
    try {
      const progressStr = localStorage.getItem('tts_progress')
      if (!progressStr) return null
      const data = JSON.parse(progressStr)

      const elapsed = Date.now() - data.timestamp
      if (elapsed > 24 * 60 * 60 * 1000) return null
      if (data.url && article?.url && data.url !== article.url) return null

      return {
        currentTime: data.currentTime || 0,
        totalTime: data.totalTime || 0
      }
    } catch (e) {
      return null
    }
  }

  const saveResumeIntent = (reason = 'playing') => {
    if (!currentArticle.value) return

    try {
      localStorage.setItem(RESUME_INTENT_KEY, JSON.stringify({
        url: currentArticle.value.url,
        index: currentIndex.value,
        currentTime: currentTime.value,
        totalTime: totalTime.value,
        timestamp: Date.now(),
        reason
      }))
    } catch (error) {
      console.warn('[PlayerStore] Failed to save resume intent:', error)
    }
  }

  const clearResumeIntent = () => {
    try {
      localStorage.removeItem(RESUME_INTENT_KEY)
    } catch (error) {
      console.warn('[PlayerStore] Failed to clear resume intent:', error)
    }
  }

  const getResumeIntent = () => {
    try {
      const raw = localStorage.getItem(RESUME_INTENT_KEY)
      if (!raw) return null

      const intent = JSON.parse(raw)
      if (!intent?.url || !intent.timestamp) return null
      if (Date.now() - intent.timestamp > RESUME_INTENT_MAX_AGE_MS) {
        clearResumeIntent()
        return null
      }

      return intent
    } catch (error) {
      console.warn('[PlayerStore] Failed to read resume intent:', error)
      clearResumeIntent()
      return null
    }
  }

  const canSyncPlaybackState = () => {
    if (typeof navigator !== 'undefined' && !navigator.onLine) return false
    if (typeof localStorage === 'undefined') return false
    return !!localStorage.getItem('readaria_token')
  }

  const buildPlaybackState = () => ({
    playlist: serializePlaylist(playlist.value),
    current_index: currentIndex.value,
    current_time: currentTime.value,
    total_time: totalTime.value,
    current_article: currentArticle.value ? serializePlaylist([currentArticle.value])[0] : null,
    is_playing: isPlaying.value,
    playback_rate: playbackRate.value
  })

  const syncPlaybackState = async (force = false) => {
    if (!canSyncPlaybackState()) return

    const now = Date.now()
    if (!force && now - lastPlaybackSyncAt < PLAYBACK_STATE_SYNC_INTERVAL_MS) {
      pendingPlaybackSync = true
      if (!playbackSyncTimer) {
        playbackSyncTimer = setTimeout(() => {
          playbackSyncTimer = null
          syncPlaybackState(true)
        }, PLAYBACK_STATE_SYNC_INTERVAL_MS - (now - lastPlaybackSyncAt))
      }
      return
    }

    if (playbackSyncInFlight) {
      pendingPlaybackSync = true
      return
    }

    playbackSyncInFlight = true
    pendingPlaybackSync = false
    try {
      await updatePlaybackState(buildPlaybackState())
      lastPlaybackSyncAt = Date.now()
    } catch (error) {
      console.error('[PlayerStore] Failed to sync playback state:', error)
      lastPlaybackSyncAt = Date.now()
    } finally {
      playbackSyncInFlight = false
      if (pendingPlaybackSync) {
        syncPlaybackState()
      }
    }
  }

  const hydrateArticleForTts = async (article) => {
    if (!shouldHydrateArticleForTts(article)) {
      return article
    }

    if (typeof navigator !== 'undefined' && !navigator.onLine) {
      return article
    }

    try {
      const { getArticleByUrl } = await import('@/api/feeds')
      const response = await getArticleByUrl(article.url)
      const hydrated = response.article || article
      console.log(`[PlayerStore] Hydrated restored playlist article for TTS: ${hydrated.id || hydrated.url}`)
      return {
        ...article,
        ...hydrated
      }
    } catch (error) {
      console.warn('[PlayerStore] Failed to hydrate restored playlist article:', error)
      return article
    }
  }

  /**
   * 轮询缓存状态（cache_only）
   */
  const waitForCacheIfNeeded = async (articleId, retries = 2, delayMs = 1500) => {
    if (!articleId) return false
    for (let i = 0; i < retries; i++) {
      try {
        const res = await checkTtsCache(articleId)
        if (res && res.cache === 'hit') return true
      } catch (e) {
        // 忽略网络/解析错误，稍后重试
      }
      if (i < retries - 1) {
        await new Promise(resolve => setTimeout(resolve, delayMs))
      }
    }
    return false
  }

  /**
   * 设置 OpenAI TTS 实例引用
   * @param {Object} tts - useOpenAITts 返回的实例
   */
  const setOpenAITTSInstance = (tts) => {
    openAITts = tts
  }

  /**
   * 设置 Web Speech API TTS 实例引用（降级）
   * @param {Object} tts - useSpeechSynthesis 返回的实例
   */
  const setLegacyTTSInstance = (tts) => {
    legacyTts = tts
  }

  /**
   * 设置新 TTS 实例（三层架构）
   * @param {Object} tts - useTTS 返回的实例
   */
  const setNewTTSInstance = (tts) => {
    newTts = tts
  }

  /**
   * 初始化 TTS Manager
   */
  const initializeTTSManager = async () => {
    try {
      await ttsManager.initialize()
      tierStatus.value = ttsManager.getTierStatus()
      console.log('[PlayerStore] TTS Manager initialized')
    } catch (error) {
      console.error('[PlayerStore] TTS Manager init failed:', error)
    }
  }

  /**
   * 设置 TTS 实例引用（兼容旧代码）
   * @deprecated 使用 setOpenAITTSInstance 或 setLegacyTTSInstance
   */
  const setTTSInstance = (tts) => {
    // 默认设置为 legacy TTS
    legacyTts = tts
  }

  /**
   * 获取当前激活的 TTS 实例
   */
  const getCurrentTTS = () => {
    // 优先使用降级 TTS（Web Speech API）
    if (useFallback.value && legacyTts) return legacyTts
    // 其次使用新 TTS 架构
    if (newTts) return newTts
    return openAITts
  }

  /**
   * 清理状态同步 interval
   */
  const clearStatusSyncInterval = () => {
    if (statusSyncIntervalId) {
      clearInterval(statusSyncIntervalId)
      statusSyncIntervalId = null
    }
    idleSyncTicks = 0
  }

  const requestLegacyFallback = (article, startTime = 0) => {
    pendingFallbackRequest.value = {
      article,
      startTime
    }
  }

  const cancelLegacyFallbackRequest = () => {
    pendingFallbackRequest.value = null
  }

  const confirmLegacyFallback = async () => {
    const request = pendingFallbackRequest.value
    if (!request) return
    pendingFallbackRequest.value = null
    await playWithLegacyTTS(request.article, request.startTime)
  }

  const syncNewTtsState = () => {
    if (!newTts) return

    isPlaying.value = !!newTts.isPlaying?.value
    isPaused.value = !!newTts.isPaused?.value
    isLoadingAudio.value = !!newTts.isLoading?.value

    if (newTts.currentTime?.value !== undefined) {
      currentTime.value = newTts.currentTime.value
    }
    if (newTts.totalTime?.value !== undefined) {
      totalTime.value = newTts.totalTime.value
    }
  }

  const clearInactiveCurrentArticle = () => {
    if (isPlaying.value || isPaused.value || isLoadingAudio.value || isActivatingFallback.value) {
      return
    }

    currentArticle.value = null
    currentTier.value = null
    currentTime.value = 0
    totalTime.value = 0
    localStorage.removeItem('tts_progress')
  }

  /**
   * 播放指定文章
   * @param {Object} article - 文章对象 { url, title, content, source, ... }
   * @param {Object} options - 可选参数
   * @param {Boolean} options._fromPlayFromList - 内部标记，playFromList 调用时跳过 playlist 同步
   */
  const playArticle = async (article, options = {}) => {
    if (!article) {
      showToast({ message: t('player.invalidArticleData'), icon: 'fail' })
      return
    }

    // 立即清除旧的 interval，防止在切换过程中因状态空闲被误判为播放结束
    clearStatusSyncInterval()

    // 同步播放列表状态（仅在直接调用时，playFromList 已自行处理）
    if (!options._fromPlayFromList) {
      const indexInPlaylist = playlist.value.findIndex(a => a.url === article.url)
      if (indexInPlaylist >= 0) {
        // 文章已在播放列表中，更新当前索引
        currentIndex.value = indexInPlaylist
      } else {
        // 文章不在播放列表中 → 检查听读队列，优先使用队列作为播放列表
        try {
          const { useQueueStore } = await import('./queueStore')
          const queueStore = useQueueStore()
          const queueIndex = queueStore.queue.findIndex(a => a.url === article.url)
          if (queueIndex >= 0 && queueStore.queue.length > 0) {
            playlist.value = [...queueStore.queue]
            currentIndex.value = queueIndex
          } else {
            playlist.value = [article]
            currentIndex.value = 0
          }
        } catch {
          playlist.value = [article]
          currentIndex.value = 0
        }
        savePlaylist()
      }
    }

    // 互斥：停止播客播放器（含 loading 状态）
    try {
      const { usePodcastPlayerStore } = await import('./podcastPlayerStore')
      const podcastPlayer = usePodcastPlayerStore()
      if (podcastPlayer.isPlaying || podcastPlayer.isPaused || podcastPlayer.isLoading) {
        podcastPlayer.stop()
      }
    } catch (e) { /* podcastPlayerStore 未加载时忽略 */ }

    // ✅ 关键修复：在开始新播放前，先停止所有正在运行的 TTS 实例
    // 防止 OpenAI TTS 和 Web Speech API 同时播放
    if (openAITts) {
      try {
        openAITts.stop()
      } catch (e) {
        // 忽略停止错误
      }
    }
    if (legacyTts) {
      try {
        legacyTts.stop()
      } catch (e) {
        // 忽略停止错误
      }
    }

    // 云端 TTS 只硬性依赖 article.id。恢复出的 metadata-only 文章缺 id 时才同步补全；
    // 正文缺失不能阻塞播放，否则弱网下 /api/articles/by-url 超时会直接打断 TTS。
    let fullArticle = await hydrateArticleForTts(article)
    if (!fullArticle.id) {
      const error = new Error('article_id_missing_after_hydration')
      console.error('[PlayerStore] Cannot play article without id:', fullArticle)
      audioLoadError.value = error.message
      showToast({ message: t('player.fetchArticleFailed'), icon: 'fail' })
      return
    }

    if (playlist.value[currentIndex.value]?.url === article.url) {
      playlist.value[currentIndex.value] = {
        ...playlist.value[currentIndex.value],
        ...fullArticle
      }
      savePlaylist()
    }

    // 更新当前文章
    const savedProgress = getSavedProgressForArticle(fullArticle)
    const resumeTime = savedProgress?.currentTime || 0
    const resumeTotal = savedProgress?.totalTime || 0

    currentArticle.value = fullArticle
    currentTime.value = resumeTime
    totalTime.value = resumeTotal || 0

    // ✅ 优先使用新 TTS 架构（两层架构：Cloud Cached -> Cloud Realtime）
    if (newTts) {
      try {
        isLoadingAudio.value = true
        audioLoadError.value = null
        useFallback.value = false

        // 调用新 TTS 播放
        await newTts.loadAudio(fullArticle, {
          rate: playbackRate.value,
          startTime: resumeTime,
          requireHighQuality: false,
          onTierChange: (tier, reason) => {
            currentTier.value = tier
            console.log(`[PlayerStore] TTS Tier changed to ${tier}, reason: ${reason}`)
          }
        })

        // 同步初始状态
        syncNewTtsState()

        // 清理之前的 interval，避免累积
        clearStatusSyncInterval()

        // 持续同步播放状态（每 100ms 检测一次）
        statusSyncIntervalId = setInterval(() => {
          // 持续同步播放状态
          const wasPlaying = isPlaying.value
          const isActiveNow = (
            newTts.isPlaying.value ||
            newTts.isPaused.value ||
            newTts.isLoading.value
          )

          syncNewTtsState()

          if (currentArticle.value && (isPlaying.value || isPaused.value || isLoadingAudio.value)) {
            const now = Date.now()
            if (now - lastProgressSaveAt >= PROGRESS_SAVE_INTERVAL_MS) {
              saveProgress()
              if (isPlaying.value) {
                saveResumeIntent('playing')
              }
              lastProgressSaveAt = now
            }
          }

          // 如果从非播放状态变为播放状态，触发进度保存
          if (!wasPlaying && isPlaying.value) {
            if (isLoadingAudio.value) {
              console.log('[PlayerStore] 检测到播放开始，重置加载状态')
            }
            saveProgress()
            saveResumeIntent('play-start')
            emitFirstAudioPlayed()
            trackArticleFirstPlay(currentArticle.value)
            console.log('[PlayerStore] 播放状态已同步，悬浮窗应该显示')
          }

          // 分段切换和错误恢复时会有极短暂 idle，连续多次 idle 才视为真正结束
          if (isActiveNow) {
            idleSyncTicks = 0
            return
          }

          idleSyncTicks += 1
          if (idleSyncTicks >= 10) {
            isLoadingAudio.value = false

            // 中途停滞（后台切换链冻结/系统暂停落在边界）不再清空会话，
            // 落为"可恢复暂停"态，由 useTTS 的韧性恢复/前台 reconcile 接管；
            // 保留状态同步 interval，恢复后 store 能立即感知
            if (shouldPreserveAsPaused({ currentTime: currentTime.value, totalTime: totalTime.value })) {
              idleSyncTicks = 0 // 防重入：仍停滞时 1s 后重新判定
              isPlaying.value = false
              if (!isPaused.value) {
                isPaused.value = true
                saveResumeIntent('playing')
                console.warn('[PlayerStore] 播放链路中途停滞，标记为可恢复暂停而非清空')
                preloadNextArticle().catch(err => {
                  console.warn('[PlayerStore] Preload failed (non-blocking):', err)
                })
              }
            } else {
              clearStatusSyncInterval()
              clearInactiveCurrentArticle()
              console.log('[PlayerStore] 播放结束，停止状态同步')

              // 异步预加载下一篇（不阻塞）
              preloadNextArticle().catch(err => {
                console.warn('[PlayerStore] Preload failed (non-blocking):', err)
              })
            }
          }
        }, 100)

        console.log('[PlayerStore] Playing with new TTS architecture')
      } catch (error) {
        console.error('[PlayerStore] New TTS failed:', error)
        const isQuotaExceeded = isTtsQuotaExceededError(error)
        audioLoadError.value = isQuotaExceeded
          ? t('player.ttsQuotaExhaustedMessage')
          : error.message
        syncNewTtsState()
        isLoadingAudio.value = false

        const isNotAllowed = error?.name === 'NotAllowedError'
        if (isQuotaExceeded && currentArticle.value) {
          // Keep the selected article visible so a quota denial does not look like
          // the player crashed or silently exited.
          isPlaying.value = false
          isPaused.value = true
          currentTier.value = null
          saveProgress()
        } else if (isNotAllowed && currentArticle.value) {
          isPaused.value = true
          audioLoadError.value = null
          saveProgress()
        } else {
          clearInactiveCurrentArticle()
        }

        if (isQuotaExceeded) {
          // 自托管版无用户付费配额；云端服务异常时直接降级本地语音
          requestLegacyFallback(fullArticle, resumeTime)
        } else {
          if (!isNotAllowed) {
            trackAudioError({
              article_id: currentArticle.value?.id || currentArticle.value?.url,
              error_code: error?.code || error?.response?.status,
              error_message: error?.message || 'article_tts_failed',
            })
            showToast({ message: error.message || t('player.playFailedRetry'), icon: 'fail' })
          }
        }
      }
    } else if (openAITts && !useFallback.value) {
      // 使用旧版 OpenAI TTS
      await playWithOpenAITTS(fullArticle, resumeTime)
    } else {
      // TTS 实例不可用
      showToast({ message: t('player.ttsNotInitialized'), icon: 'fail' })
    }

  }

  /**
   * 使用旧版 OpenAI TTS 播放（内部方法）
   */
  const playWithOpenAITTS = async (article, startTime) => {
    try {
      isLoadingAudio.value = true
      audioLoadError.value = null

      let canResumeFromCache = false
      if (startTime > 0 && article.id) {
        canResumeFromCache = await waitForCacheIfNeeded(article.id)
        if (!canResumeFromCache) {
          showToast({
            message: t('player.audioGeneratingPlayFromStart'),
            type: 'warning',
            duration: 2500
          })
        }
      }

      const resumeTime = canResumeFromCache ? startTime : 0

      await openAITts.loadAudio(article, {
        rate: playbackRate.value,
        startTime: resumeTime
      })
      console.log(`[PlayerStore] 开始播放，播放速率: ${playbackRate.value}x，起始位置: ${resumeTime}s`)

      // 清理之前的 interval，避免累积
      clearStatusSyncInterval()

      // 持续同步播放状态
      statusSyncIntervalId = setInterval(() => {
        if (openAITts.isPlaying.value && isLoadingAudio.value) {
          isLoadingAudio.value = false
        }

        const wasPlaying = isPlaying.value
        isPlaying.value = openAITts.isPlaying.value
        isPaused.value = openAITts.isPaused.value

        if (!wasPlaying && isPlaying.value) {
          saveProgress()
          emitFirstAudioPlayed()
          trackArticleFirstPlay(currentArticle.value)
        }

        if (!openAITts.isPlaying.value && !openAITts.isPaused.value && !openAITts.isLoading.value) {
          clearStatusSyncInterval()
          isLoadingAudio.value = false

          // 区分运行时错误与正常结束：loadAudio() 已 resolve 后若再被 audio.error 置脏，
          // 则视为播放途中失败，不应预热下一篇、不应触发 audio_completed，必须显式收口。
          const runtimeError = openAITts.loadError?.value
          if (runtimeError) {
            audioLoadError.value = runtimeError
            trackAudioError({
              article_id: currentArticle.value?.id || currentArticle.value?.url,
              error_code: 'openai_tts_runtime_error',
              error_message: runtimeError,
            })
            showToast({ message: runtimeError || t('player.playFailedRetry'), icon: 'fail' })
            clearInactiveCurrentArticle()
            return
          }

          preloadNextArticle().catch(err => {
            console.warn('[PlayerStore] Preload failed:', err)
          })
        }
      }, 100)

      console.log('[PlayerStore] Playing with OpenAI TTS')
    } catch (error) {
      console.error('[PlayerStore] OpenAI TTS failed:', error)
      audioLoadError.value = error.message
      isLoadingAudio.value = false

      if (error.name === 'AbortError') {
        console.log('[PlayerStore] 播放被取消，跳过 fallback')
        return
      }

      trackAudioError({
        article_id: currentArticle.value?.id || currentArticle.value?.url,
        error_code: error?.code || error?.response?.status,
        error_message: error?.message || 'openai_tts_failed',
      })
      showToast({ message: error.message || t('player.playFailedRetry'), icon: 'fail' })
    }
  }

  /**
   * 使用 Web Speech API 播放（降级，内部方法）
   */
  const playWithLegacyTTS = async (article, startTime) => {
    if (!legacyTts) {
      showToast({ message: t('player.ttsNotInitialized'), icon: 'fail' })
      return
    }

    useFallback.value = true
    isActivatingFallback.value = true
    audioLoadError.value = null
    isLoadingAudio.value = false
    isPlaying.value = false
    isPaused.value = false
    // 重置上一次的合成错误标记，避免污染本次播放循环
    legacyPlaybackErrored = false

    // 先设置播放速率，再开始朗读
    if (playbackRate.value !== 1.0 && legacyTts.setRate) {
      legacyTts.setRate(playbackRate.value)
    }

    // 不阻塞 speak() 加载 voices，避免 Android 用户手势同步链断裂
    if (legacyTts.loadVoices) {
      legacyTts.loadVoices().catch(() => {})
    }

    legacyTts.speak(article.content || article.summary || article.title)

    // 清理之前的 interval，避免累积
    clearStatusSyncInterval()

    // 持续同步 Web Speech API 播放状态
    // 使用 idleSyncTicks 容错，避免 Android 上 onstart 延迟导致的过早清理
    idleSyncTicks = 0
    statusSyncIntervalId = setInterval(() => {
      isPlaying.value = legacyTts.isPlaying.value
      isPaused.value = legacyTts.isPaused.value

      if (legacyTts.currentTime.value !== undefined) {
        currentTime.value = legacyTts.currentTime.value
      }
      if (legacyTts.totalTime.value !== undefined) {
        totalTime.value = legacyTts.totalTime.value
      }

      const isActiveNow = legacyTts.isPlaying.value || legacyTts.isPaused.value
      if (isActiveNow) {
        isActivatingFallback.value = false
        if (legacyTts.isPlaying.value) {
          emitFirstAudioPlayed()
          trackArticleFirstPlay(currentArticle.value)
        }
        idleSyncTicks = 0
        return
      }

      // 播放结束（既不播放也不暂停）连续多次 idle 才视为真正结束
      idleSyncTicks += 1
      if (idleSyncTicks >= 10) {
        isActivatingFallback.value = false
        clearStatusSyncInterval()
        // 区分合成错误与自然结束：错误时不能走 preloadNextArticle，否则相当于"播放失败被当成播放完成"
        // 注意：user-visible 的错误提示由 useSpeechSynthesis 的 onerror 直接 toast，
        // 这里只做静默的状态清理 + 跳过 preload，避免双重 toast。
        if (legacyPlaybackErrored) {
          legacyPlaybackErrored = false
          clearInactiveCurrentArticle()
          return
        }
        preloadNextArticle().catch(err => console.warn('[PlayerStore] Preload failed:', err))
      }
    }, 100)

    // 如果有起始时间且支持跳转，尝试 seek
    if (startTime > 0 && legacyTts.totalTime.value > 0 && legacyTts.seekTo) {
      legacyTts.seekTo(startTime, legacyTts.totalTime.value)
    }

    saveProgress()
    console.log('[PlayerStore] Playing with Web Speech API')
  }

  /**
   * 从列表开始播放
   * @param {Array} articles - 文章数组
   * @param {Number} startIndex - 起始索引
   */
  const playFromList = async (articles, startIndex = 0) => {
    if (!articles || articles.length === 0) {
      showToast({ message: t('player.playlistEmpty'), icon: 'fail' })
      return
    }

    if (startIndex < 0 || startIndex >= articles.length) {
      showToast({ message: t('player.invalidStartPosition'), icon: 'fail' })
      return
    }

    // 设置播放列表
    playlist.value = articles
    currentIndex.value = startIndex

    // 播放第一篇（跳过 playlist 同步，因为已在上面设置好）
    await playArticle(articles[startIndex], { _fromPlayFromList: true })

    // 保存播放列表到 localStorage
    savePlaylist()
  }

  /**
   * 切换播放/暂停
   */
  const togglePlayPause = () => {
    const tts = getCurrentTTS()
    if (!tts) return

    // 关键修复：优先检查 isPaused 状态，而不是 isPlaying
    // 因为暂停时 isPlaying = false，导致无法恢复播放
    if (isPaused.value) {
      // 恢复播放
      if (useFallback.value && legacyTts) {
        legacyTts.resume()
      } else if (newTts) {
        // App 重启后 TTS 实例可能没有加载当前文章，回退到重新加载
        if (!newTts.currentArticle?.value || newTts.currentArticle.value?.url !== currentArticle.value?.url) {
          playArticle(currentArticle.value)
          return
        }
        // 中断/断流后的元素可能已损坏，优先走韧性恢复（重载+断点续播）
        if (newTts.resumePlayback) {
          newTts.resumePlayback('store_toggle')
        } else {
          newTts.play()
        }
      } else if (openAITts) {
        // App 重启后 TTS 实例可能没有加载当前文章，回退到重新加载
        if (!openAITts.currentArticle?.value || openAITts.currentArticle.value?.url !== currentArticle.value?.url) {
          playArticle(currentArticle.value)
          return
        }
        openAITts.play()
      }
      isPaused.value = false
      saveResumeIntent('manual-resume')
      showToast({ message: t('player.resumed'), icon: 'volume-o', duration: 1000 })
    } else if (isPlaying.value) {
      clearResumeIntent()
      // 暂停播放
      if (useFallback.value && legacyTts) {
        legacyTts.pause()
      } else if (newTts) {
        newTts.pause()
      } else if (openAITts) {
        openAITts.pause()
      }
      isPaused.value = true
      showToast({ message: t('player.paused'), icon: 'pause', duration: 1000 })
    } else {
      // 容错：存在当前文章但状态未同步时，尝试重新接管播放
      if (currentArticle.value) {
        console.warn('[PlayerStore] 播放状态丢失，尝试重新恢复当前文章')
        playArticle(currentArticle.value)
        return
      }

      // 当前没有播放，无法切换
      console.warn('[PlayerStore] 无法切换播放/暂停：当前没有播放')
      return
    }

    saveProgress()
  }

  /**
   * 停止播放
   */
  const stop = () => {
    cancelLegacyFallbackRequest()
    clearResumeIntent()
    if (useFallback.value && legacyTts) {
      legacyTts.stop()
    } else if (newTts) {
      newTts.stop()
    } else if (openAITts) {
      openAITts.stop()
    }

    isPlaying.value = false
    isPaused.value = false
    currentTime.value = 0
    totalTime.value = 0
    currentArticle.value = null
    currentTier.value = null
    isActivatingFallback.value = false
    useFallback.value = false

    // 清除播放进度
    localStorage.removeItem('tts_progress')

    // 清理状态同步 interval
    clearStatusSyncInterval()
  }

  /**
   * 跳转到指定时间
   * @param {Number} time - 目标时间 (秒)
   */
  const seekTo = (time) => {
    if (!currentArticle.value) return

    const liveCurrentTime = newTts?.currentTime?.value ?? currentTime.value
    const liveTotalTime = newTts?.totalTime?.value ?? totalTime.value
    const targetTime = Math.max(0, Math.min(time, liveTotalTime || time))
    currentTime.value = targetTime

    // 调用 TTS 跳转
    if (useFallback.value && legacyTts && legacyTts.seekTo) {
      legacyTts.seekTo(targetTime, totalTime.value)
    } else if (newTts) {
      newTts.seekTo(targetTime)
    } else if (openAITts && openAITts.seekTo) {
      openAITts.seekTo(targetTime)
    }

    saveProgress()
  }

  /**
   * 快进
   * @param {Number} seconds - 快进秒数 (默认 15 秒)
   */
  const skipForward = (seconds = 15) => {
    const baseTime = newTts?.currentTime?.value ?? currentTime.value
    seekTo(baseTime + seconds)
    showToast({ message: t('player.skipForwardNSeconds', { n: seconds }), icon: 'success', duration: 1000 })
  }

  /**
   * 快退
   * @param {Number} seconds - 快退秒数 (默认 15 秒)
   */
  const skipBackward = (seconds = 15) => {
    const baseTime = newTts?.currentTime?.value ?? currentTime.value
    seekTo(baseTime - seconds)
    showToast({ message: t('player.skipBackwardNSeconds', { n: seconds }), icon: 'success', duration: 1000 })
  }

  /**
   * 播放下一篇
   */
  const playNext = async () => {
    if (playlist.value.length === 0) {
      showToast({ message: t('player.playlistEmpty'), icon: 'info' })
      return
    }

    if (currentIndex.value < playlist.value.length - 1) {
      currentIndex.value++
      await playArticle(playlist.value[currentIndex.value], { _fromPlayFromList: true })
      showToast({ message: t('player.nextArticle'), icon: 'success', duration: 1000 })
    } else {
      showToast({ message: t('player.lastArticle'), icon: 'info' })
      stop()
    }
  }

  /**
   * 播放上一篇
   */
  const playPrevious = async () => {
    if (playlist.value.length === 0) {
      showToast({ message: t('player.playlistEmpty'), icon: 'info' })
      return
    }

    if (currentIndex.value > 0) {
      currentIndex.value--
      await playArticle(playlist.value[currentIndex.value], { _fromPlayFromList: true })
      showToast({ message: t('player.previousArticle'), icon: 'success', duration: 1000 })
    } else {
      showToast({ message: t('player.firstArticle'), icon: 'info' })
    }
  }

  /**
   * 跳转到播放列表指定位置
   * @param {Number} index - 目标索引
   */
  const playAtIndex = async (index) => {
    if (index < 0 || index >= playlist.value.length) {
      showToast({ message: t('player.invalidPosition'), icon: 'fail' })
      return
    }

    currentIndex.value = index
    await playArticle(playlist.value[index], { _fromPlayFromList: true })
  }

  /**
   * 设置播放速度
   * @param {Number} rate - 播放速度 (0.5 - 2.0)
   */
  const setPlaybackRate = (rate) => {
    const newRate = Math.max(0.5, Math.min(2.0, rate))
    playbackRate.value = newRate

    if (useFallback.value && legacyTts && legacyTts.setRate) {
      legacyTts.setRate(newRate)
    } else if (newTts) {
      newTts.setRate(newRate)
    } else if (openAITts && openAITts.setRate) {
      openAITts.setRate(newRate)
    }

    saveSettings()
    showToast({ message: t('player.speedNX', { n: newRate }), icon: 'success', duration: 1000 })
  }

  /**
   * 更新播放进度 (由 TTS composable 定期调用)
   * @param {Number} current - 当前时间
   * @param {Number} total - 总时长
   */
  const updateProgress = (current, total) => {
    currentTime.value = current
    totalTime.value = total
  }

  /**
   * 播放结束回调 (由 TTS composable 调用)
   */
  const onPlaybackEnd = async () => {
    isActivatingFallback.value = false
    clearResumeIntent()
    // 清除旧 interval，避免切换过程中被误判为播放结束而清空 currentArticle
    clearStatusSyncInterval()
    // 记录当前文章完成播放（无论是否连播下一篇）
    const completedArticle = currentArticle.value
    trackAudioCompleted({ article_id: completedArticle?.id || completedArticle?.url })
    // 自动播放下一篇
    if (playlist.value.length > 0 && currentIndex.value < playlist.value.length - 1) {
      await playNext()
    } else {
      showToast({ message: t('player.playbackComplete'), icon: 'success' })
      stop()
    }
  }

  /**
   * 快速交接簿记（Fix 1，iOS 后台连播）
   * useTTS 在 ended 事件内已同步完成换 src + play() 后调用本方法做异步收尾：
   * 上报上一篇完成、前进 index、保存状态、触发 N+2 服务端预热。
   * 注意：不调用 loadAudio/playArticle，音频交接已在 ended 回合约内完成。
   */
  const onNextTrackHandoff = (article) => {
    if (!article) return

    const finishedArticle = currentArticle.value
    if (finishedArticle && finishedArticle.url !== article.url) {
      trackAudioCompleted({ article_id: finishedArticle.id || finishedArticle.url })
    }

    if (currentIndex.value < playlist.value.length - 1) {
      currentIndex.value += 1
    }

    currentArticle.value = article
    currentTime.value = 0
    audioLoadError.value = null

    trackArticleFirstPlay(article)
    saveResumeIntent('playing')
    saveProgress()
    savePlaylist()

    // N+2 服务端生成预热（原 preloadNextArticle 的常规职责）
    preloadNextArticle().catch(err => {
      console.warn('[PlayerStore] Preload after handoff failed (non-blocking):', err)
    })

    console.log(`[PlayerStore] Fast handoff bookkeeping done: ${article.title || article.id || article.url}`)
  }

  /**
   * 预加载下一篇文章音频
   * 播放成功后自动触发，减少下一篇等待时间
   */
  const preloadNextArticle = async () => {
    // 检查是否有下一篇
    if (!playlist.value || playlist.value.length === 0) {
      console.log('[Player] No playlist for preload')
      return
    }

    const nextIndex = currentIndex.value + 1
    if (nextIndex >= playlist.value.length) {
      console.log('[Player] No next article to preload')
      return
    }

    let nextArticle = playlist.value[nextIndex]
    if (!nextArticle) {
      console.log('[Player] Next article has no content')
      return
    }

    nextArticle = await hydrateArticleForTts(nextArticle)
    playlist.value[nextIndex] = {
      ...playlist.value[nextIndex],
      ...nextArticle
    }
    savePlaylist()

    if (!nextArticle.id) {
      console.log('[Player] Next article missing playable fields after hydration')
      return
    }

    try {
      console.log(`[Player] Preloading next article: ${nextArticle.title}`)

      // Phase 2/3: 使用 ttsManager 统一预加载入口
      // 使用 ttsManager 触发云端预加载
      const result = await ttsManager.preloadArticle(nextArticle.id, nextArticle)

      console.log(`[Player] Preload complete for article ${nextArticle.id}:`, result)
    } catch (error) {
      console.error('[Player] Preload failed:', error)
      // 预加载失败不影响当前播放，静默处理
    }
  }

  const onLegacyPlaybackStart = () => {
    isActivatingFallback.value = false
    isLoadingAudio.value = false
    isPlaying.value = true
    isPaused.value = false
    // 新会话真正开始：清理上一次的错误标记（覆盖 useSpeechSynthesis 内部 retry 等场景）
    legacyPlaybackErrored = false
  }

  const onLegacyPlaybackError = (errorReason) => {
    isActivatingFallback.value = false
    // 标记本次会话已发生合成错误，让 playWithLegacyTTS 轮询的 idle 分支识别为错误结束而非自然结束
    legacyPlaybackErrored = true
    // 上报 Web Speech fallback 的播放失败，使其与 segmented/cloud/openAI 路径在 audio_error 指标里口径一致
    trackAudioError({
      article_id: currentArticle.value?.id || currentArticle.value?.url,
      error_code: errorReason || 'legacy_tts_failed',
      error_message: errorReason ? `legacy_tts_${errorReason}` : 'legacy_tts_failed',
    })
  }

  /**
   * 保存播放进度到 localStorage
   */
  const saveProgress = () => {
    if (!currentArticle.value) return

    const progressData = {
      url: currentArticle.value.url,
      currentTime: currentTime.value,
      totalTime: totalTime.value,
      timestamp: Date.now()
    }

    localStorage.setItem('tts_progress', JSON.stringify(progressData))
    localStorage.setItem('tts_last_article', currentArticle.value.url)
    lastProgressSaveAt = Date.now()
    syncPlaybackState()
  }

  /**
   * 保存播放列表到 localStorage
   */
  const savePlaylist = () => {
    if (playlist.value.length === 0) return

    const playlistMeta = serializePlaylist(playlist.value)

    localStorage.setItem('tts_playlist', JSON.stringify(playlistMeta))
    localStorage.setItem('tts_current_index', currentIndex.value.toString())
    syncPlaybackState()
  }

  /**
   * 保存播放设置到 localStorage
   */
  const saveSettings = () => {
    const settings = {
      playbackRate: playbackRate.value,
      volume: volume.value
    }

    localStorage.setItem('tts_settings', JSON.stringify(settings))
  }

  /**
   * 恢复播放进度 (应用启动时调用)
   */
  const restoreProgress = async () => {
    try {
      // 恢复播放设置
      const settingsStr = localStorage.getItem('tts_settings')
      if (settingsStr) {
        const settings = JSON.parse(settingsStr)
        playbackRate.value = settings.playbackRate || 1.0
        volume.value = settings.volume || 1.0
      }

      // 恢复播放列表
      const playlistStr = localStorage.getItem('tts_playlist')
      if (playlistStr) {
        playlist.value = JSON.parse(playlistStr)
      }

      const indexStr = localStorage.getItem('tts_current_index')
      if (indexStr) {
        currentIndex.value = parseInt(indexStr, 10)
      }

      if (playlist.value.length > 0) {
        const safeIndex = Math.min(Math.max(currentIndex.value || 0, 0), playlist.value.length - 1)
        currentIndex.value = safeIndex
        currentArticle.value = playlist.value[safeIndex]
      }

      // 恢复播放进度
      let localProgressTimestamp = 0
      const progressStr = localStorage.getItem('tts_progress')
      if (progressStr) {
        const progressData = JSON.parse(progressStr)

        // 检查是否过期 (超过 24 小时)
        const elapsed = Date.now() - progressData.timestamp
        if (elapsed < 24 * 60 * 60 * 1000) {
          currentTime.value = progressData.currentTime || 0
          totalTime.value = progressData.totalTime || 0
          localProgressTimestamp = progressData.timestamp || 0
        }
      }

      // App 重启后，如果 currentArticle 存在但没有活跃的播放状态，标记为暂停
      // 避免进入 isPlaying=false && isPaused=false 的僵尸状态
      if (currentArticle.value && !isPlaying.value && !isPaused.value) {
        isPaused.value = true
      }

      // 从服务端拉取更新的播放状态（如果服务端更新则覆盖本地）
      if (canSyncPlaybackState()) {
        try {
          const server = await getPlaybackState()
          const serverTime = server?.updated_at ? Date.parse(server.updated_at) : 0
          if (serverTime > localProgressTimestamp && server.playlist?.length > 0) {
            playlist.value = server.playlist
            currentIndex.value = Math.min(
              Math.max(server.current_index || 0, 0),
              playlist.value.length - 1
            )
            currentArticle.value = server.current_article || playlist.value[currentIndex.value] || null
            currentTime.value = server.current_time || 0
            totalTime.value = server.total_time || 0
            playbackRate.value = server.playback_rate || 1.0

            // 写回本地，避免刚恢复就立即上传
            localStorage.setItem('tts_playlist', JSON.stringify(serializePlaylist(playlist.value)))
            localStorage.setItem('tts_current_index', currentIndex.value.toString())
            if (currentArticle.value) {
              localStorage.setItem('tts_progress', JSON.stringify({
                url: currentArticle.value.url,
                currentTime: currentTime.value,
                totalTime: totalTime.value,
                timestamp: serverTime
              }))
              localStorage.setItem('tts_last_article', currentArticle.value.url)
            }
            lastPlaybackSyncAt = Date.now()
          }
        } catch (error) {
          console.warn('[PlayerStore] Failed to restore playback state from server:', error)
        }
      }
    } catch (error) {
      console.error('恢复播放进度失败:', error)
    }
  }

  const resumeInterruptedPlayback = async () => {
    const intent = getResumeIntent()
    if (!intent || resumeAttemptInFlight || isPlaying.value || isLoadingAudio.value) {
      return false
    }

    let article = currentArticle.value
    if (!article && playlist.value.length > 0) {
      const safeIndex = Math.min(Math.max(intent.index || currentIndex.value || 0, 0), playlist.value.length - 1)
      currentIndex.value = safeIndex
      article = playlist.value[safeIndex]
      currentArticle.value = article
    }

    if (!article || article.url !== intent.url) {
      return false
    }

    if (typeof navigator !== 'undefined' && !navigator.onLine) {
      return false
    }

    resumeAttemptInFlight = true
    try {
      currentTime.value = intent.currentTime || currentTime.value || 0
      totalTime.value = intent.totalTime || totalTime.value || 0
      console.log('[PlayerStore] Resuming interrupted TTS playback after app restart')
      await playArticle(article, { _fromPlayFromList: true })
      if (!isPlaying.value) {
        console.log('[PlayerStore] Interrupted playback resume did not start automatically')
        return false
      }
      return true
    } catch (error) {
      console.warn('[PlayerStore] Failed to resume interrupted playback:', error)
      return false
    } finally {
      resumeAttemptInFlight = false
    }
  }

  /**
   * 清除所有播放数据
   */
  const clearAllData = () => {
    stop()
    playlist.value = []
    currentIndex.value = 0
    reportedArticles.clear()

    localStorage.removeItem('tts_progress')
    localStorage.removeItem('tts_last_article')
    localStorage.removeItem('tts_playlist')
    localStorage.removeItem('tts_current_index')
    clearResumeIntent()
  }

  return {
    // 状态
    isPlaying,
    isPaused,
    isLoadingAudio, // 新增：音频加载状态
    audioLoadError, // 新增：音频加载错误
    useFallback, // 新增：降级标志
    isActivatingFallback,
    currentArticle,
    pendingFallbackRequest,
    playlist,
    currentIndex,
    currentTime,
    totalTime,
    progress,
    playbackRate,
    volume,
    currentTier, // 新增：当前 TTS 层级
    tierStatus, // 新增：TTS 层级状态

    // 方法
    setOpenAITTSInstance, // 新增：设置 OpenAI TTS 实例
    setLegacyTTSInstance, // 新增：设置 Legacy TTS 实例
    setNewTTSInstance, // 新增：设置新 TTS 实例（三层架构）
    initializeTTSManager, // 新增：初始化 TTS Manager
    setTTSInstance, // 兼容旧代码
    getCurrentTTS, // 新增：获取当前 TTS 实例
    playArticle,
    playFromList,
    togglePlayPause,
    stop,
    seekTo,
    skipForward,
    skipBackward,
    playNext,
    playPrevious,
    playAtIndex,
    setPlaybackRate,
    updateProgress,
    onPlaybackEnd,
    onNextTrackHandoff, // 快速交接簿记（Fix 1）
    onLegacyPlaybackStart,
    onLegacyPlaybackError,
    preloadNextArticle, // 新增：预加载下一篇
    requestLegacyFallback,
    confirmLegacyFallback,
    cancelLegacyFallbackRequest,
    saveProgress,
    savePlaylist,
    saveSettings,
    restoreProgress,
    resumeInterruptedPlayback,
    clearAllData
  }
})
