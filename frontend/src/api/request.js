import axios from 'axios'
import { showToast } from 'vant'
import i18n from '@/i18n'

// 获取 API 基础 URL
// 生产环境使用环境变量，开发环境使用空字符串（让 Vite 代理处理）
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || ''

console.log('[API Config] Base URL:', API_BASE_URL)

// 创建axios实例
const request = axios.create({
  baseURL: API_BASE_URL,
  timeout: 180000  // 3分钟超时，适配播客生成等长时间操作
})

// 请求拦截器
request.interceptors.request.use(
  config => {
    // 从localStorage获取token并添加到请求头
    const token = localStorage.getItem('readaria_token')
    if (token) {
      config.headers['Authorization'] = `Bearer ${token}`
    }
    // 调试日志：记录 API 请求详情（生产环境自动过滤）
    if (import.meta.env.DEV || import.meta.env.VITE_DEBUG_API === 'true') {
      console.log(`[API] ${config.method?.toUpperCase()} ${config.baseURL || ''}${config.url}`)
    }
    return config
  },
  error => {
    console.error('Request error:', error)
    return Promise.reject(error)
  }
)

// 响应拦截器
request.interceptors.response.use(
  response => {
    // 如果后端返回了包装格式 {status, data/feeds/articles/results/...}
    const data = response.data
    if (response.config?.preserveEnvelope) {
      return data
    }
    if (data.status === 'success') {
      // 返回实际数据（feeds、articles、results等）
      return data.feeds || data.articles || data.results || data.data || data
    }
    return data
  },
  error => {
    const cfg = error.config || {}
    const silent = cfg.silent || (cfg.headers && (cfg.headers['X-Silent'] || cfg.headers['x-silent']))
    if (!silent) {
      console.error('Response error:', error)
      // 调试日志：记录错误响应详情
      if (import.meta.env.DEV || import.meta.env.VITE_DEBUG_API === 'true') {
        console.error(`[API Error] ${cfg.method?.toUpperCase()} ${cfg.baseURL || ''}${cfg.url} → ${error.response?.status} ${error.response?.statusText}`)
      }
    }

    let message = i18n.global.t('common.requestFailed')
    if (error.response) {
      switch (error.response.status) {
        case 401:
          message = i18n.global.t('common.unauthorized')
          try {
            // 清理本地登录状态并跳转到登录页
            localStorage.removeItem('readaria_token')
            localStorage.removeItem('readaria_user')
            const redirect = encodeURIComponent(window.location.pathname + window.location.search)
            // 避免在登录页重复跳转
            if (!window.location.pathname.startsWith('/login')) {
              window.location.href = `/login?redirect=${redirect}`
            }
          } catch (_) {
            // ignore
          }
          break
        case 403:
          message = i18n.global.t('common.accessDenied')
          break
        case 404:
          message = i18n.global.t('common.resourceNotFound')
          break
        case 500:
          message = i18n.global.t('common.serverError')
          break
        default:
          message = error.response.data?.message || i18n.global.t('common.requestFailed')
      }
    } else if (error.request) {
      message = i18n.global.t('common.networkError')
    }

    if (!silent) showToast(message)
    return Promise.reject(error)
  }
)

export default request
