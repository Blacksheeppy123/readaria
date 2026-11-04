/**
 * TTS (Text-to-Speech) API 封装
 *
 * 提供 OpenAI TTS 合成服务的前端 API 调用接口
 */
import request from './request'

// Vite 代理下 baseURL 可能为空，生产使用环境变量
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || ''

function buildTtsParams({ voice = null, lang = 'auto' } = {}) {
  const params = new URLSearchParams()

  if (lang) {
    params.set('lang', lang)
  }

  if (voice) {
    params.set('voice', voice)
  }

  return params
}

/**
 * 合成语音
 *
 * @param {Object} params - 合成参数
 * @param {string} params.text - 待合成的文本（必填）
 * @param {number} [params.article_id] - 文章 ID（可选，用于缓存标识）
 * @param {string} [params.lang='auto'] - 语言（auto/zh/en）
 * @param {string} [params.voice='default'] - 声音（default/alloy/echo/fable/onyx/nova/shimmer）
 * @returns {Promise<Blob>} 返回音频 Blob 对象
 *
 * @example
 * const audioBlob = await synthesize({ text: '这是测试文本' })
 * const audioUrl = URL.createObjectURL(audioBlob)
 */
export async function synthesize({ text, article_id, lang = 'auto', voice = 'default' }) {
  try {
    const response = await request({
      url: '/api/v1/tts/synthesize',
      method: 'post',
      data: {
        text,
        article_id,
        lang,
        voice
      },
      // 关键：指定响应类型为 blob
      responseType: 'blob',
      // 超时设置：长文本可能需要较长时间
      timeout: 60000 // 60 秒
    })

    // 验证响应是否为音频文件
    if (response.type && !response.type.startsWith('audio/')) {
      throw new Error(`Invalid response type: ${response.type}, expected audio/*`)
    }

    return response
  } catch (error) {
    // 错误处理：如果是 Blob 类型的错误响应，尝试解析错误信息
    if (error.response && error.response.data instanceof Blob) {
      try {
        const text = await error.response.data.text()
        const errorData = JSON.parse(text)
        throw new Error(errorData.message || errorData.detail || 'TTS synthesis failed')
      } catch (parseError) {
        // 如果解析失败，抛出原始错误
        throw error
      }
    }

    // 重新抛出错误，由上层处理
    throw error
  }
}

/**
 * 流式合成语音（边生成边播放）
 *
 * @param {Object} params - 合成参数
 * @param {string} params.text - 待合成的文本
 * @param {number} [params.article_id] - 文章 ID
 * @param {string} [params.lang='auto'] - 语言
 * @param {string} [params.voice='default'] - 声线
 * @returns {Promise<{stream: ReadableStream, format: string, contentType: string}>}
 */
export async function synthesizeStream({ text, article_id, lang = 'auto', voice = 'default' }) {
  const token = localStorage.getItem('readaria_token')

  const response = await fetch(`${API_BASE_URL}/api/v1/tts/synthesize-stream`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { 'Authorization': `Bearer ${token}` } : {})
    },
    body: JSON.stringify({ text, article_id, lang, voice })
  })

  if (!response.ok) {
    let detail = 'TTS streaming failed'
    try {
      const errorJson = await response.json()
      detail = errorJson.detail || errorJson.message || detail
    } catch (_) {
      // ignore
    }
    throw new Error(detail)
  }

  if (!response.body) {
    throw new Error('当前环境不支持流式播放')
  }

  return {
    stream: response.body,
    format: response.headers.get('X-Audio-Format') || 'aac',
    contentType: response.headers.get('Content-Type') || 'audio/mp4'  // ✅ M4A 容器
  }
}

/**
 * 预加载下一篇文章的音频
 *
 * v2.0 注意：MP3 架构迁移后，前端不再需要预加载
 * - 后端使用服务器文件系统缓存（自动缓存命中）
 * - 浏览器 HTTP 缓存机制自动处理重复请求
 *
 * 保留此函数仅为兼容性，实际不执行任何操作
 *
 * @param {string} text - 文章文本（已废弃）
 * @param {number} article_id - 文章 ID（已废弃）
 * @returns {Promise<void>}
 *
 * @deprecated 新架构不再需要前端预加载
 */
export async function preloadNextArticle(text, article_id) {
  if (!article_id) {
    return Promise.resolve()
  }

  return startTtsPrepare(article_id)
}

/**
 * 获取缓存的音频 URL
 *
 * @param {number} article_id - 文章 ID
 * @returns {string|null} 音频 Blob URL 或 null
 */
export function getCachedAudio(article_id) {
  const cacheKey = `tts_audio_${article_id}`
  return sessionStorage.getItem(cacheKey)
}

/**
 * 清理音频缓存
 *
 * @param {number} article_id - 文章 ID
 */
export function clearAudioCache(article_id) {
  const cacheKey = `tts_audio_${article_id}`
  const audioUrl = sessionStorage.getItem(cacheKey)

  // 释放 Blob URL，避免内存泄漏
  if (audioUrl && audioUrl.startsWith('blob:')) {
    URL.revokeObjectURL(audioUrl)
  }

  sessionStorage.removeItem(cacheKey)
}

/**
 * 清理所有 TTS 音频缓存
 */
