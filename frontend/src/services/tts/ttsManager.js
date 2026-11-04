/**
 * TTS Manager - 统一语音合成管理器
 *
 * 实现两层 TTS 架构：
 * - Tier 1: 云端高质量缓存 (OpenAI/Azure TTS) - 默认优先
 * - Tier 2: 云端实时生成 (OpenAI) - fallback
 *
 * 自动选择最佳 TTS 引擎，提供统一的 API 接口
 */

import { ref } from 'vue'
import { resolvePreferredVoice } from '@/utils/ttsVoicePreference'

// ==================== 常量定义 ====================

const TTS_TIER = {
  CLOUD_CACHED: 'cloud_cached',    // Tier 1: 云端缓存
  CLOUD_REALTIME: 'cloud_realtime' // Tier 2: 云端实时
}

const TTS_CONFIG = {
  // 默认引擎优先级
  DEFAULT_PRIORITY: [
    TTS_TIER.CLOUD_CACHED,
    TTS_TIER.CLOUD_REALTIME
  ],

  // 音频格式
  AUDIO_FORMAT: {
    MP3: 'audio/mpeg',
    WAV: 'audio/wav',
    OGG: 'audio/ogg'
  },

  // 超时设置
  TIMEOUT: {
    CLOUD_CACHE_CHECK: 2000,    // 缓存检查超时
    CLOUD_PLAY: 30000           // 云端播放超时
  },

  // 重试配置
  RETRY: {
    MAX_ATTEMPTS: 2,
    DELAY_MS: 1000
  }
}

// ==================== 状态管理 ====================

const state = ref({
  // 当前使用的 TTS 层级
  currentTier: null,

  // 各引擎状态
  tierStatus: {
    [TTS_TIER.CLOUD_CACHED]: { available: true, initialized: false },
    [TTS_TIER.CLOUD_REALTIME]: { available: true, initialized: false }
  },

  // 用户偏好设置
  preferences: {
    // 默认语音
    voice: null,
    // 语速
    speed: 1.0,
    // 首选层级（用户手动选择）
    preferredTier: null, // 'cloud_realtime' | null (auto)
    // 是否记住用户选择
    rememberPreference: true
  },

  // 缓存状态
  cacheStatus: new Map(), // articleId -> { status: 'hit'|'miss'|'generating', timestamp }

  // 回退历史记录
  fallbackHistory: [], // [{ articleId, fromTier, toTier, timestamp, reason }]

  // 初始化状态
  initialized: false,
  initializing: false
})

// ==================== 工具函数 ====================

/**
 * 带超时的 Promise
 */
function withTimeout(promise, timeoutMs, errorMessage) {
  return Promise.race([
    promise,
    new Promise((_, reject) =>
      setTimeout(() => reject(new Error(errorMessage || 'Timeout')), timeoutMs)
    )
  ])
}

/**
 * 检查云端缓存状态
 * 标准化缓存状态：API 返回 { cache: 'hit'|'miss' }，内部统一使用 { status: 'hit'|'miss' }
 */
async function checkCloudCache(articleId, options = {}) {
  if (!articleId) return { status: 'miss' }

  try {
    const { checkTtsCache } = await import('@/api/tts')
    const result = await withTimeout(
      checkTtsCache(articleId, { voice: options.voice || null }),
      TTS_CONFIG.TIMEOUT.CLOUD_CACHE_CHECK,
      'Cache check timeout'
    )
    // 标准化响应格式：支持 result.status 或 result.cache
    const status = result?.status ?? result?.cache ?? 'miss'
    return { status, ...result }
  } catch (error) {
    console.warn('[TTSManager] Cache check failed:', error)
    return { status: 'miss' }
  }
}

/**
 * 获取 API 基础 URL
 */
function getApiBaseUrl() {
  return import.meta.env.VITE_API_BASE_URL || ''
}

function buildCloudPlaybackSource(article, options = {}) {
  return {
    type: 'cloud_v2',
    articleId: article.id,
    // 显式传入优先（测试/调试），否则按文章语言解析用户音色偏好；
    // 解析结果为 null 时后端走系统默认音色（现状行为不变）
    voice: options.voice || resolvePreferredVoice(article),
    apiBaseUrl: getApiBaseUrl()
  }
}

// ==================== 核心 API ====================

