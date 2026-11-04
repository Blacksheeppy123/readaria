import request from './request'

/**
 * 用户注册
 * @param {Object} data - 注册数据
 * @param {string} data.username - 用户名
 * @param {string} data.email - 邮箱
 * @param {string} data.password - 密码
 * @param {string} [data.full_name] - 全名（可选）
 */
export function register(data) {
  return request({
    url: '/api/auth/register',
    method: 'post',
    data
  })
}

/**
 * 用户登录
 * @param {string} username - 用户名
 * @param {string} password - 密码
 */
export function login(username, password) {
  return request({
    url: '/api/auth/login',
    method: 'post',
    data: { username, password }
  })
}

/**
 * 获取当前登录用户信息
 */
export function getCurrentUser(options = {}) {
  return request({
    url: '/api/auth/me',
    method: 'get',
    silent: options.silent,
    headers: options.silent ? { 'X-Silent': '1' } : undefined
  })
}

/**
 * 用户登出
 */
export function logout() {
  return request({
    url: '/api/auth/logout',
    method: 'post'
  })
}

/**
 * 更新用户语言偏好
 * @param {string} preferred_language - 语言代码
 */
export function updateLanguage(preferred_language) {
  return request({
    url: '/api/auth/me/language',
    method: 'patch',
    data: { preferred_language }
  })
}

/**
 * 更新用户自动播客设置
 * @param {boolean} auto_podcast_enabled - 是否启用自动播客
 */
export function updateAutoPodcast(auto_podcast_enabled) {
  return request({
    url: '/api/auth/me/auto-podcast',
    method: 'patch',
    data: { auto_podcast_enabled }
  })
}

/**
 * 更新用户 TTS 音色偏好
 * @param {Object} data - { tts_voice_zh?: string|null, tts_voice_en?: string|null }
 *   只传要修改的字段；值为 null 表示恢复系统默认
 */
export function updateTtsVoices(data) {
  return request({
    url: '/api/auth/me/tts-voices',
    method: 'patch',
    data
  })
}

/**
 * 删除账号（GDPR）
 * @param {string} password - 密码确认
 */
export function deleteAccount(password) {
  return request({
    url: '/api/auth/account',
    method: 'delete',
    data: { password }
  })
}

/**
 * Google OAuth login
 * @param {string} idToken - Google ID token from GSI
 */
export function googleLogin(idToken) {
  return request({
    url: '/api/auth/google',
    method: 'post',
    data: { id_token: idToken }
  })
}

/**
 * Get Google OAuth client ID (public)
 */
export function getGoogleClientId() {
  return request({
    url: '/api/auth/google/client-id',
    method: 'get',
    silent: true,
    headers: { 'X-Silent': '1' }
  })
}
