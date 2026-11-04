import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { showToast } from 'vant'
import i18n from '@/i18n'
import { getUserQueue, updateUserQueue } from '@/api/queue'
import {
  shouldAdoptServerState,
  isSnapshotStale,
  needsFollowUpSync,
  mergeDirtyQueueOnPull
} from '@/services/queue/queueSyncPolicy'

const LISTEN_QUEUE_KEY = 'listen_queue'
const LISTEN_QUEUE_META_KEY = 'listen_queue_meta'
const SYNC_DEBOUNCE_MS = 1000

/**
 * 序列化队列项，去掉 content 等运行时大字段
 */
const serializeQueueItems = (items) => items.map(a => ({
  id: a.id,
  url: a.url,
  title: a.title,
  summary: a.summary,
  source: a.source,
  author: a.author,
  published_at: a.published_at,
  updated_at: a.updated_at,
  cover: a.cover
}))

/**
 * 听读队列管理
 * 用户从 Feed 页主动添加的待听文章列表
 * 与 playerStore 的 playlist 分离：queue 是用户意图，playlist 是播放引擎状态
 *
 * 多端同步语义（2026-07-21 修复删除内容复活问题）：
 * - dirty 标记：本地有未同步的变更（增/删/排序/清空）时为 true
 * - 删除墓碑（tombstones）：记录本设备删除项的 URL，合并时删除优先于服务器快照
 * - 新增记录（addedUrls）：记录本设备新增项的 URL，合并时只有这些本地项会被追加；
 *   其余本地独有项一律视为过期副本丢弃——这是区分「本地新增」与「他端已删除」的关键
 * - 拉取时若本地无未同步变更，直接采用服务器状态（server wins）且不回写，
 *   避免过期本地副本把已删除内容并回服务器（docs/bugs/20260721-queue_sync_deleted_items_reappear.md）
 * - 所有服务端写入统一经 doSync 串行（syncInFlight + pendingSync），避免并发写相互覆盖
 *
 * 已知边界：多端同时处于 dirty 状态并发写入时，后到全量写可能覆盖先到写
 * （全量替换架构的固有边界）；如需彻底杜绝需后端引入 revision/CAS，见 bug 文档「可选后续」。
 */
