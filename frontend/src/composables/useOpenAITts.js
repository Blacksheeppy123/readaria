import { ref, onUnmounted, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { showToast } from 'vant'
import { getTtsPlayUrl } from '@/api/tts'

/**
 * OpenAI TTS Composable - 简化版
 *
 * 使用 HTML5 Audio API + 后端统一播放接口
 * 架构：后端流式透传 + 服务器缓存
 * 删除：IndexedDB、分段播放、MediaSource API
 *
 * v2.0 (2025-12-25) - MP3 统一格式迁移
 */

// ==================== 日志收集工具 ====================

/**
 * 将关键日志存储到 localStorage，供后续诊断
 * @param {string} message - 日志消息
 * @param {Object} data - 附加数据
 * @param {Object} options - 可选配置 { type, key, params }
 */
const logToStorage = (message, data = {}, options = {}) => {
  try {
    const LOG_KEY = 'tts_debug_logs'
    const MAX_LOGS = 100  // 最多保留100条日志

    // 读取现有日志
    const logsStr = localStorage.getItem(LOG_KEY)
    let logs = []
    if (logsStr) {
      try {
        logs = JSON.parse(logsStr)
      } catch (e) {
        logs = []
      }
    }

    // 添加新日志
    logs.push({
      timestamp: new Date().toISOString(),
      message,
      key: options.key || null,
      params: options.params || null,
      type: options.type || 'log',
      data,
      userAgent: navigator.userAgent
    })

    // 保持最多100条日志
    if (logs.length > MAX_LOGS) {
      logs = logs.slice(-MAX_LOGS)
    }

    // 保存到localStorage
    localStorage.setItem(LOG_KEY, JSON.stringify(logs))
  } catch (error) {
    // 静默失败，不影响播放
    console.warn('[TTS] logToStorage failed:', error)
  }
}

/**
 * 清除诊断日志
 */
export const clearDebugLogs = () => {
  try {
    localStorage.removeItem('tts_debug_logs')
    console.log('[TTS] 诊断日志已清除')
  } catch (error) {
    console.error('[TTS] 清除日志失败:', error)
  }
}

/**
 * 导出诊断日志为JSON字符串
 * @returns {string} JSON格式的日志
 */
export const exportDebugLogs = () => {
  try {
    const logsStr = localStorage.getItem('tts_debug_logs')
    if (!logsStr) return '[]'

    // 格式化输出
    const logs = JSON.parse(logsStr)
    return JSON.stringify(logs, null, 2)
  } catch (error) {
    console.error('[TTS] 导出日志失败:', error)
    return '[]'
  }
}

// 全局共用的 Audio 实例引用，确保播放器单例
const audio = ref(null)

export function useOpenAITts(playerStore = null) {
  const { t } = useI18n()

  // ==================== 状态管理 ====================

  // 播放状态
  const isPlaying = ref(false)
  const isPaused = ref(false)
  const isLoading = ref(false)
  const loadError = ref(null)

  // 当前文章信息
  const currentArticle = ref(null)

  // 播放进度
  const currentTime = ref(0) // 当前播放时间 (秒)
  const totalTime = ref(0) // 总时长 (秒)
  const progress = computed(() => {
    return totalTime.value > 0 ? (currentTime.value / totalTime.value) * 100 : 0
  })

  // 播放速度
  const rate = ref(1.0) // 0.75, 1.0, 1.25, 1.5, 2.0
  let manualPause = false // 标记用户主动暂停/停止，避免自动重连误判
  let autoResumeAttempted = false // 单次自动恢复保护
  let reloadingAfterPause = false // 防止 pause 中的 reload 循环

  // ==================== Media Session API (iOS 后台播放支持) ====================

  // ✅ 用于检测音频是否真正在播放（避免 iOS 锁屏后状态不一致）
  let activeStreamArticleId = null
  // ✅ 每次 loadAudio 重置：避免 canplay 在同一来源上多次触发倍速降级提示
  // 单例 Audio 复用时，若使用 { once: true } 则只对第一篇文章生效，第二篇起会丢失流式降级保护
  let streamingRateHandledForSrc = false

  /**
   * 配置 Media Session API（支持 iOS 后台播放）
   * @param {Object} article - 文章对象 { title, source }
   */
  const setupMediaSession = (article) => {
    if (!('mediaSession' in navigator)) {
      console.warn('[TTS] Media Session API not supported')
      return
    }

    try {
      // 设置元数据（显示在锁屏界面）
      navigator.mediaSession.metadata = new MediaMetadata({
        title: article.title || t('tts.nowPlaying'),
        artist: article.author?.trim() || 'Readaria',
        album: 'Readaria RSS Reader',
        artwork: [
          { src: '/apple-touch-icon.png', sizes: '180x180', type: 'image/png' }
        ]
      })

      // 注册播放控制（锁屏界面按钮）
      navigator.mediaSession.setActionHandler('play', async () => {
        try {
          if (!audio.value) {
            console.warn('[TTS] 无音频实例')
            logToStorage('[TTS] 无音频实例', {}, { type: 'warning', key: 'debug.noAudioInstance' })
            return
          }

          if (!audio.value.paused) {
            console.log('[TTS] 音频正在正常播放，跳过操作')
            return
          }

          logToStorage('[TTS] Media Session play 事件触发', {
            isPaused: isPaused.value,
            readyState: audio.value.readyState,
            paused: audio.value.paused
          }, { type: 'media', key: 'debug.mediaSessionPlayTriggered' })

          // 确保音频已就绪
          if (audio.value.readyState < 2) {
            const canplayPromise = new Promise((resolve, reject) => {
              const timeout = setTimeout(() => {
                audio.value.removeEventListener('canplay', onCanPlay)
                reject(new Error('等待 canplay 超时'))
              }, 5000)

              const onCanPlay = () => {
                clearTimeout(timeout)
                audio.value.removeEventListener('canplay', onCanPlay)
                resolve()
              }

              audio.value.addEventListener('canplay', onCanPlay, { once: true })
            })

            try {
              await canplayPromise
              logToStorage('[TTS] canplay 事件触发，音频已就绪', {}, { type: 'success', key: 'debug.canplayReady' })
            } catch (err) {
              console.error('[TTS] 等待 canplay 失败:', err)
              logToStorage('[TTS] 等待 canplay 超时', { error: err.message }, { type: 'error', key: 'debug.canplayTimeout' })
              return
            }
          }

          // ✅ 添加错误处理，防止 play() 失败导致状态不一致
          try {
            await audio.value.play()
            isPaused.value = false
            isPlaying.value = true

            try {
              navigator.mediaSession.playbackState = 'playing'
            } catch (e) {
              console.warn('[TTS] Failed to set playbackState:', e)
            }

            logToStorage('[TTS] 播放成功', {
              currentTime: audio.value.currentTime,
              paused: audio.value.paused
            }, { type: 'success', key: 'debug.playSuccess' })
          } catch (playError) {
            console.error('[TTS] 播放失败:', playError)
            logToStorage('[TTS] 播放失败', {
              error: playError.message,
              name: playError.name,
              readyState: audio.value.readyState
            }, { type: 'error', key: 'debug.playError' })

            // NotAllowedError: 用户需要手动交互，静默失败
            if (playError.name === 'NotAllowedError') {
              console.log('[TTS] NotAllowedError - 需要用户手动交互')
            }
          }
        } catch (error) {
          console.error('[TTS] Media Session play handler failed:', error)
          logToStorage('[TTS] Media Session play handler 失败', {
            error: error.message,
            stack: error.stack
          }, { type: 'error', key: 'debug.mediaSessionHandlerFailed' })
        }
      })

      navigator.mediaSession.setActionHandler('pause', () => {
        try {
          console.log('[TTS] Media Session: 暂停')

          // 立即设置 playbackState（同步）
          try {
            navigator.mediaSession.playbackState = 'paused'
          } catch (e) {
            console.warn('[TTS] Failed to set playbackState:', e)
          }

          pause()
        } catch (error) {
          console.error('[TTS] Media Session pause handler failed:', error)
          logToStorage('[TTS] Media Session pause handler 失败', { error: error.message }, { type: 'error', key: 'debug.mediaSessionPauseHandlerFailed' })
        }
      })

      navigator.mediaSession.setActionHandler('seekbackward', (details) => {
        try {
          const skipTime = details.seekOffset || 15
          backward(skipTime)
        } catch (error) {
          console.error('[TTS] Media Session seekbackward handler failed:', error)
          logToStorage('[TTS] Media Session seekbackward handler 失败', { error: error.message }, { type: 'error', key: 'debug.mediaSessionSeekBackwardHandlerFailed' })
        }
      })

      navigator.mediaSession.setActionHandler('seekforward', (details) => {
        try {
          const skipTime = details.seekOffset || 15
          forward(skipTime)
        } catch (error) {
          console.error('[TTS] Media Session seekforward handler failed:', error)
          logToStorage('[TTS] Media Session seekforward handler 失败', { error: error.message }, { type: 'error', key: 'debug.mediaSessionSeekForwardHandlerFailed' })
        }
      })

      // 上一篇/下一篇支持
      navigator.mediaSession.setActionHandler('previoustrack', () => {
        try {
          if (playerStore && typeof playerStore.playPrevious === 'function') {
            playerStore.playPrevious()
          }
        } catch (error) {
          console.error('[TTS] Media Session previoustrack handler failed:', error)
          logToStorage('[TTS] Media Session previoustrack handler 失败', { error: error.message }, { type: 'error', key: 'debug.mediaSessionPreviousTrackHandlerFailed' })
        }
      })

      navigator.mediaSession.setActionHandler('nexttrack', () => {
        try {
          if (playerStore && typeof playerStore.playNext === 'function') {
            playerStore.playNext()
          }
        } catch (error) {
          console.error('[TTS] Media Session nexttrack handler failed:', error)
          logToStorage('[TTS] Media Session nexttrack handler 失败', { error: error.message }, { type: 'error', key: 'debug.mediaSessionNextTrackHandlerFailed' })
        }
      })

      console.log('[TTS] Media Session 已配置:', article.title)
    } catch (error) {
      console.error('[TTS] Failed to setup Media Session:', error)
    }
  }

  const getBufferedInfo = () => {
    if (!audio.value) return { bufferedRemaining: 0, hasBuffer: false }
    const buffered = audio.value.buffered
    const now = audio.value.currentTime
    for (let i = 0; i < buffered.length; i++) {
      const start = buffered.start(i)
      const end = buffered.end(i)
      if (now >= start && now <= end) {
        return { bufferedRemaining: end - now, hasBuffer: true }
      }
    }
    return { bufferedRemaining: 0, hasBuffer: false }
  }

  /**
   * 更新 Media Session 播放位置状态
   * 告诉 iOS 系统当前播放进度（支持进度条显示）
   */
  const updateMediaSessionPositionState = () => {
    if (!('mediaSession' in navigator) || !audio.value) {
      return
    }

    try {
      const duration = totalTime.value || 0
      const position = currentTime.value || 0
      const playbackRate = audio.value.playbackRate || 1.0

      // 防御性检查
      if (isNaN(duration) || duration < 0 || !isFinite(duration)) {
        //console.warn(`[TTS] 跳过 Media Session 更新：无效的 duration=${duration}`)
        return
      }

      if (isNaN(position) || position < 0 || position > duration) {
        console.warn(`[TTS] 跳过 Media Session 更新：无效的 position=${position}, duration=${duration}`)
        return
      }

      navigator.mediaSession.setPositionState({
        duration,
        playbackRate,
        position
      })
    } catch (error) {
      // iOS 13.4 以下版本可能不支持 setPositionState
      console.error('[TTS] setPositionState failed:', error)
    }
  }

  /**
   * 清理 Media Session 状态
   * 播放结束或停止时调用
   */
  const clearMediaSession = () => {
    if (!('mediaSession' in navigator)) {
      return
    }

    try {
      // 清空元数据
      navigator.mediaSession.metadata = null

      // 移除所有 Action Handlers
      const actions = ['play', 'pause', 'seekbackward', 'seekforward', 'nexttrack', 'previoustrack']
      actions.forEach(action => {
        try {
          navigator.mediaSession.setActionHandler(action, null)
        } catch (e) {
          // 忽略错误
        }
      })

      console.log('[TTS] Media Session cleared')
    } catch (error) {
      console.error('[TTS] Failed to clear Media Session:', error)
    }
  }

  // ==================== 音频加载 ====================

  /**
   * 加载并播放音频
   * @param {Object} article - 文章对象 { id, title, content }
   * @param {Object} options - 可选参数 { voice, lang, rate }
   */
  const loadAudio = async (article, options = {}) => {
    // ✅ 修复：不再硬编码 voice 默认值，让后端使用配置文件中的默认值
    // 后端 settings.py: openai_tts_voice = "nova"
    const { voice = null, lang = 'auto', rate: inheritedRate = null, startTime = 0 } = options

    try {
      isLoading.value = true
      loadError.value = null
      currentArticle.value = article

      // 获取签名播放 URL（HTML5 audio 标签无法发送 Authorization header，必须使用签名 URL）
      const url = await getTtsPlayUrl(article.id, { voice, lang })
      console.log('[TTS] 开始加载音频:', article.id, voice ? `(voice: ${voice})` : '(使用后端默认 voice)')

      // ✅ 修复：确保 Audio 实例存在时，传递继承的播放速率
      ensureAudioInstance(inheritedRate)

      // 配置 Media Session（支持锁屏/车载控制）
      setupMediaSession(article)

      // 设置音频源（浏览器自动处理：流式播放 + 缓存）
      audio.value.src = url
      // 单例 Audio 复用：重置每源生效的 canplay 倍速降级标记，确保新的一篇文章能再走一次流式检测
      streamingRateHandledForSrc = false

      // 如有恢复点，尽早尝试在播放前定位，避免先从 0 播放后再跳转导致“重头播”错觉
      if (startTime > 0) {
        const waitForMetadata = new Promise((resolve) => {
          if (audio.value.readyState >= 1) {
            resolve()
            return
          }
          const onMetadata = () => {
            audio.value.removeEventListener('loadedmetadata', onMetadata)
            resolve()
          }
          audio.value.addEventListener('loadedmetadata', onMetadata)
          setTimeout(() => {
            audio.value.removeEventListener('loadedmetadata', onMetadata)
            resolve()
          }, 3000)
        })

        await waitForMetadata
        try {
          audio.value.currentTime = startTime
          logToStorage('[TTS] loadAudio 恢复到历史进度', { startTime }, { type: 'info', key: 'debug.loadAudioResumedProgress' })
        } catch (e) {
          console.warn('[TTS] 设置恢复进度失败:', e)
          logToStorage('[TTS] loadAudio 设置恢复进度失败', { startTime, error: e.message }, { type: 'error', key: 'debug.loadAudioSetProgressFailed' })
        }
      }

      // 记录本次流式起点
      activeStreamArticleId = article.id || null
      manualPause = false
      autoResumeAttempted = false
      logToStorage('[TTS] 开始拉流', {
        articleId: activeStreamArticleId,
        voice: voice || 'default',
        lang
      }, { type: 'info', key: 'debug.startStreaming' })

      // 开始播放
      await audio.value.play()

      console.log('[TTS] 播放开始')
      return true
    } catch (error) {
      console.error('[TTS] 播放失败:', error)
      loadError.value = error.message || t('tts.audioPlaybackFailed')
      activeStreamArticleId = null

      showToast({
        message: t('tts.playFailed'),
        icon: 'fail',
        duration: 2000
      })

      throw error
    } finally {
      isLoading.value = false
    }
  }

  // ==================== 音频监听器 ====================

  const setupAudioListeners = () => {
    if (!audio.value) return

    // 时长元数据加载完成
    audio.value.addEventListener('loadedmetadata', () => {
      totalTime.value = audio.value.duration
      console.log('[TTS] Audio duration:', totalTime.value)

      // ✅ 修复：元数据加载后，重新确保播放速率正确
      // 流式播放时，playbackRate 可能在 ensureAudioInstance 后被重置
      const targetRate = rate.value
      if (Math.abs(audio.value.playbackRate - targetRate) > 0.01) {
        console.warn(`[TTS] loadedmetadata 时检测到播放速率异常: ${audio.value.playbackRate} → ${targetRate}`)
        audio.value.playbackRate = targetRate
        console.log(`[TTS] 已重新设置播放速率: ${targetRate}x`)
      }

      // 同步总时长到 playerStore
      if (playerStore && typeof playerStore.updateProgress === 'function') {
        playerStore.updateProgress(currentTime.value, totalTime.value)
      }

      // 如果时长可用，说明已是缓存文件，清理流式标记
      if (Number.isFinite(audio.value.duration)) {
        activeStreamArticleId = null
      }
    })

    // ✅ 修复：检测流式音频，主动降级倍速（避免解码失败）
    // canplay 事件在音频有足够数据开始播放时触发
    // 注意：单例 Audio 复用，必须用 streamingRateHandledForSrc 而不是 { once: true }
    // 否则只对会话内第一篇文章生效，第二篇起 iOS 流式降级保护会丢失
    audio.value.addEventListener('canplay', () => {
      if (streamingRateHandledForSrc) return

      const targetRate = rate.value
      const isStreaming = !Number.isFinite(audio.value.duration) || audio.value.duration === 0

      // iOS/Safari 对流式音频（duration 未知）不支持倍速
      if (isStreaming && Math.abs(targetRate - 1.0) > 0.01) {
        console.warn('[TTS] 检测到流式音频，iOS 平台限制，降级倍速到 1.0x')
        logToStorage('[TTS] 流式音频倍速降级', {
          targetRate,
          actualRate: audio.value.playbackRate,
          duration: audio.value.duration,
          readyState: audio.value.readyState,
          isStreaming
        }, { type: 'rate', key: 'debug.streamingRateDowngrade' })

        // ✅ 主动降级倍速到 1.0（避免解码失败）
        audio.value.playbackRate = 1.0

        // ✅ 给用户明确提示
        showToast({
          message: t('tts.firstPlaySpeedFixed'),
          type: 'warning',
          duration: 3000
        })

        streamingRateHandledForSrc = true
      } else if (!isStreaming && Math.abs(targetRate - 1.0) > 0.01) {
        // 非流式音频（缓存命中），正常设置倍速
        audio.value.playbackRate = targetRate
        console.log(`[TTS] 缓存命中，倍速设置成功: ${targetRate}x`)
        streamingRateHandledForSrc = true
      }
    })

    // 播放中 - 更新进度
    audio.value.addEventListener('timeupdate', () => {
      currentTime.value = audio.value.currentTime

      // 同步进度到 playerStore
      if (playerStore && typeof playerStore.updateProgress === 'function') {
        playerStore.updateProgress(currentTime.value, totalTime.value)
      }

      // 更新 Media Session 播放位置（支持 iOS 锁屏进度条）
      updateMediaSessionPositionState()
    })

    // 播放结束
    audio.value.addEventListener('ended', () => {
      console.log('[TTS] 播放结束')
      logToStorage('[TTS] Audio ended 事件触发', {
        currentTime: audio.value.currentTime,
        duration: audio.value.duration
      }, { type: 'info', key: 'debug.audioEnded' })

      activeStreamArticleId = null

      isPlaying.value = false
      isPaused.value = false
      currentTime.value = 0

      // 告知 iOS 播放已结束
      if ('mediaSession' in navigator) {
        try {
          navigator.mediaSession.playbackState = 'none'
        } catch (e) {
          console.warn('[TTS] Failed to set playbackState:', e)
        }
      }

      // 清理 Media Session
      clearMediaSession()

      // 调用播放结束回调（如果有）
      if (playerStore && typeof playerStore.onPlaybackEnd === 'function') {
        playerStore.onPlaybackEnd()
      }
    })

    // 播放开始
    audio.value.addEventListener('play', () => {
      isPlaying.value = true
      isPaused.value = false
      manualPause = false
      autoResumeAttempted = false

      logToStorage('[TTS] Audio play 事件触发', {
        currentTime: audio.value.currentTime,
        duration: audio.value.duration
      }, { type: 'info', key: 'debug.audioPlayEvent' })
    })

    // 暂停
    audio.value.addEventListener('pause', () => {
      isPlaying.value = false
      if (currentTime.value < totalTime.value) {
        isPaused.value = true
      }

      logToStorage('[TTS] Audio pause 事件触发', {
        currentTime: currentTime.value,
        totalTime: totalTime.value
      }, { type: 'info', key: 'debug.audioPauseEvent' })

      // 流式阶段的非用户暂停：尝试自动恢复或重拉
      if (!manualPause && activeStreamArticleId && !autoResumeAttempted) {
        autoResumeAttempted = true

        const { bufferedRemaining, hasBuffer } = getBufferedInfo()
        const ready = audio.value.readyState
        const needsReload = ready < 2 || !hasBuffer || bufferedRemaining < 0.3

        if (needsReload && currentArticle.value && !reloadingAfterPause) {
          reloadingAfterPause = true
          logToStorage('[TTS] 自动重拉尝试（缓冲不足）', {
            readyState: ready,
            bufferedRemaining,
            currentTime: audio.value.currentTime
          }, { type: 'warning', key: 'debug.autoReloadAttempt' })

          loadAudio(currentArticle.value, {
            rate: rate.value,
            startTime: audio.value.currentTime
          }).catch(err => {
            logToStorage('[TTS] 自动重拉失败', { error: err?.message }, { type: 'error', key: 'debug.autoReloadFailed' })
          }).finally(() => {
            reloadingAfterPause = false
          })
        } else {
          logToStorage('[TTS] 自动恢复播放尝试', {
            currentTime: audio.value.currentTime,
            duration: audio.value.duration,
            readyState: ready,
            bufferedRemaining
          }, { type: 'info', key: 'debug.autoResumeAttempt' })
          audio.value.play().catch((err) => {
            logToStorage('[TTS] 自动恢复失败', { error: err?.message }, { type: 'error', key: 'debug.autoResumeFailed' })

            // Play 失败且缓冲不足时，尝试重拉
            if (!reloadingAfterPause && (ready < 2 || !hasBuffer)) {
              reloadingAfterPause = true
              loadAudio(currentArticle.value, {
                rate: rate.value,
                startTime: audio.value.currentTime
              }).finally(() => {
                reloadingAfterPause = false
              })
            }
          })
        }
      }

      // 重置标记，下一次由 play 事件重新置为 false
      manualPause = false
    })

    // 加载错误
    audio.value.addEventListener('error', () => {
      const errorDetail = {
        errorCode: audio.value.error?.code || null,
        errorMessage: audio.value.error?.message || 'unknown',
        src: audio.value.src?.substring(0, 100) || 'N/A',
        readyState: audio.value.readyState,
        networkState: audio.value.networkState
      }

      console.error('[TTS] 音频错误:', errorDetail)
      logToStorage('[TTS] Audio 错误', errorDetail, { type: 'error', key: 'debug.audioError' })

      loadError.value = t('tts.audioPlaybackFailed')
      isPlaying.value = false
      isPaused.value = false
    })
  }

  // ==================== 播放控制 ====================

  /**
   * 确保存在 Audio 实例并重置旧状态
   * @param {number} inheritedRate - 从外部继承的播放速率（优先级高于内部 rate.value）
   */
  function ensureAudioInstance(inheritedRate = null) {
    if (audio.value) {
      audio.value.pause()
    } else {
      audio.value = new Audio()
      audio.value.crossOrigin = 'anonymous'
      setupAudioListeners()
    }

    // ✅ 修复：优先使用继承的播放速率，确保与 playerStore 同步
    const targetRate = inheritedRate !== null ? inheritedRate : rate.value
    audio.value.playbackRate = targetRate
    rate.value = targetRate  // 同步内部状态
    console.log(`[TTS] ensureAudioInstance - 设置播放速率: ${targetRate}x`)
  }

  /**
   * 播放
   */
  const play = async () => {
    if (!audio.value) {
      showToast(t('tts.pleaseLoadAudioFirst'))
      return
    }

    try {
      await audio.value.play()
      console.log('[TTS] Playing')
    } catch (error) {
      console.error('[TTS] Play failed:', error)
      showToast(t('tts.playFailed'))
    }
  }

  /**
   * 暂停
   */
  const pause = () => {
    if (audio.value) {
      manualPause = true
      audio.value.pause()
      console.log('[TTS] Paused')
    }
  }

  /**
   * 停止（重置到开头）
   */
  const stop = () => {
    if (audio.value) {
      manualPause = true
      audio.value.pause()
      audio.value.currentTime = 0
      isPlaying.value = false
      isPaused.value = false
      console.log('[TTS] Stopped')
    }
  }

  /**
   * 跳转到指定时间
   * @param {number} time - 目标时间 (秒)
   */
  const seekTo = (time) => {
    if (!audio.value) {
      console.warn('[TTS] seekTo: 无音频实例')
      return
    }

    // ✅ 修复：使用 audio.value 的实际时长，而不是 totalTime.value
    // 流式播放时 totalTime 可能尚未更新
    const duration = audio.value.duration || totalTime.value || 0

    if (duration <= 0) {
      console.warn('[TTS] seekTo: 音频时长未知，无法跳转')
      return
    }

    const targetTime = Math.max(0, Math.min(time, duration))

    // ✅ 修复：检查目标时间是否在已缓冲范围内（流式播放）
    const buffered = audio.value.buffered
    let isBuffered = false
    for (let i = 0; i < buffered.length; i++) {
      if (targetTime >= buffered.start(i) && targetTime <= buffered.end(i)) {
        isBuffered = true
        break
      }
    }

    // 流式阶段禁止跳到未生成/未缓冲的位置，避免超前 Range 导致超时
    if (!isBuffered && (!Number.isFinite(audio.value.duration) || activeStreamArticleId)) {
      showToast({
        message: t('tts.cannotSeekUnbuffered'),
        type: 'warning',
        duration: 2000
      })
      logToStorage('[TTS] seekTo 拒绝（未缓冲，流式阶段）', {
        targetTime,
        duration,
        bufferedRanges: Array.from({ length: buffered.length }, (_, i) => ({
          start: buffered.start(i),
          end: buffered.end(i)
        }))
      }, { type: 'warning', key: 'debug.seekToRejected' })
      return
    }

    console.log('[TTS] seekTo:', {
      current: audio.value.currentTime,
      target: targetTime,
      duration,
      buffered: isBuffered,
      bufferedRanges: Array.from({ length: buffered.length }, (_, i) => ({
        start: buffered.start(i),
        end: buffered.end(i)
      }))
    })

    try {
      audio.value.currentTime = targetTime
      currentTime.value = targetTime  // 立即同步状态

      // 更新 Media Session 位置
      updateMediaSessionPositionState()

      console.log('[TTS] Seeked to:', targetTime)
    } catch (error) {
      console.error('[TTS] seekTo failed:', error)
      logToStorage('[TTS] seekTo 失败', {
        error: error.message,
        targetTime,
        duration
      }, { type: 'error', key: 'debug.seekToFailed' })
    }
  }

  /**
   * 快进
   * @param {number} seconds - 快进秒数（默认 15 秒）
   */
  const forward = (seconds = 15) => {
    if (!audio.value) {
      console.warn('[TTS] forward: 无音频实例')
      return
    }

    // ✅ 修复：使用 audio.currentTime 而不是 currentTime.value
    // 避免状态同步延迟导致的跳转不准确
    const newTime = audio.value.currentTime + seconds
    console.log(`[TTS] 快进 ${seconds} 秒: ${audio.value.currentTime} → ${newTime}`)
    seekTo(newTime)
  }

  /**
   * 快退
   * @param {number} seconds - 快退秒数（默认 15 秒）
   */
  const backward = (seconds = 15) => {
    if (!audio.value) {
      console.warn('[TTS] backward: 无音频实例')
      return
    }

    // ✅ 修复：使用 audio.currentTime 而不是 currentTime.value
    const newTime = audio.value.currentTime - seconds
    console.log(`[TTS] 快退 ${seconds} 秒: ${audio.value.currentTime} → ${newTime}`)
    seekTo(newTime)
  }

  /**
   * 设置播放速度
   * @param {number} newRate - 播放速度 (0.75, 1.0, 1.25, 1.5, 2.0)
   */
  const setRate = (newRate) => {
    if (!audio.value) {
      console.warn('[TTS] setRate: 无音频实例')
      rate.value = newRate  // 保存设置，等待音频加载后应用
      return
    }

    rate.value = newRate

    // ✅ 修复：增强日志，记录设置前后的实际 playbackRate
    const oldRate = audio.value.playbackRate
    console.log(`[TTS] 设置播放速率: ${oldRate}x → ${newRate}x`, {
      readyState: audio.value.readyState,
      paused: audio.value.paused,
      currentTime: audio.value.currentTime,
      duration: audio.value.duration
    })

    audio.value.playbackRate = newRate

    // ✅ 验证设置是否生效
    const actualRate = audio.value.playbackRate
    if (Math.abs(actualRate - newRate) > 0.01) {
      console.warn(`[TTS] 播放速率设置异常: 期望 ${newRate}x, 实际 ${actualRate}x`)
      logToStorage('[TTS] 播放速率设置异常', {
        expected: newRate,
        actual: actualRate,
        readyState: audio.value.readyState
      }, { type: 'rate', key: 'debug.playbackRateAnomaly' })
    } else {
      console.log(`[TTS] 播放速率已生效: ${actualRate}x`)
    }

    // 更新 Media Session（避免位置被重置）
    if ('mediaSession' in navigator && !audio.value.paused) {
      updateMediaSessionPositionState()
    }
  }

  // ==================== 清理函数 ====================

  /**
   * 清理资源
   */
  const cleanup = () => {
    if (audio.value) {
      audio.value.pause()
      audio.value = null
    }

    // 清理 Media Session
    clearMediaSession()

    // 清理状态
    isPlaying.value = false
    isPaused.value = false
    isLoading.value = false
    loadError.value = null
    currentArticle.value = null
    currentTime.value = 0
    totalTime.value = 0

    console.log('[TTS] 已清理')
  }

  // 组件卸载时清理
  onUnmounted(() => {
    cleanup()
  })

  // ==================== 返回接口 ====================

  return {
    // 状态
    isPlaying,
    isPaused,
    isLoading,
    loadError,
    currentArticle,

    // 进度
    currentTime,
    totalTime,
    progress,

    // 播放速度
    rate,
    setRate,

    // 音频加载
    loadAudio,

    // 播放控制
    play,
    pause,
    stop,
    seekTo,
    forward,
    backward,

    // Media Session（iOS 后台播放）
    setupMediaSession,
    updateMediaSessionPositionState,
    clearMediaSession,

    // 清理
    cleanup
  }
}
