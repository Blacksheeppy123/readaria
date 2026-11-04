/**
 * 根据文章语言解析用户偏好的 TTS 音色（语音选择功能，2026-09-07）
 *
 * 用户偏好存后端 users 表（tts_voice_zh / tts_voice_en），
 * 前端经 localStorage 'readaria_user' 镜像读取 —— service 层（ttsManager）
 * 无 Pinia 依赖，直接读 localStorage 最稳妥。
 *
 * 返回 null = 不传 voice 参数，后端用系统默认音色（现状行为）。
 */

/**
 * 推断文章语言：优先用后端 language 字段，缺失时用 CJK/拉丁字符占比兜底
 * @param {Object} article
 * @returns {'zh'|'en'|null}
 */
function detectArticleLang(article) {
  const declared = (article?.language || '').toLowerCase()
  if (declared.startsWith('zh')) return 'zh'
  if (declared.startsWith('en')) return 'en'

  const text = `${article?.title || ''} ${String(article?.content || '').slice(0, 500)}`
  const cjk = (text.match(/[一-鿿]/g) || []).length
  const latin = (text.match(/[a-zA-Z]/g) || []).length
  if (cjk === 0 && latin === 0) return null
  return cjk >= latin ? 'zh' : 'en'
}

/**
 * 解析当前文章应使用的偏好音色
 * @param {Object} article - 文章对象（需含 language 或 title/content）
 * @param {Object} [user] - 用户对象；缺省时从 localStorage 'readaria_user' 读取
 * @returns {string|null} Azure 完整音色名，或 null（系统默认）
 */
export function resolvePreferredVoice(article, user = null) {
  try {
    const u = user || JSON.parse(localStorage.getItem('readaria_user') || 'null')
    if (!u) return null
    const lang = detectArticleLang(article)
    if (lang === 'zh') return u.tts_voice_zh || null
    if (lang === 'en') return u.tts_voice_en || null
    return null
  } catch (e) {
    return null
  }
}