export const useQueueStore = defineStore('queue', () => {
  const queue = ref([])
  const syncStatus = ref('idle') // 'idle' | 'syncing' | 'error'
  const lastSyncAt = ref(null)

  let syncTimer = null
  let syncInFlight = false
  let pendingSync = false

  // 同步元数据（持久化到 localStorage，用于区分「本地新增未上传」与「他端已删除」）
  let dirty = false
  let tombstones = {} // { [url]: deletedAtISO }
  let addedUrls = {} // { [url]: addedAtISO }
  let mutationSeq = 0 // 本地变更序号，用于拉取/回写期间的竞态防护
  let flushListenerAdded = false

  // 队列长度
  const length = computed(() => queue.value.length)

  // 队列是否为空
  const isEmpty = computed(() => queue.value.length === 0)

  /**
   * 判断是否具备同步条件：在线 + 已登录
   */
  const canSync = () => {
    if (typeof navigator !== 'undefined' && !navigator.onLine) return false
    if (typeof localStorage === 'undefined') return false
    return !!localStorage.getItem('readaria_token')
  }

  /**
   * 持久化同步元数据
   */
  const persistMeta = () => {
    try {
      localStorage.setItem(LISTEN_QUEUE_META_KEY, JSON.stringify({ dirty, tombstones, added: addedUrls }))
    } catch (e) {
      console.error('[QueueStore] Failed to persist queue meta:', e)
    }
  }

  /**
   * 恢复同步元数据
   */
  const restoreMeta = () => {
    try {
      const saved = localStorage.getItem(LISTEN_QUEUE_META_KEY)
      if (saved) {
        const meta = JSON.parse(saved)
        dirty = !!meta?.dirty
        tombstones = meta?.tombstones && typeof meta.tombstones === 'object' ? meta.tombstones : {}
        addedUrls = meta?.added && typeof meta.added === 'object' ? meta.added : {}
      }
    } catch (e) {
      console.error('[QueueStore] Failed to restore queue meta:', e)
    }
  }

  /**
   * 标记本地发生未同步变更
   */
  const markDirty = () => {
    dirty = true
    mutationSeq += 1
    persistMeta()
  }

  /**
   * 同步成功后清除元数据；若期间发生了新的本地变更则保留
   */
  const clearMetaIfUnchanged = (seq) => {
    if (seq === mutationSeq) {
      dirty = false
      tombstones = {}
      addedUrls = {}
      persistMeta()
    }
  }

  /**
   * 初始化：从 localStorage 恢复队列与同步元数据
   */
  const restore = () => {
    try {
      const saved = localStorage.getItem(LISTEN_QUEUE_KEY)
      if (saved) {
        queue.value = JSON.parse(saved)
      }
    } catch (e) {
      console.error('[QueueStore] Failed to restore queue:', e)
    }
    restoreMeta()
  }

  /**
   * 持久化队列到 localStorage
   */
  const persist = () => {
    try {
      localStorage.setItem(LISTEN_QUEUE_KEY, JSON.stringify(serializeQueueItems(queue.value)))
    } catch (e) {
      console.error('[QueueStore] Failed to persist queue:', e)
    }
  }

  /**
   * 立即执行同步到服务端（唯一的服务端写入口，经 syncInFlight 串行）
   */
  const doSync = async () => {
    if (!canSync() || syncInFlight) {
      if (syncInFlight) pendingSync = true
      return
    }

    syncInFlight = true
    syncStatus.value = 'syncing'
    // 请求开始前消费 pending；请求期间的新变更会重新置位 pendingSync / 递增 mutationSeq
    pendingSync = false
    const seq = mutationSeq
    try {
      await updateUserQueue(serializeQueueItems(queue.value))
      lastSyncAt.value = Date.now()
      syncStatus.value = 'idle'
      clearMetaIfUnchanged(seq)
    } catch (error) {
      console.error('[QueueStore] Failed to sync queue:', error)
      syncStatus.value = 'error'
    } finally {
      syncInFlight = false
      // 请求期间发生的变更必须补发，不能让它只停留在本地
      if (needsFollowUpSync(pendingSync, seq, mutationSeq)) {
        scheduleSync()
      }
    }
  }

  /**
   * 延迟同步：合并快速操作（拖拽排序等）
   */
  const scheduleSync = () => {
    persist()
    if (!canSync()) return

    pendingSync = true
    if (syncInFlight) return

    if (syncTimer) clearTimeout(syncTimer)
    syncTimer = setTimeout(() => {
      syncTimer = null
      doSync()
    }, SYNC_DEBOUNCE_MS)
  }

  /**
   * 从服务端拉取队列
   * - 本地无未同步变更（dirty=false 且拉取期间无变更）：直接采用服务器状态，不回写
   * - 拉取期间本地发生变更：快照已过期，丢弃后推当前本地状态
   * - 本地有未同步变更且快照未过期：服务器项过滤墓碑 + 本地新增（addedUrls）追加，
   *   合并结果经 doSync 串行回写，保证多端收敛
   */
  const syncFromServer = async () => {
    if (!canSync()) return

    syncStatus.value = 'syncing'
    try {
      // 拉取期间若本地发生变更，服务器快照即过期；
      // 墓碑快照与变更序号用于防止过期快照复活已删除内容
      const seqAtFetch = mutationSeq
      const tombstonesAtFetch = { ...tombstones }
      const server = await getUserQueue()
      const serverItems = server?.items || []

      if (shouldAdoptServerState(dirty, seqAtFetch, mutationSeq)) {
        // 本地无未同步变更：server wins，不做回写
        queue.value = serverItems
        persist()
        lastSyncAt.value = server?.updated_at ? Date.parse(server.updated_at) : Date.now()
        syncStatus.value = 'idle'
        return
      }

      if (isSnapshotStale(seqAtFetch, mutationSeq)) {
        // 拉取期间本地发生变更：快照过期，直接推当前本地状态（doSync 内部串行/补偿）
        await doSync()
        return
      }

      // 本地有未同步变更且快照未过期：合并（语义见 queueSyncPolicy）
      const merged = mergeDirtyQueueOnPull({
        serverItems,
        localItems: queue.value,
        tombstones: { ...tombstonesAtFetch, ...tombstones },
        addedUrls
      })

      queue.value = merged
      persist()

      // 回写合并结果（doSync 成功后按 mutationSeq 竞态安全地清除 dirty/墓碑/新增记录）
      await doSync()
    } catch (error) {
      console.error('[QueueStore] Failed to sync from server:', error)
      syncStatus.value = 'error'
    }
  }

  /**
   * 注册页面隐藏/关闭时的同步冲刷，降低防抖窗口内杀 App 丢同步的概率
   */
  const registerSyncFlush = () => {
    if (flushListenerAdded || typeof window === 'undefined') return
    flushListenerAdded = true
    const flush = () => {
      if (!dirty || !canSync() || syncInFlight) return
      if (syncTimer) {
        clearTimeout(syncTimer)
        syncTimer = null
      }
      doSync()
    }
    window.addEventListener('pagehide', flush)
    document.addEventListener('visibilitychange', () => {
      if (document.visibilityState === 'hidden') flush()
    })
  }

  /**
   * 应用启动后由 main.js 调用：恢复 + 服务端同步
   */
  const initSync = async () => {
    restore()
    registerSyncFlush()
    if (canSync()) {
      await syncFromServer()
    }
  }

  /**
   * 本地状态完全重置（登出场景）：不访问服务端，
   * 清理定时器、队列、同步元数据与全部 localStorage 键
   */
  const resetLocal = () => {
    if (syncTimer) {
      clearTimeout(syncTimer)
      syncTimer = null
    }
    mutationSeq += 1 // 使在途请求的元数据清理失效
    queue.value = []
    dirty = false
    tombstones = {}
    addedUrls = {}
    pendingSync = false
    syncStatus.value = 'idle'
    lastSyncAt.value = null
    persist()
    persistMeta()
  }

  /**
   * 检查文章是否已在队列中
   */
  const isInQueue = (article) => {
    if (!article?.url) return false
    return queue.value.some(a => a.url === article.url)
  }

  /**
   * 添加文章到队列
   */
  const addToQueue = (article) => {
    if (!article?.url) return

    if (isInQueue(article)) {
      const { t } = i18n.global
      showToast({ message: t('listen.alreadyInQueue'), icon: 'info', duration: 1500 })
      return
    }

    const now = new Date().toISOString()
    addedUrls[article.url] = now
    // 重新加入等于撤销一条未同步的删除
    if (tombstones[article.url]) {
      delete tombstones[article.url]
    }

    queue.value.push({
      id: article.id,
      url: article.url,
      title: article.title,
      summary: article.summary,
      content: article.content,
      source: article.source,
      author: article.author,
      published_at: article.published_at,
      updated_at: article.updated_at
    })

    markDirty()
    scheduleSync()

    const { t } = i18n.global
    showToast({ message: t('listen.addedToQueue'), icon: 'success', duration: 1500 })
  }

  /**
   * 从队列中移除
   */
  const removeFromQueue = (index) => {
    if (index < 0 || index >= queue.value.length) return
    const [removed] = queue.value.splice(index, 1)
    if (removed?.url) {
      tombstones[removed.url] = new Date().toISOString()
      // 先加后删且尚未同步：该项不在服务器上，无需保留新增记录
      delete addedUrls[removed.url]
    }
    markDirty()
    scheduleSync()
  }

  /**
   * 通过 URL 移除
   */
  const removeByUrl = (url) => {
    const index = queue.value.findIndex(a => a.url === url)
    if (index >= 0) {
      removeFromQueue(index)
    }
  }

  /**
   * 拖拽排序
   */
  const reorder = (fromIndex, toIndex) => {
    if (fromIndex === toIndex) return
    if (fromIndex < 0 || fromIndex >= queue.value.length) return
    if (toIndex < 0 || toIndex >= queue.value.length) return

    const item = queue.value.splice(fromIndex, 1)[0]
    queue.value.splice(toIndex, 0, item)
    markDirty()
    scheduleSync()
  }

  /**
   * 清空队列
   */
  const clearQueue = async () => {
    // 为全部现有项记录墓碑：若本次推送失败，下次拉取合并时删除仍然生效
    const now = new Date().toISOString()
    queue.value.forEach(a => {
      if (a?.url) tombstones[a.url] = now
    })
    queue.value = []
    addedUrls = {}
    markDirty()
    persist()
    // 统一经 doSync 串行写入；PUT 空队列与 DELETE 在 GET 语义上等价
    await doSync()
  }

  /**
   * 全部播放：将队列传给 playerStore
   */
  const playAll = async () => {
    if (queue.value.length === 0) {
      const { t } = i18n.global
      showToast({ message: t('listen.queueEmpty'), icon: 'info' })
      return
    }

    const { usePlayerStore } = await import('./playerStore')
    const playerStore = usePlayerStore()
    await playerStore.playFromList([...queue.value], 0)
  }

  return {
    queue,
    length,
    isEmpty,
    syncStatus,
    lastSyncAt,
    isInQueue,
    addToQueue,
    removeFromQueue,
    removeByUrl,
    reorder,
    clearQueue,
    playAll,
    restore,
    persist,
    initSync,
    syncFromServer,
    scheduleSync,
    resetLocal
  }
})
