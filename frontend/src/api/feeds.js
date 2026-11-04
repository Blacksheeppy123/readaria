import request from './request'
import { useUserStore } from '@/stores/userStore'

function getUserIdFromToken() {
  const token = localStorage.getItem('readaria_token')
  if (!token) return null

  try {
    const base64 = token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')
    const json = decodeURIComponent(atob(base64).split('').map(c => '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2)).join(''))
    const payload = JSON.parse(json)
    return payload?.sub || null
  } catch (_) {
    return null
  }
}

// 获取当前用户ID（优先以 JWT sub 为准，避免切账号瞬间读到旧的 Pinia/localStorage 用户对象）
function getCurrentUserId() {
  const tokenUserId = getUserIdFromToken()

  try {
    const store = useUserStore()
    if (store?.user?.id) {
      if (!tokenUserId || store.user.id === tokenUserId) return store.user.id
      console.warn('[getCurrentUserId] Pinia user.id 与 JWT sub 不一致，使用 JWT sub')
      return tokenUserId
    }
  } catch (_) {}

  const userStr = localStorage.getItem('readaria_user')
  if (userStr) {
    try {
      const user = JSON.parse(userStr)
      if (!tokenUserId || user.id === tokenUserId) return user.id
      console.warn('[getCurrentUserId] localStorage user.id 与 JWT sub 不一致，使用 JWT sub')
      return tokenUserId
    } catch (e) {
      console.error('解析用户信息失败:', e)
    }
  }

  if (tokenUserId) return tokenUserId

  console.warn('[getCurrentUserId] 未能获取用户 ID')
  return null
}

// 获取用户订阅列表
export function getUserFeeds() {
  return request({
    url: `/user/${getCurrentUserId()}/feeds`,
    method: 'get',
    silent: true,
    headers: { 'X-Silent': '1' }
  })
}

// 添加订阅
export function addFeed(data, options = {}) {
  const silent = !!options.silent
  return request({
    url: `/user/${getCurrentUserId()}/feeds`,
    method: 'post',
    data,
    silent,
    headers: silent ? { 'X-Silent': '1' } : undefined
  })
}

// 删除订阅
export function deleteFeed(feedId) {
  return request({
    url: `/user/${getCurrentUserId()}/feeds/${feedId}`,
    method: 'delete'
  })
}

// 更新订阅
export function updateFeed(feedId, data) {
  return request({
    url: `/user/${getCurrentUserId()}/feeds/${feedId}`,
    method: 'put',
    data
  })
}

// 刷新订阅（单个或多个）
export function refreshFeed(feedId, asyncMode = false) {
  const asyncQuery = asyncMode ? '?async_mode=true' : ''
  return request({
    url: `/api/user/${getCurrentUserId()}/feeds/refresh${asyncQuery}`,
    method: 'post',
    data: [feedId]
  })
}

// 刷新所有订阅
export function refreshAllFeeds(asyncMode = false) {
  const asyncQuery = asyncMode ? '?async_mode=true' : ''
  return request({
    url: `/api/user/${getCurrentUserId()}/feeds/refresh${asyncQuery}`,
    method: 'post'
  })
}

// 获取最近的刷新状态
export function getRefreshStatus() {
  return request({
    url: `/api/user/${getCurrentUserId()}/feeds/refresh/status`,
    method: 'get',
    // 静默错误，避免 404 或超时弹Toast
    silent: true,
    headers: { 'X-Silent': '1' }
  })
}

// 测试RSS URL
export function testFeedUrl(feedUrl) {
  return request({
    url: '/api/feeds/test',
    method: 'post',
    data: { feed_url: feedUrl }
  })
}

// 获取文章列表
export function getArticles(params, options = {}) {
  const silent = options.silent !== false
  return request({
    url: `/api/user/${getCurrentUserId()}/feeds/articles`,
    method: 'get',
    params,
    silent,
    preserveEnvelope: !!options.preserveEnvelope,
    headers: silent ? { 'X-Silent': '1' } : undefined
  })
}

// 搜索文章
export function searchArticles(query, size = 50) {
  return request({
    url: '/articles/search',
    method: 'get',
    params: { query, size }
  })
}

// 根据URL获取文章详情
export function getArticleByUrl(url) {
  return request({
    url: '/api/articles/by-url',
    method: 'get',
    params: { url }
  })
}

// 收藏相关
export function getSavedArticles(params = {}) {
  return request({
    url: '/api/saved',
    method: 'get',
    params
  })
}

export function isArticleSaved(url) {
  return request({
    url: '/api/saved/status',
    method: 'get',
    params: { url },
    // 静默错误，避免无数据时报错提示
    silent: true,
    headers: { 'X-Silent': '1' }
  })
}

export function saveArticleByUrl(url) {
  return request({
    url: '/api/saved',
    method: 'post',
    data: { url }
  })
}

export function unsaveArticleByUrl(url) {
  return request({
    url: '/api/saved',
    method: 'delete',
    params: { url }
  })
}

// 阅读状态
export function markReadByUrl(url) {
  return request({
    url: '/api/articles/read',
    method: 'post',
    data: { url },
    silent: true,
    headers: { 'X-Silent': '1' }
  })
}

export function markUnreadByUrl(url) {
  return request({
    url: '/api/articles/read',
    method: 'delete',
    params: { url }
  })
}

// OPML Export - returns blob URL for download
export function exportOpml() {
  return request({
    url: `/api/user/${getCurrentUserId()}/feeds/opml/export`,
    method: 'get',
    responseType: 'blob'
  })
}

// OPML Import - upload OPML file
export function importOpml(file) {
  const formData = new FormData()
  formData.append('file', file)
  return request({
    url: `/api/user/${getCurrentUserId()}/feeds/opml/import`,
    method: 'post',
    data: formData,
    headers: { 'Content-Type': 'multipart/form-data' }
  })
}
