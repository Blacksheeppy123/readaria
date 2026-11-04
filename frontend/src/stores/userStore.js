import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import posthog from 'posthog-js'
import { getCurrentUser } from '@/api/auth'
import { identifyUser, applySessionRecordingSampling, resetSessionRecordingSampling } from '@/utils/analytics'
import { frontendLogCollector } from '@/utils/frontendLogCollector'
import { resetAuthSessionState } from '@/utils/authSessionReset'

export const useUserStore = defineStore('user', () => {
  // State
  const user = ref(null)
  const token = ref(null)
  const isLoggedIn = computed(() => !!token.value && !!user.value)

  const isDebugUser = computed(() => {
    return !!user.value?.is_frontend_log_whitelist_user
  })

  // 从localStorage初始化
  const initFromStorage = () => {
    const savedToken = localStorage.getItem('readaria_token')
    const savedUser = localStorage.getItem('readaria_user')

    if (savedToken && savedUser) {
      try {
        token.value = savedToken
        user.value = JSON.parse(savedUser)
        console.log('从localStorage恢复用户状态:', user.value.username)

        // PostHog 识别用户（页面刷新后恢复登录态）
        identifyUser(user.value)
        applySessionRecordingSampling(user.value)

        // 如果是白名单用户，启动前端日志收集器
        if (isDebugUser.value) {
          console.log('[UserStore] Debug user detected on init - starting log collector')
          frontendLogCollector.start()
        }

        // 刷新服务端派生能力，避免白名单等开关变更后必须手动重新登录。
        setTimeout(() => {
          refreshUser({ silent: true }).catch(() => {})
        }, 0)
      } catch (e) {
        console.error('恢复用户状态失败:', e)
        void clearUser()
      }
    }
  }

  // 设置用户信息和token
  const setUser = async (userData, accessToken) => {
    const wasDebugUser = !!user.value?.is_frontend_log_whitelist_user
    const willBeDebugUser = !!userData?.is_frontend_log_whitelist_user

    if (wasDebugUser && !willBeDebugUser) {
      frontendLogCollector.stop()
    }

    await resetAuthSessionState()

    // 跨用户登录时清除 onboarding 状态，避免账号 A 的进度泄漏给账号 B
    // Fallback chain: last_user_id → readaria_user (localStorage) → user.value (Pinia)
    // Handles migration from pre-deployment sessions where last_user_id didn't exist yet.
    let previousUserId = localStorage.getItem('last_user_id')
    if (!previousUserId) {
      try {
        const savedUser = JSON.parse(localStorage.getItem('readaria_user') || '{}')
        previousUserId = savedUser.id || savedUser.username || user.value?.id || user.value?.username
      } catch {
        previousUserId = user.value?.id || user.value?.username
      }
    }
    const newUserId = userData.id || userData.username
    if (previousUserId && previousUserId !== String(newUserId)) {
      localStorage.removeItem('onboarding_state')
      localStorage.removeItem('onboarding_completed')
      try {
        const { useOnboardingStore } = await import('@/stores/onboardingStore')
        useOnboardingStore().reset()
      } catch (error) {
        console.warn('[UserStore] Failed to reset onboardingStore:', error)
      }
    }
    localStorage.setItem('last_user_id', String(newUserId))

    user.value = userData
    token.value = accessToken

    // 保存到localStorage
    localStorage.setItem('readaria_token', accessToken)
    localStorage.setItem('readaria_user', JSON.stringify(userData))

    console.log('用户登录成功:', userData.username)

    // PostHog 识别用户
    identifyUser(userData)
    // 新登录态：重新决定 Session Replay 采样（免费 10% / 付费 100%）
    resetSessionRecordingSampling()
    applySessionRecordingSampling(userData)

    // 如果是白名单用户，启动前端日志收集器
    if (willBeDebugUser) {
      console.log('[UserStore] Debug user detected - starting log collector')
      frontendLogCollector.start()
    }
  }

  // 清除用户信息
  const clearUser = async () => {
    // 保留 outgoing user id，供下次登录时做跨用户 onboarding 清理
    const outgoingUserId = user.value?.id || user.value?.username
    if (outgoingUserId && !localStorage.getItem('last_user_id')) {
      localStorage.setItem('last_user_id', String(outgoingUserId))
    }

    user.value = null
    token.value = null

    // 清除localStorage（保留 onboarding 状态，让同一用户重新登录时保持进度）
    localStorage.removeItem('readaria_token')
    localStorage.removeItem('readaria_user')

    console.log('用户已登出')

    // PostHog 清除用户身份
    posthog.reset()
    resetSessionRecordingSampling()

    // 停止前端日志收集器
    frontendLogCollector.stop()

    await resetAuthSessionState()
  }

  // 刷新用户信息（从服务器获取最新数据）
  const refreshUser = async (options = {}) => {
    if (!token.value) {
      console.log('未登录，无法刷新用户信息')
      return false
    }

    try {
      const userData = await getCurrentUser({ silent: options.silent })
      const wasDebugUser = !!user.value?.is_frontend_log_whitelist_user
      const willBeDebugUser = !!userData?.is_frontend_log_whitelist_user
      user.value = userData
      localStorage.setItem('readaria_user', JSON.stringify(userData))
      if (!wasDebugUser && willBeDebugUser) {
        console.log('[UserStore] Debug access granted on refresh - starting log collector')
        frontendLogCollector.start()
      } else if (wasDebugUser && !willBeDebugUser) {
        frontendLogCollector.stop()
      }
      console.log('用户信息已刷新')
      return true
    } catch (error) {
      console.error('刷新用户信息失败:', error)
      // 如果token无效，清除用户状态
      if (error.response?.status === 401) {
        await clearUser()
      }
      return false
    }
  }

  // 检查token是否有效
  const checkAuth = async () => {
    if (!token.value) {
      return false
    }

    try {
      await getCurrentUser()
      return true
    } catch (error) {
      console.error('Token验证失败:', error)
      await clearUser()
      return false
    }
  }

  // 登出
  const logout = async () => {
    await clearUser()
  }

  return {
    // State
    user,
    token,
    isLoggedIn,
    isDebugUser,

    // Actions
    initFromStorage,
    setUser,
    clearUser,
    refreshUser,
    checkAuth,
    logout
  }
})