/**
 * 初始化 TTS Manager
 * 检测各引擎可用性
 */
export async function initialize(options = {}) {
  if (state.value.initialized || state.value.initializing) {
    return state.value.initialized
  }

  state.value.initializing = true

  try {
    // 加载用户偏好设置
    loadPreferences()

    state.value.initialized = true
    console.log('[TTSManager] Initialized, tiers:', state.value.tierStatus)

    return true
  } catch (error) {
    console.error('[TTSManager] Initialization failed:', error)
    return false
  } finally {
    state.value.initializing = false
  }
}

/**
 * 记录回退历史
 */
function recordFallback(articleId, fromTier, toTier, reason) {
  const record = {
    articleId,
    fromTier,
    toTier,
    timestamp: Date.now(),
    reason
  }

  state.value.fallbackHistory.push(record)

  // 只保留最近 50 条记录
  if (state.value.fallbackHistory.length > 50) {
    state.value.fallbackHistory.shift()
  }
}

/**
 * 选择最佳 TTS 引擎
 * @param {Object} context - 播放上下文
 * @param {number} context.articleId - 文章 ID
 * @param {boolean} context.requireHighQuality - 是否要求高质量
 * @param {boolean} context.canUseCloud - 是否可以使用云端 TTS
 */
export async function selectBestTier(context = {}) {
  const { articleId, voice = null, requireHighQuality = false, canUseCloud = true } = context
  const { preferredTier } = state.value.preferences

  // 如果强制使用云端
  if (state.value.preferences.forceCloud || requireHighQuality) {
    // 先检查缓存（与播放一致的音色）
    if (articleId) {
      const cacheStatus = await checkCloudCache(articleId, { voice })
      if (cacheStatus.status === 'hit') {
        return { tier: TTS_TIER.CLOUD_CACHED, reason: 'cache_hit' }
      }
    }
    return { tier: TTS_TIER.CLOUD_REALTIME, reason: 'force_cloud' }
  }

  // 优先检查云端缓存（所有用户都可用；与播放一致的音色）
  if (articleId) {
    const cacheStatus = await checkCloudCache(articleId, { voice })
    if (cacheStatus.status === 'hit') {
      return { tier: TTS_TIER.CLOUD_CACHED, reason: 'cache_hit' }
    }
  }

  // 所有用户默认优先使用云端实时生成
  if (canUseCloud) {
    return { tier: TTS_TIER.CLOUD_REALTIME, reason: 'cloud_first' }
  }

  // 配额耗尽：返回云端实时，由后端返回 429，前端根据用户类型分别处理
  return { tier: TTS_TIER.CLOUD_REALTIME, reason: 'quota_exhausted' }
}

/**
 * 播放文章 TTS
 * @param {Object} article - 文章对象
 * @param {Object} options - 播放选项
 */
export async function playArticle(article, options = {}) {
  const {
    autoPlay = true,
    startTime = 0,
    onProgress,
    onError,
    onTierChange
  } = options

  if (!article || !article.id) {
    const error = new Error('Invalid article')
    if (onError) onError(error)
    throw error
  }

  // 确保已初始化
  if (!state.value.initialized) {
    await initialize()
  }

  // 选择最佳 TTS 引擎（voice 与后续播放保持一致，避免按默认音色缓存误判 tier）
  const tierSelection = await selectBestTier({
    articleId: article.id,
    voice: options.voice || resolvePreferredVoice(article),
    requireHighQuality: options.requireHighQuality,
    canUseCloud: options.canUseCloud !== false
  })

  const selectedTier = tierSelection.tier
  state.value.currentTier = selectedTier

  if (onTierChange) {
    onTierChange(selectedTier, tierSelection.reason)
  }

  console.log(`[TTSManager] Selected tier: ${selectedTier}, reason: ${tierSelection.reason}`)

  try {
    let audioUrl = null
    let duration = 0

    switch (selectedTier) {
      case TTS_TIER.CLOUD_CACHED:
        // 使用云端缓存音频
        audioUrl = await playCloudCached(article, { startTime })
        break

      case TTS_TIER.CLOUD_REALTIME:
        // 使用云端实时生成
        audioUrl = await playCloudRealtime(article, { startTime })
        break

      default:
        throw new Error(`Unknown tier: ${selectedTier}`)
    }

    return {
      tier: selectedTier,
      audioUrl,
      duration,
      article
    }
  } catch (error) {
    console.error(`[TTSManager] Play failed with tier ${selectedTier}:`, error)

    // 尝试降级到云端实时
    if (selectedTier !== TTS_TIER.CLOUD_REALTIME) {
      console.log('[TTSManager] Falling back to cloud realtime')
      recordFallback(article.id, selectedTier, TTS_TIER.CLOUD_REALTIME, error.message)
      return playArticle(article, {
        ...options,
        requireHighQuality: true // 强制使用云端
      })
    }

    if (onError) onError(error)
    throw error
  }
}

