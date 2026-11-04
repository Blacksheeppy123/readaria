import { defineStore } from 'pinia'
import { getUserFeeds, addFeed, deleteFeed, refreshFeed, refreshAllFeeds, getRefreshStatus } from '@/api/feeds'

// 订阅列表前端缓存TTL（毫秒），支持通过 Vite 环境变量覆盖
// 默认 10 分钟：600_000 ms
const USER_FEEDS_CACHE_TTL_MS = Number(import.meta.env.VITE_USER_FEEDS_CACHE_TTL_MS || 600000)

function getStoredUserId() {
  try {
    const savedUser = localStorage.getItem('readaria_user')
    if (!savedUser) return null
    return JSON.parse(savedUser)?.id || null
  } catch (_) {
    return null
  }
}

function getFeedsCacheKey(userId) {
  return userId ? `readaria_feeds_cache_${userId}` : 'readaria_feeds_cache'
}

function loadFeedsFromCache(userId) {
  try {
    const cached = localStorage.getItem(getFeedsCacheKey(userId))
    if (cached) {
      return JSON.parse(cached)
    }
  } catch (_) {}
  return null
}

function saveFeedsToCache(userId, feeds) {
  try {
    localStorage.setItem(getFeedsCacheKey(userId), JSON.stringify(feeds))
  } catch (_) {}
}

function clearFeedsCache(userId) {
  try {
    localStorage.removeItem(getFeedsCacheKey(userId))
  } catch (_) {}
}

export const useFeedStore = defineStore('feed', {
  state: () => ({
    feeds: [],
    loading: false,
    error: null,
    refreshStatus: {}, // { [feed_id]: { status, started_at, completed_at, ... } }
    lastFetchedAt: 0, // 上次从后端拉取订阅列表的时间戳（ms）
    lastFetchedUserId: null, // 当前缓存归属的用户 ID，避免切账号后复用旧数据
    // Monotonic generation invalidates requests across logout/login resets,
    // including a quick re-login as the same account.
    fetchGeneration: 0
  }),

  getters: {
    feedCount: (state) => state.feeds.length,
    activeFeed: (state) => state.feeds.filter(f => f.is_active !== false)
  },

  actions: {
    resetState() {
      this.fetchGeneration++
      this._fetchInflight = null
      this._fetchInflightUserId = null
      this.feeds = []
      this.loading = false
      this.error = null
      this.refreshStatus = {}
      this.lastFetchedAt = 0
      clearFeedsCache(this.lastFetchedUserId)
      this.lastFetchedUserId = null
    },

    /**
     * 获取订阅列表
     * @param {boolean} force 是否强制从后端刷新（忽略前端缓存）
     */
    async fetchFeeds(force = false) {
      const currentUserId = getStoredUserId()

      // DesktopShell and the active desktop view can mount together. Reuse a
      // request already fetching the same account instead of issuing duplicate
      // GETs. A force refresh must retain its semantics, so it waits for the
      // current request and then starts a fresh one.
      if (this._fetchInflight && this._fetchInflightUserId === currentUserId) {
        if (!force) return this._fetchInflight
        try { await this._fetchInflight } catch (_) {}
        if (getStoredUserId() !== currentUserId) return this.fetchFeeds(force)
        if (this._fetchInflight && this._fetchInflightUserId === currentUserId) {
          return this.fetchFeeds(true)
        }
      }

      if (this.lastFetchedUserId && this.lastFetchedUserId !== currentUserId) {
        this.feeds = []
        this.refreshStatus = {}
        this.lastFetchedAt = 0
      }

      // 在未强制刷新且内存缓存未过期的情况下，直接返回前端缓存
      const now = Date.now()
      if (
        !force &&
        this.feeds.length > 0 &&
        this.lastFetchedAt &&
        this.lastFetchedUserId === currentUserId &&
        now - this.lastFetchedAt < USER_FEEDS_CACHE_TTL_MS
      ) {
        return this.feeds
      }

      this.loading = true
      this.error = null
      const requestUserId = currentUserId
      const requestGeneration = this.fetchGeneration
      const request = (async () => {
        try {
          const data = await getUserFeeds()
          // A logout/login can happen while the request is in flight. Do not
          // let the previous account repopulate the shared store.
          if (
            getStoredUserId() !== requestUserId ||
            this.fetchGeneration !== requestGeneration
          ) return data
          this.feeds = data
          this.lastFetchedAt = Date.now()
          this.lastFetchedUserId = currentUserId
          saveFeedsToCache(currentUserId, data)
          return data
        } catch (error) {
          if (
            getStoredUserId() !== requestUserId ||
            this.fetchGeneration !== requestGeneration
          ) throw error
          this.error = error.message
          // 若请求失败且本地有缓存，返回缓存数据作为兜底（支持离线场景）
          const cached = loadFeedsFromCache(currentUserId)
          if (cached && cached.length > 0) {
            console.warn('[feedStore] fetchFeeds failed, falling back to localStorage cache')
            this.feeds = cached
            this.lastFetchedUserId = currentUserId
            // 不更新 lastFetchedAt，以便网络恢复后自动刷新
            return cached
          }
          throw error
        } finally {
          if (this._fetchInflight === request) {
            this._fetchInflight = null
            this._fetchInflightUserId = null
            this.loading = false
          }
        }
      })()
      this._fetchInflight = request
      this._fetchInflightUserId = requestUserId
      return request
    },
    // 获取刷新状态
    async fetchRefreshStatus() {
      try {
        const res = await getRefreshStatus()
        const map = {}
        const list = Array.isArray(res.results) ? res.results : res
        for (const item of list || []) {
          map[item.feed_id] = item
        }
        this.refreshStatus = map
        return map
      } catch (error) {
        // 404 说明后端路由未就绪，返回 null 便于调用方停止轮询
        if (error?.response?.status === 404) return null
        return {}
      }
    },

    // 添加订阅
    async createFeed(feedData) {
      try {
        const response = await addFeed(feedData)
        // 重新获取订阅列表以获得完整的 feed 对象
        await this.fetchFeeds(true)
        return response
      } catch (error) {
        throw error
      }
    },

    // 删除订阅
    async removeFeed(feedId) {
      try {
        await deleteFeed(feedId)
        this.feeds = this.feeds.filter(f => f.id !== feedId)
        this.lastFetchedAt = Date.now()
        saveFeedsToCache(this.lastFetchedUserId, this.feeds)
      } catch (error) {
        throw error
      }
    },

    // 刷新订阅
    async refreshFeed(feedId, asyncMode = false) {
      try {
        await refreshFeed(feedId, asyncMode)
      } catch (error) {
        throw error
      }
    },

    async refreshAll(asyncMode = false) {
      try {
        await refreshAllFeeds(asyncMode)
      } catch (error) {
        throw error
      }
    }
  }
})
