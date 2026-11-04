import { defineStore } from 'pinia'

export const useArticleStore = defineStore('article', {
  state: () => ({
    current: null
  }),
  actions: {
    setCurrent(article) {
      this.current = article
    },
    clear() {
      this.current = null
    }
  }
})