/**
 * 播放云端缓存音频
 */
async function playCloudCached(article, options = {}) {
  return buildCloudPlaybackSource(article, options)
}

/**
 * 使用云端实时生成播放
 */
async function playCloudRealtime(article, options = {}) {
  return buildCloudPlaybackSource(article, options)
}

/**
 * 预加载文章音频（后台生成缓存）
 * @param {number} articleId - 文章 ID
 */
export async function preloadArticle(articleId, article = null) {
  if (!articleId) return

  // 音色选择功能：预加载必须与后续播放使用同一音色，
  // 否则自定义音色用户会白白生成默认音色缓存（2026-09-08 review）
  const voice = article ? resolvePreferredVoice(article) : null

  try {
    // 1. 先检查云端缓存（同音色）
    const cacheStatus = await checkCloudCache(articleId, { voice })

    if (cacheStatus.status === 'hit') {
      return { status: 'cached', tier: 'cloud' }
    }

    if (cacheStatus.status === 'generating') {
      return { status: 'generating', tier: 'cloud' }
    }

    // 2. 触发云端后台生成（同音色）
    const { startTtsPrepare } = await import('@/api/tts')
    await startTtsPrepare(articleId, { voice })

    return { status: 'triggered', tier: 'cloud' }
  } catch (error) {
    console.warn('[TTSManager] Preload failed:', error)
    return { status: 'error', error: error.message }
  }
}

/**
 * 批量预加载
 * @param {Array<number>} articleIds - 文章 ID 列表
 */
export async function preloadArticles(articleIds) {
  if (!articleIds || articleIds.length === 0) return

  // 限制并发数
  const CONCURRENCY = 3
  const results = []

  for (let i = 0; i < articleIds.length; i += CONCURRENCY) {
    const batch = articleIds.slice(i, i + CONCURRENCY)
    const batchResults = await Promise.all(
      batch.map(id => preloadArticle(id))
    )
    results.push(...batchResults)
  }

  return results
}

// ==================== 设置管理 ====================

/**
 * 加载用户偏好设置
 */
function loadPreferences() {
  try {
    const saved = localStorage.getItem('tts_preferences')
    if (saved) {
      const prefs = JSON.parse(saved)
      state.value.preferences = {
        ...state.value.preferences,
        ...prefs
      }
    }
  } catch (error) {
    console.warn('[TTSManager] Failed to load preferences:', error)
  }
}

/**
 * 保存用户偏好设置
 */
export function savePreferences() {
  try {
    localStorage.setItem('tts_preferences', JSON.stringify(state.value.preferences))
  } catch (error) {
    console.warn('[TTSManager] Failed to save preferences:', error)
  }
}

/**
 * 更新偏好设置
 */
export function updatePreferences(newPrefs) {
  state.value.preferences = {
    ...state.value.preferences,
    ...newPrefs
  }
  savePreferences()
}

/**
 * 获取当前设置
 */
export function getPreferences() {
  return { ...state.value.preferences }
}

// ==================== 状态查询 ====================

/**
 * 获取当前 TTS 层级
 */
export function getCurrentTier() {
  return state.value.currentTier
}

/**
 * 获取各引擎状态
 */
export function getTierStatus() {
  return { ...state.value.tierStatus }
}

// ==================== 导出 ====================

export { TTS_TIER, TTS_CONFIG }

export default {
  initialize,
  selectBestTier,
  playArticle,
  preloadArticle,
  preloadArticles,
  updatePreferences,
  getPreferences,
  getCurrentTier,
  getTierStatus,
  TTS_TIER,
  TTS_CONFIG
}
