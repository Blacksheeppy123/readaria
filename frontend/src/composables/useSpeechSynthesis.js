import { ref, onUnmounted, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { showToast } from 'vant'
import { useUserStore } from '@/stores/userStore'

/**
 * TTS (Text-to-Speech) Composable
 * 使用浏览器原生 Web Speech API 实现语音朗读功能
 * 支持进度模拟、跳转、播放结束回调
 */
export function useSpeechSynthesis(playerStore = null) {
  const { t } = useI18n()

  // 检查浏览器支持
  const isSupported = ref('speechSynthesis' in window)

  // 播放状态
  const isPlaying = ref(false)
  const isPaused = ref(false)
  const currentText = ref('')
  const currentUtterance = ref(null)

  // 播放控制
  const rate = ref(1.0) // 播放速度 (0.1 - 10)
  const pitch = ref(1.0) // 音调 (0 - 2)
  const volume = ref(1.0) // 音量 (0 - 1)
  const voice = ref(null) // 选择的语音

  // 可用的语音列表
  const voices = ref([])

  // 进度跟踪
  const currentTime = ref(0) // 当前播放时间 (秒)
  const totalTime = ref(0) // 总时长 (秒)
  let progressInterval = null // 进度更新定时器

  // 手动暂停标记（Android Chrome 不支持 speechSynthesis.pause/resume，用 cancel + 重播模拟）
  let manualPause = false
  let currentChunkPlan = null
  const CHUNK_MAX_LENGTH = 120

  const resolveSpeechLang = () => {
    const langMap = { zh: 'zh-CN', en: 'en-US' }
    try {
      const userStore = useUserStore()
      const pref = userStore.user?.preferred_language
      return langMap[pref] || pref || 'zh-CN'
    } catch (e) {
      return 'zh-CN'
    }
  }

  // 加载可用语音（支持异步等待，解决 Android 上 voices 延迟加载问题）
  const loadVoices = async (timeoutMs = 2000) => {
    const availableVoices = window.speechSynthesis.getVoices()
    if (availableVoices.length > 0) {
      voices.value = availableVoices
      return true
    }

    return new Promise((resolve) => {
      let resolved = false
      const handler = () => {
        if (resolved) return
        const list = window.speechSynthesis.getVoices()
        voices.value = list
        resolved = true
        resolve(list.length > 0)
      }

      window.speechSynthesis.onvoiceschanged = handler

      // 某些设备不会触发 voiceschanged，轮询兜底
      const interval = setInterval(() => {
        if (resolved) {
          clearInterval(interval)
          return
        }
        const list = window.speechSynthesis.getVoices()
        if (list.length > 0) {
          handler()
          clearInterval(interval)
        }
      }, 200)

      setTimeout(() => {
        if (!resolved) {
          resolved = true
          clearInterval(interval)
          resolve(false)
        }
      }, timeoutMs)
    })
  }

  // 初始化时尝试加载
  if (isSupported.value) {
    if (window.speechSynthesis.getVoices().length > 0) {
      loadVoices()
    } else {
      window.speechSynthesis.onvoiceschanged = () => loadVoices()
    }
  }

  /**
   * 文本预处理 - 清理 HTML 和特殊字符
   * @param {string} html - 原始 HTML 文本
   * @returns {string} 清理后的纯文本
   */
  const preprocessText = (html) => {
    if (!html) return ''

    // 纯文本方式剥离 HTML 标签，避免 innerHTML 解析带来的 XSS 风险
    let text = html
      // 先移除 script/style 标签及其内容
      .replace(/<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script\s*>/gi, ' ')
      .replace(/<style\b[^<]*(?:(?!<\/style>)<[^<]*)*<\/style\s*>/gi, ' ')
      // 再移除所有剩余 HTML 标签
      .replace(/<[^>]+>/g, ' ')
      // 清理多余空白
      .replace(/\s+/g, ' ')
      .trim()

    // 移除 URL
    text = text.replace(/https?:\/\/[^\s]+/g, '')

    return text
  }

  /**
   * 估算朗读总时长
   * @param {string} text - 文本内容
   * @param {number} playbackRate - 播放速度
   * @returns {number} 估算时长 (秒)
   */
  const estimateDuration = (text, playbackRate = 1.0) => {
    if (!text) return 0

    const cleanText = preprocessText(text)
    // 中文约 5 字/秒,英文约 10 字/秒 (速度为 1.0 时)
    // 这里使用保守估计: 5 字/秒
    const charsPerSecond = 5 * playbackRate
    return cleanText.length / charsPerSecond
  }

  /**
   * 开始进度跟踪
   */
  const startProgressTracking = () => {
    // 清除旧的定时器
    if (progressInterval) {
      clearInterval(progressInterval)
    }

    // 每 100ms 更新一次进度
    progressInterval = setInterval(() => {
      currentTime.value += 0.1

      // 同步到 Player Store
      if (playerStore && playerStore.updateProgress) {
        playerStore.updateProgress(currentTime.value, totalTime.value)
      }

      // 播放结束检测
      if (currentTime.value >= totalTime.value) {
        clearInterval(progressInterval)
        progressInterval = null
      }
    }, 100)
  }

  /**
   * 停止进度跟踪
   */
  const stopProgressTracking = () => {
    if (progressInterval) {
      clearInterval(progressInterval)
      progressInterval = null
    }
  }

  /**
   * 分段文本 - 将长文本分成多个段落
   * Web Speech API 对单次朗读文本长度有限制
   * @param {string} text - 完整文本
   * @param {number} maxLength - 单段最大长度
   * @returns {string[]} 文本段落数组
   */
  const splitText = (text, maxLength = 200) => {
    const chunks = []

    // 按句子分割
    const sentences = text.match(/[^.!?。!?]+[.!?。!?]*/g) || [text]

    let currentChunk = ''

    sentences.forEach(sentence => {
      if (currentChunk.length + sentence.length > maxLength) {
        if (currentChunk) {
          chunks.push(currentChunk.trim())
        }
        currentChunk = sentence
      } else {
        currentChunk += sentence
      }
    })

    if (currentChunk) {
      chunks.push(currentChunk.trim())
    }

    return chunks
  }

  const buildChunkPlan = (text, maxLength = CHUNK_MAX_LENGTH) => {
    const chunks = splitText(text, maxLength).filter(Boolean)
    return { chunks }
  }

  const playChunk = (plan, chunkIndex = 0, targetVoice = null) => {
    const chunkText = plan?.chunks?.[chunkIndex]
    if (!chunkText) {
      isPlaying.value = false
      isPaused.value = false
      stopProgressTracking()
      currentUtterance.value = null

      if (playerStore && playerStore.onPlaybackEnd) {
        playerStore.onPlaybackEnd()
      }
      return
    }

    currentChunkPlan = plan
    const utterance = new SpeechSynthesisUtterance(chunkText)

    // 设置参数
    utterance.rate = rate.value
    utterance.pitch = pitch.value
    utterance.volume = volume.value
    utterance.lang = resolveSpeechLang()
    if (targetVoice) {
      utterance.voice = targetVoice
    }

    utterance.onstart = () => {
      isPlaying.value = true
      isPaused.value = false
      startProgressTracking()
      if (playerStore && playerStore.onLegacyPlaybackStart) {
        playerStore.onLegacyPlaybackStart()
      }
    }

    utterance.onend = () => {
      if (currentUtterance.value !== utterance) return
      if (manualPause) {
        isPlaying.value = true
        isPaused.value = true
        return
      }

      const nextChunkIndex = chunkIndex + 1
      if (nextChunkIndex < plan.chunks.length) {
        playChunk(plan, nextChunkIndex, targetVoice)
        return
      }

      isPlaying.value = false
      isPaused.value = false
      stopProgressTracking()
      currentUtterance.value = null
      currentChunkPlan = null

      if (playerStore && playerStore.onPlaybackEnd) {
        playerStore.onPlaybackEnd()
      }
    }

    utterance.onerror = (event) => {
      if (currentUtterance.value !== utterance) return
      console.error('Speech synthesis error:', event.error, event)
      isPlaying.value = false
      isPaused.value = false
      stopProgressTracking()

      if (event.error === 'canceled' || event.error === 'interrupted') {
        if (manualPause) {
          isPlaying.value = true
          isPaused.value = true
        }
        return
      }

      const retriableErrors = ['synthesis-failed', 'voice-unavailable', 'language-unavailable']
      if (targetVoice && retriableErrors.includes(event.error)) {
        console.warn('[useSpeechSynthesis] Voice-specific error, retrying without explicit voice...')
        playChunk(plan, chunkIndex, null)
        return
      }

      const errorMap = {
        'not-allowed': t('speech.permissionDenied'),
        'voice-unavailable': t('speech.voiceUnavailable'),
        'language-unavailable': t('speech.languageUnavailable'),
        'network': t('speech.networkError'),
        'synthesis-failed': t('speech.synthesisFailed'),
        'audio-busy': t('speech.audioBusy'),
        'audio-hardware': t('speech.audioHardwareError')
      }
      currentChunkPlan = null
      if (playerStore && playerStore.onLegacyPlaybackError) {
        playerStore.onLegacyPlaybackError(event.error)
      }
      showToast(errorMap[event.error] || t('speech.speechErrorRetry'))
    }

    currentUtterance.value = utterance
    window.speechSynthesis.speak(utterance)
  }

  /**
   * 内部执行朗读
   * @param {string} cleanText - 清理后的文本
   * @param {SpeechSynthesisVoice|null} targetVoice - 指定语音（null 则由系统根据 lang 自动选择）
   */
  const doSpeak = (cleanText, targetVoice = null) => {
    const plan = buildChunkPlan(cleanText)
    if (!plan.chunks.length) {
      showToast(t('speech.noReadableContent'))
      return
    }
    playChunk(plan, 0, targetVoice)
  }

  /**
   * 开始朗读
   * @param {string} text - 要朗读的文本 (可以是 HTML)
   */
  const speak = async (text) => {
    if (!isSupported.value) {
      showToast(t('speech.browserNotSupported'))
      return
    }

    // 停止当前朗读
    stop()

    // 预处理文本
    const cleanText = preprocessText(text)

    if (!cleanText) {
      showToast(t('speech.noReadableContent'))
      return
    }

    currentText.value = cleanText

    // 估算总时长
    totalTime.value = estimateDuration(cleanText, rate.value)
    currentTime.value = 0

    // 同步初始进度到 Player Store
    if (playerStore && playerStore.updateProgress) {
      playerStore.updateProgress(0, totalTime.value)
    }

    // 非阻塞加载 voices（不阻塞 speak，避免打断 Android 用户手势同步链）
    // 系统会根据 utterance.lang 自动选择默认 voice
    if (voices.value.length === 0) {
      loadVoices().catch(() => {})
    }

    // 默认让系统根据 lang 自动选择 voice；如果用户手动选过 voice 才显式绑定
    doSpeak(cleanText, voice.value)
  }

  /**
   * 暂停朗读
   * 注：Android Chrome 不支持 speechSynthesis.pause()，统一用 cancel() + 标记模拟
   */
  const pause = () => {
    if (isPlaying.value && !isPaused.value) {
      manualPause = true
      isPaused.value = true
      stopProgressTracking()
      window.speechSynthesis.cancel()
    }
  }

  /**
   * 恢复朗读
   * 从 currentTime 位置重新播放剩余文本
   */
  const resume = () => {
    if (isPlaying.value && isPaused.value && manualPause) {
      manualPause = false
      isPaused.value = false
      if (currentText.value && totalTime.value > 0) {
        const progressRatio = currentTime.value / totalTime.value
        const charIndex = Math.floor(currentText.value.length * progressRatio)
        const remainingText = currentText.value.slice(charIndex)
        if (remainingText) {
          doSpeak(remainingText, voice.value)
          return
        }
      }
      // 若无法计算剩余文本，从头重播
      if (currentText.value) {
        doSpeak(currentText.value, voice.value)
      }
    }
  }

  /**
   * 停止朗读
   */
  const stop = () => {
    manualPause = false
    currentChunkPlan = null
    window.speechSynthesis.cancel()
    isPlaying.value = false
    isPaused.value = false
    currentUtterance.value = null
    stopProgressTracking()
    currentTime.value = 0
    totalTime.value = 0
  }

  /**
   * 跳转到指定时间
   * Web Speech API 不支持直接跳转,需要重新播放
   * @param {number} targetTime - 目标时间 (秒)
   * @param {number} totalDuration - 总时长 (秒)
   */
  const seekTo = (targetTime, totalDuration) => {
    if (!currentText.value || !totalDuration || totalDuration === 0) return

    // 计算目标位置的字符索引
    const progress = targetTime / totalDuration
    const charIndex = Math.floor(currentText.value.length * progress)
    const remainingText = currentText.value.slice(charIndex)

    if (!remainingText) {
      showToast(t('speech.reachedEnd'))
      return
    }

    // 停止当前朗读 (但不重置 currentText)
    window.speechSynthesis.cancel()
    stopProgressTracking()

    // 更新时间
    currentTime.value = targetTime
    totalTime.value = totalDuration

    // 同步进度到 Player Store
    if (playerStore && playerStore.updateProgress) {
      playerStore.updateProgress(currentTime.value, totalTime.value)
    }

    // 重新开始播放剩余部分
    const utterance = new SpeechSynthesisUtterance(remainingText)
    utterance.rate = rate.value
    utterance.pitch = pitch.value
    utterance.volume = volume.value
    utterance.lang = resolveSpeechLang()
    if (voice.value) {
      utterance.voice = voice.value
    }

    utterance.onstart = () => {
      isPlaying.value = true
      isPaused.value = false
      startProgressTracking()
      if (playerStore && playerStore.onLegacyPlaybackStart) {
        playerStore.onLegacyPlaybackStart()
      }
    }

    utterance.onend = () => {
      if (currentUtterance.value !== utterance) return
      isPlaying.value = false
      isPaused.value = false
      stopProgressTracking()
      currentUtterance.value = null

      if (playerStore && playerStore.onPlaybackEnd) {
        playerStore.onPlaybackEnd()
      }
    }

    utterance.onerror = (event) => {
      if (currentUtterance.value !== utterance) return
      console.error('Speech synthesis error (seek):', event.error, event)
      isPlaying.value = false
      isPaused.value = false
      stopProgressTracking()

      if (event.error === 'canceled' || event.error === 'interrupted') {
        if (manualPause) {
          isPlaying.value = true
          isPaused.value = true
        }
        return
      }

      const retriableErrors = ['synthesis-failed', 'voice-unavailable', 'language-unavailable']
      if (voice.value && retriableErrors.includes(event.error)) {
        console.warn('[useSpeechSynthesis] Voice-specific error on seek, retrying without explicit voice...')
        const retryUtterance = new SpeechSynthesisUtterance(remainingText)
        retryUtterance.rate = rate.value
        retryUtterance.pitch = pitch.value
        retryUtterance.volume = volume.value
        retryUtterance.lang = resolveSpeechLang()
        retryUtterance.onstart = () => {
          isPlaying.value = true
          isPaused.value = false
          startProgressTracking()
          if (playerStore && playerStore.onLegacyPlaybackStart) {
            playerStore.onLegacyPlaybackStart()
          }
        }
        retryUtterance.onend = () => {
          if (currentUtterance.value !== retryUtterance) return
          isPlaying.value = false
          isPaused.value = false
          stopProgressTracking()
          currentUtterance.value = null
          if (playerStore && playerStore.onPlaybackEnd) {
            playerStore.onPlaybackEnd()
          }
        }
        retryUtterance.onerror = (ev2) => {
          if (currentUtterance.value !== retryUtterance) return
          if (ev2.error === 'canceled' || ev2.error === 'interrupted') {
            if (manualPause) {
              isPlaying.value = true
              isPaused.value = true
            }
            return
          }
          if (playerStore && playerStore.onLegacyPlaybackError) {
            playerStore.onLegacyPlaybackError(ev2.error)
          }
          showToast(t('speech.speechErrorRetry'))
        }
        currentUtterance.value = retryUtterance
        window.speechSynthesis.speak(retryUtterance)
        return
      }

      if (playerStore && playerStore.onLegacyPlaybackError) {
        playerStore.onLegacyPlaybackError(event.error)
      }
      showToast(t('speech.speechErrorRetry'))
    }

    currentUtterance.value = utterance
    window.speechSynthesis.speak(utterance)
  }

  /**
   * 切换播放/暂停
   */
  const togglePlayPause = () => {
    if (isPlaying.value) {
      if (isPaused.value) {
        resume()
      } else {
        pause()
      }
    }
  }

  /**
   * 设置播放速度
   * @param {number} newRate - 新速度 (0.5 - 2.0)
   */
  const setRate = (newRate) => {
    rate.value = Math.max(0.5, Math.min(2.0, newRate))

    // 如果正在播放,需要重新开始
    if (isPlaying.value && currentText.value) {
      const wasPlaying = !isPaused.value
      const savedTime = currentTime.value
      const savedTotal = totalTime.value

      stop()

      // 重新估算总时长 (基于新速度)
      totalTime.value = estimateDuration(currentText.value, rate.value)

      speak(currentText.value)

      // 如果之前是暂停状态,保持暂停
      if (!wasPlaying) {
        pause()
      }

      // 尝试恢复进度位置
      if (savedTime > 0 && savedTotal > 0) {
        const progressRatio = savedTime / savedTotal
        seekTo(totalTime.value * progressRatio, totalTime.value)
      }
    }
  }

  /**
   * 设置音量
   * @param {number} newVolume - 新音量 (0 - 1)
   */
  const setVolume = (newVolume) => {
    volume.value = Math.max(0, Math.min(1, newVolume))
    if (currentUtterance.value) {
      currentUtterance.value.volume = volume.value
    }
  }

  // 计算属性
  const rateLabel = computed(() => {
    const rates = {
      0.5: '0.5x',
      0.75: '0.75x',
      1.0: '1.0x',
      1.25: '1.25x',
      1.5: '1.5x',
      2.0: '2.0x'
    }
    return rates[rate.value] || `${rate.value}x`
  })

  // 组件卸载时停止朗读
  onUnmounted(() => {
    stop()
  })

  return {
    // 状态
    isSupported,
    isPlaying,
    isPaused,
    currentText,
    currentTime,
    totalTime,

    // 控制参数
    rate,
    pitch,
    volume,
    voice,
    voices,
    rateLabel,
    resolveSpeechLang,

    // 方法
    speak,
    pause,
    resume,
    stop,
    seekTo,
    togglePlayPause,
    setRate,
    setVolume,

    // 工具方法
    preprocessText,
    estimateDuration
  }
}
