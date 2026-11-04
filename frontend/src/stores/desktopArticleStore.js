import { defineStore } from 'pinia'
import { getArticles } from '@/api/feeds'

export const useDesktopArticleStore = defineStore('desktopArticle', {
  state: () => ({
    articles: [],
    seenUrls: new Set(),
    selectedFeedId: null, // null = 全部来源
    sortField: 'updated_at',
    sortDirection: 'desc',
    page: 1,
    pageSize: 20,
    finished: false,
    loading: false,
    error: null,
    selectedUrl: null,
    requestGeneration: 0
  }),

  getters: {
    selectedIndex: (state) =>
      state.articles.findIndex((a) => a.url === state.selectedUrl)
  },

  actions: {
    async loadMore() {
      if (this.finished) return
      // 并发去重：滚动触底与筛选切换同时触发时复用在途请求
      if (this._inflight) return this._inflight
      this.loading = true
      this.error = null
      const gen = this.requestGeneration
      const request = (async () => {
        try {
          const params = {
            page: this.page,
            size: this.pageSize,
            order_by: this.sortField,
            sort: this.sortDirection
          }
          if (this.selectedFeedId) params.feed_id = this.selectedFeedId
          const response = await getArticles(params, { preserveEnvelope: true })
          if (gen !== this.requestGeneration) return // 已过期，丢弃
          const items = Array.isArray(response?.articles) ? response.articles : []
          const fresh = items.filter((a) => {
            if (!a?.url || this.seenUrls.has(a.url)) return false
            this.seenUrls.add(a.url)
            return true
          })
          if (fresh.length === 0) {
            this.finished = true
          } else {
            this.articles.push(...fresh)
            if (fresh.length >= this.pageSize) this.page++
            else this.finished = true
          }
        } catch (e) {
          if (gen === this.requestGeneration) {
            this.error = e?.message || 'load failed'
            this.finished = true
          }
          throw e
        } finally {
          if (gen === this.requestGeneration) this.loading = false
          if (this._inflight === request) this._inflight = null
        }
      })()
      this._inflight = request
      try {
        await request
      } finally {
        if (this._inflight === request) this._inflight = null
      }
    },

    async refresh() {
      this.requestGeneration++ // 旧请求结果将被 generation 守卫丢弃
      // 等待在途请求结束，避免旧请求未清 loading 导致新筛选永远发不出请求
      if (this._inflight) {
        try { await this._inflight } catch (_) {}
      }
      this.articles = []
      this.seenUrls = new Set()
      this.page = 1
      this.finished = false
      this.error = null
      await this.loadMore()
    },

    async selectFeed(feedId) {
      if (this.selectedFeedId === feedId) return
      this.selectedFeedId = feedId
      await this.refresh()
    },

    async setSort(field) {
      this.sortField = field
      this.sortDirection = 'desc'
      await this.refresh()
    },

    setSelected(url) {
      this.selectedUrl = url
    },

    markLocalRead(url) {
      const item = this.articles.find((a) => a.url === url)
      if (item) item.is_read = true
    },

    reset() {
      this.requestGeneration++
      // Do not let a request from the previous account block the next user's
      // first load. The stale request is invalidated by requestGeneration.
      this._inflight = null
      this.articles = []
      this.seenUrls = new Set()
      this.selectedFeedId = null
      this.sortField = 'updated_at'
      this.sortDirection = 'desc'
      this.page = 1
      this.finished = false
      this.loading = false
      this.error = null
      this.selectedUrl = null
    }
  }
})
