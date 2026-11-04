const SESSION_STORAGE_KEYS = [
  'articles_filter',
  'articles_sort',
  'read_urls_cache',
  'last_read_url'
]

const SESSION_STORAGE_PREFIXES = [
  'article_',
  'tts_audio_'
]

const LOCAL_STORAGE_PREFIXES = [
  'readaria_feed_articles_cache_',
  'readaria_feeds_cache_'
]

const LOCAL_STORAGE_KEYS = [
  'listen_queue',
  'listen_queue_meta',
  'podcast_progress',
  'tts_progress',
  'tts_last_article',
  'tts_playlist',
  'tts_current_index'
]

function clearSessionStorage() {
  for (const key of SESSION_STORAGE_KEYS) {
    sessionStorage.removeItem(key)
  }

  const keys = Object.keys(sessionStorage)
  for (const key of keys) {
    if (SESSION_STORAGE_PREFIXES.some(prefix => key.startsWith(prefix))) {
      sessionStorage.removeItem(key)
    }
  }
}

function clearLocalStorage() {
  for (const key of LOCAL_STORAGE_KEYS) {
    localStorage.removeItem(key)
  }

  const keys = Object.keys(localStorage)
  for (const key of keys) {
    if (LOCAL_STORAGE_PREFIXES.some(prefix => key.startsWith(prefix))) {
      localStorage.removeItem(key)
    }
  }
}

async function clearRuntimeCaches() {
  if (typeof caches === 'undefined') return

  const cacheNames = await caches.keys()
  await Promise.all(
    cacheNames
      .filter(name => ['api-cache', 'articles-cache'].includes(name))
      .map(name => caches.delete(name))
  )
}

export async function resetAuthSessionState() {
  if (typeof window !== 'undefined') {
    delete window.__firstAudioPlayedEmitted
  }

  // 清理音频缓存
  try {
    const { clearAllAudioCache } = await import('@/api/tts')
    clearAllAudioCache()
  } catch (error) {
    console.warn('[AuthSessionReset] Failed to clear audio cache:', error)
  }

  // 逐个导入并重置 store，避免一个失败影响其他
  try {
    const { useFeedStore } = await import('@/stores/feedStore')
    const feedStore = useFeedStore()
    if (typeof feedStore.resetState === 'function') {
      // Invalidate in-flight requests before clearing account-scoped data.
      // Pinia's generic $reset() cannot clear runtime Promise handles.
      feedStore.resetState()
    } else if (typeof feedStore.$reset === 'function') {
      feedStore.$reset()
    }
  } catch (error) {
    console.warn('[AuthSessionReset] Failed to reset feedStore:', error)
  }

  try {
    const { useArticleStore } = await import('@/stores/articleStore')
    const articleStore = useArticleStore()
    if (typeof articleStore.$reset === 'function') {
      articleStore.$reset()
    } else {
      articleStore.clear?.()
    }
  } catch (error) {
    console.warn('[AuthSessionReset] Failed to reset articleStore:', error)
  }

  // Desktop article state is account-scoped too. Clear it on logout/login so a
  // newly authenticated user never reuses the previous user's in-memory list.
  try {
    const { useDesktopArticleStore } = await import('@/stores/desktopArticleStore')
    const desktopArticleStore = useDesktopArticleStore()
    if (typeof desktopArticleStore.reset === 'function') {
      desktopArticleStore.reset?.()
    } else if (typeof desktopArticleStore.$reset === 'function') {
      desktopArticleStore.$reset()
    }
  } catch (error) {
    console.warn('[AuthSessionReset] Failed to reset desktopArticleStore:', error)
  }

  try {
    const { useQueueStore } = await import('@/stores/queueStore')
    // 登出只做本地重置（不访问服务端）：此刻 token 已失效，clearQueue 的服务端删除必然失败，
    // 且会留下 dirty/墓碑元数据，污染下次登录（可能是其他账号）的合并结果
    useQueueStore().resetLocal()
  } catch (error) {
    console.warn('[AuthSessionReset] Failed to reset queueStore:', error)
  }

  try {
    const { usePlayerStore } = await import('@/stores/playerStore')
    usePlayerStore().clearAllData()
  } catch (error) {
    console.warn('[AuthSessionReset] Failed to reset playerStore:', error)
  }

  try {
    const { usePodcastStore } = await import('@/stores/podcastStore')
    usePodcastStore().clearAll()
  } catch (error) {
    console.warn('[AuthSessionReset] Failed to reset podcastStore:', error)
  }

  try {
    const { useConversationStore } = await import('@/stores/conversationStore')
    useConversationStore().clearMessages()
  } catch (error) {
    console.warn('[AuthSessionReset] Failed to reset conversationStore:', error)
  }

  try {
    const { usePodcastPlayerStore } = await import('@/stores/podcastPlayerStore')
    const podcastPlayerStore = usePodcastPlayerStore()
    podcastPlayerStore.stop({ persistProgress: false })
    podcastPlayerStore.clearAnalyticsDedupe?.()
  } catch (error) {
    console.warn('[AuthSessionReset] Failed to reset podcastPlayerStore:', error)
  }

  // Note: onboarding state is intentionally NOT reset here.
  // It is preserved across logout/login for the same user.
  // Cross-user cleanup is handled in userStore.setUser().

  await clearRuntimeCaches()
  clearSessionStorage()
  clearLocalStorage()
}
