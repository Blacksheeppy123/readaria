import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { useUserStore } from '@/stores/userStore'

const STORAGE_KEY = 'onboarding_state'
const COMPLETED_KEY = 'onboarding_completed'
const EXPERIENCE_PODCAST_REQUESTED_AT_KEY = 'onboarding_experience_podcast_requested_at'
const EXPERIENCE_PODCAST_REQUESTED_USER_ID_KEY = 'onboarding_experience_podcast_requested_user_id'
// 窗口放宽至 2 分钟，覆盖 addFeed × 4 同步链接全局文章的耗时（最坏可达 30+s）
const EXPERIENCE_PODCAST_REQUEST_WINDOW_MS = 120000

export const useOnboardingStore = defineStore('onboarding', () => {
  // === State ===
  const VALID_STATES = ['language_pending', 'path_pending', 'starter_pack_selected', 'manual_selected', 'onboarding_complete']
  const savedState = localStorage.getItem(STORAGE_KEY)
  // 旧版付费墙等未知状态统一回到语言选择，保证升级后可继续 onboarding。
  const state = ref(VALID_STATES.includes(savedState) ? savedState : 'language_pending')
  const completed = ref((() => {
    try {
      const raw = localStorage.getItem(COMPLETED_KEY)
      return raw ? JSON.parse(raw) : {}
    } catch {
      return {}
    }
  })())

  // === Computed ===
  const isLanguagePending = computed(() => state.value === 'language_pending')
  const isPathPending = computed(() => state.value === 'path_pending')
  const isOnboardingComplete = computed(() => state.value === 'onboarding_complete')
  const isManualSelected = computed(() => state.value === 'manual_selected')
  const needsOnboarding = computed(() => !isOnboardingComplete.value)

  // 记录 experience podcast 请求时间，用于 FeedView 竞态控制
  // 持久化到 localStorage，避免在 onboarding 跨页面/刷新时丢失（addFeed 同步链接可能耗时 ~30s）
  // 同时绑定 userId，避免跨账号在同一浏览器内误命中 starter-pack 兜底轮询
  const experiencePodcastRequestedAt = ref(null)
  const experiencePodcastRequestedUserId = ref(null)
  // 显式定时器：computed 不依赖 Date.now()（非响应式），靠 setTimeout 把 ref 置 null 触发 reactivity
  // 这样 FeedView keep-alive 缓存不会让 marker 永远停留在 true
  let experiencePodcastExpiryTimerId = null

  const scheduleExperiencePodcastExpiry = (ts) => {
    if (experiencePodcastExpiryTimerId) {
      clearTimeout(experiencePodcastExpiryTimerId)
      experiencePodcastExpiryTimerId = null
    }
    if (!ts) return
    // clamp 到 0 而非走同步清理路径，避免 TDZ（clearExperiencePodcastRequested 在下方声明）；
    // setTimeout 回调里读取的引用会在 store 初始化结束后解析，安全。
    const remaining = Math.max(0, EXPERIENCE_PODCAST_REQUEST_WINDOW_MS - (Date.now() - ts))
    experiencePodcastExpiryTimerId = setTimeout(() => {
      experiencePodcastExpiryTimerId = null
      clearExperiencePodcastRequested()
    }, remaining)
  }

  const loadExperiencePodcastMarker = () => {
    try {
      const rawTs = localStorage.getItem(EXPERIENCE_PODCAST_REQUESTED_AT_KEY)
      const ts = rawTs ? Number(rawTs) : null
      if (!ts || Number.isNaN(ts)) {
        localStorage.removeItem(EXPERIENCE_PODCAST_REQUESTED_AT_KEY)
        localStorage.removeItem(EXPERIENCE_PODCAST_REQUESTED_USER_ID_KEY)
        return
      }
      // 过期的时间戳直接丢弃，避免误命中竞态守卫
      if (Date.now() - ts >= EXPERIENCE_PODCAST_REQUEST_WINDOW_MS) {
        localStorage.removeItem(EXPERIENCE_PODCAST_REQUESTED_AT_KEY)
        localStorage.removeItem(EXPERIENCE_PODCAST_REQUESTED_USER_ID_KEY)
        return
      }
      experiencePodcastRequestedAt.value = ts
      const rawUid = localStorage.getItem(EXPERIENCE_PODCAST_REQUESTED_USER_ID_KEY)
      experiencePodcastRequestedUserId.value = rawUid || null
      // 恢复后立即按剩余时间排定到期清理，跨刷新场景下窗口仍然真实生效
      scheduleExperiencePodcastExpiry(ts)
    } catch {
      experiencePodcastRequestedAt.value = null
      experiencePodcastRequestedUserId.value = null
    }
  }

  loadExperiencePodcastMarker()

  const isExperiencePodcastRecentlyRequested = computed(() => {
    if (!experiencePodcastRequestedAt.value) return false
    if (Date.now() - experiencePodcastRequestedAt.value >= EXPERIENCE_PODCAST_REQUEST_WINDOW_MS) return false
    // 跨账号防护：marker 带 userId 时，只允许当前登录用户命中
    if (experiencePodcastRequestedUserId.value) {
      const userStore = useUserStore()
      const currentUserId = userStore.user?.id != null ? String(userStore.user.id) : null
      if (!currentUserId || currentUserId !== String(experiencePodcastRequestedUserId.value)) {
        return false
      }
    }
    return true
  })

  // === Actions ===
  const setState = (newState) => {
    state.value = newState
    try {
      localStorage.setItem(STORAGE_KEY, newState)
    } catch {
      // Storage may be unavailable in private mode
    }
  }

  const markLanguageSelected = () => {
    completed.value = { ...completed.value, language_selected: true }
    try {
      localStorage.setItem(COMPLETED_KEY, JSON.stringify(completed.value))
    } catch {
      // Storage may be unavailable in private mode
    }
    setState('path_pending')
  }

  const markPathSelected = (path) => {
    completed.value = { ...completed.value, path_selected: true, selected_path: path }
    try {
      localStorage.setItem(COMPLETED_KEY, JSON.stringify(completed.value))
    } catch {
      // Storage may be unavailable in private mode
    }
    setState(path === 'starter_pack' ? 'starter_pack_selected' : 'manual_selected')
  }

  const markFirstAudioPlayed = () => {
    completed.value = { ...completed.value, first_audio_played: true }
    try {
      localStorage.setItem(COMPLETED_KEY, JSON.stringify(completed.value))
    } catch {
      // Storage may be unavailable in private mode
    }
    setState('onboarding_complete')
  }

  const markExperiencePodcastRequested = (userId = null) => {
    const now = Date.now()
    experiencePodcastRequestedAt.value = now
    const uid = userId != null ? String(userId) : null
    experiencePodcastRequestedUserId.value = uid
    try {
      localStorage.setItem(EXPERIENCE_PODCAST_REQUESTED_AT_KEY, String(now))
      if (uid) {
        localStorage.setItem(EXPERIENCE_PODCAST_REQUESTED_USER_ID_KEY, uid)
      } else {
        localStorage.removeItem(EXPERIENCE_PODCAST_REQUESTED_USER_ID_KEY)
      }
    } catch {
      // Storage may be unavailable in private mode
    }
    // 重新排定到期清理，确保 120s 窗口结束时 ref→null 触发 reactivity
    scheduleExperiencePodcastExpiry(now)
  }

  const clearExperiencePodcastRequested = () => {
    if (experiencePodcastExpiryTimerId) {
      clearTimeout(experiencePodcastExpiryTimerId)
      experiencePodcastExpiryTimerId = null
    }
    experiencePodcastRequestedAt.value = null
    experiencePodcastRequestedUserId.value = null
    try {
      localStorage.removeItem(EXPERIENCE_PODCAST_REQUESTED_AT_KEY)
      localStorage.removeItem(EXPERIENCE_PODCAST_REQUESTED_USER_ID_KEY)
    } catch {
      // Storage may be unavailable in private mode
    }
  }

  const reset = () => {
    state.value = 'language_pending'
    completed.value = {}
    localStorage.removeItem(STORAGE_KEY)
    localStorage.removeItem(COMPLETED_KEY)
    clearExperiencePodcastRequested()
  }

  return {
    state,
    completed,
    isLanguagePending,
    isPathPending,
    isOnboardingComplete,
    isManualSelected,
    needsOnboarding,
    experiencePodcastRequestedAt,
    experiencePodcastRequestedUserId,
    isExperiencePodcastRecentlyRequested,
    setState,
    markLanguageSelected,
    markPathSelected,
    markFirstAudioPlayed,
    markExperiencePodcastRequested,
    clearExperiencePodcastRequested,
    reset
  }
})