export function clearAllAudioCache() {
  const keys = Object.keys(sessionStorage)
  keys.forEach(key => {
    if (key.startsWith('tts_audio_')) {
      const audioUrl = sessionStorage.getItem(key)
      if (audioUrl && audioUrl.startsWith('blob:')) {
        URL.revokeObjectURL(audioUrl)
      }
      sessionStorage.removeItem(key)
    }
  })
  console.log('[TTS] Cleared all audio cache')
}

/**
 * 检查 TTS 缓存状态（cache_only）
 * @param {number|string} articleId
 * @returns {Promise<{cache: 'hit'|'miss', size?: number}>}
 */
export async function checkTtsCache(articleId, options = {}) {
  if (!articleId) return { cache: 'miss' }
  const { voice = null } = options
  const params = Object.fromEntries(buildTtsParams({ voice, lang: null }).entries())
  const res = await request({
    url: `/api/v1/tts/prepare/${articleId}`,
    method: 'get',
    params,
    headers: { 'X-Silent': 'true' }
  })

  return {
    cache: res?.final_ready ? 'hit' : (res?.status === 'generating' || res?.first_playable_ready ? 'generating' : 'miss'),
    ...res
  }
}

export async function startTtsPrepare(articleId, options = {}) {
  const { voice = null } = options
  if (!articleId) {
    throw new Error('articleId is required')
  }

  const params = Object.fromEntries(buildTtsParams({ voice, lang: null }).entries())
  return request({
    url: `/api/v1/tts/prepare/${articleId}`,
    method: 'post',
    params,
    headers: { 'X-Silent': 'true' }
  })
}

export async function getTtsPrepareStatus(articleId, options = {}) {
  const { voice = null } = options
  if (!articleId) {
    throw new Error('articleId is required')
  }

  const params = Object.fromEntries(buildTtsParams({ voice, lang: null }).entries())
  return request({
    url: `/api/v1/tts/prepare/${articleId}`,
    method: 'get',
    params,
    // 通过 header 传递 silent 标志，避免网络错误时弹出 Toast
    headers: { 'X-Silent': 'true' }
  })
}

/**
 * 获取 TTS 最终音频的签名播放 URL
 *
 * @param {number|string} articleId - 文章 ID
 * @param {Object} options - 选项
 * @param {string} [options.voice] - 声线
 * @param {string} [options.lang='auto'] - 语言
 * @returns {Promise<string>} 签名后的临时播放 URL
 */
export async function getTtsPlayUrl(articleId, options = {}) {
  const { voice = null, lang = 'auto' } = options
  const params = buildTtsParams({ voice, lang })
  const res = await request({
    url: `/api/v1/tts/play-url/${articleId}`,
    method: 'get',
    params: Object.fromEntries(params.entries()),
    headers: { 'X-Silent': 'true' }
  })
  // 拼接完整 URL（后端返回的是相对路径）
  return res.audio_url.startsWith('http')
    ? res.audio_url
    : `${API_BASE_URL}${res.audio_url}`
}

/**
 * 获取 TTS segment 的签名播放 URL
 *
 * @param {number|string} articleId - 文章 ID
 * @param {number} index - segment 索引
 * @param {Object} options - 选项
 * @param {string} [options.voice] - 声线
 * @returns {Promise<string>} 签名后的临时播放 URL
 */
export async function getTtsSegmentPlayUrl(articleId, index, options = {}) {
  const { voice = null } = options
  const params = buildTtsParams({ voice, lang: null })
  const res = await request({
    url: `/api/v1/tts/segment-play-url/${articleId}/${index}`,
    method: 'get',
    params: Object.fromEntries(params.entries()),
    headers: { 'X-Silent': 'true' }
  })
  return res.audio_url.startsWith('http')
    ? res.audio_url
    : `${API_BASE_URL}${res.audio_url}`
}

/**
 * @deprecated 直接构造 URL 不再安全，请使用 getTtsPlayUrl / getTtsSegmentPlayUrl
 */
export function getTtsFinalAudioUrl(articleId, options = {}) {
  const { voice = null, lang = 'auto' } = options
  const params = buildTtsParams({ voice, lang })
  return `${API_BASE_URL}/api/v1/tts/play/${articleId}?${params.toString()}`
}

/**
 * @deprecated 直接构造 URL 不再安全，请使用 getTtsSegmentPlayUrl
 */
export function getTtsSegmentAudioUrl(articleId, index, options = {}) {
  const { voice = null } = options
  const params = buildTtsParams({ voice, lang: null })
  return `${API_BASE_URL}/api/v1/tts/segments/${articleId}/${index}?${params.toString()}`
}

/**
 * 获取可选 TTS 音色目录（按语言分组）
 * @returns {Promise<{zh: Array, en: Array}>}
 */
export function getTtsVoices() {
  return request({
    url: '/api/v1/tts/voices',
    method: 'get'
  })
}

/**
 * 音色试听（不消耗 TTS 每日配额，文本为目录固定示例句）
 * @param {Object} params - { voice: string（目录音色 id 或 'default'）, lang: 'zh'|'en' }
 * @returns {Promise<Blob>} 音频 Blob
 */
export async function previewTtsVoice({ voice, lang }) {
  const response = await request({
    url: '/api/v1/tts/voice-preview',
    method: 'post',
    data: { voice, lang },
    responseType: 'blob',
    timeout: 30000
  })
  if (response.type && !response.type.startsWith('audio/')) {
    throw new Error(`Invalid response type: ${response.type}, expected audio/*`)
  }
  return response
}
