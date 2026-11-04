/**
 * 听读队列多端同步的纯函数决策模块
 * 从 queueStore 抽离，便于 node:test 单元测试（参照 playbackRecoveryPolicy 模式）
 *
 * 背景：docs/bugs/20260721-queue_sync_deleted_items_reappear.md
 * 同步语义：dirty + tombstones（本设备删除）+ addedUrls（本设备新增）+ mutationSeq，
 * 区分「本地新增未上传」与「他端已删除的过期副本」，避免过期客户端把已删除内容并回服务器。
 */

/**
 * 拉取后是否直接采用服务器状态（server wins，不回写）
 * 条件：本地无未同步变更（dirty=false）且拉取期间没有发生新的本地变更
 */
export const shouldAdoptServerState = (dirty, seqAtFetch, currentSeq) => !dirty && seqAtFetch === currentSeq

/**
 * 拉取快照是否已过期
 * 过期快照必须丢弃，改为推当前本地状态（否则过期项会被合并复活）
 */
export const isSnapshotStale = (seqAtFetch, currentSeq) => seqAtFetch !== currentSeq

/**
 * doSync 结束后是否需要补发同步
 * 请求在途期间发生的本地变更会置位 pendingSync 或递增 mutationSeq，必须补发，
 * 否则最新变更只停留在本地（Codex review 问题 3）
 */
export const needsFollowUpSync = (pendingSync, seqAtStart, currentSeq) => pendingSync || seqAtStart !== currentSeq

/**
 * dirty 状态下的拉取合并：
 * - 服务器项过滤墓碑（本设备删除优先，含拉取期间的墓碑快照）
 * - 仅 addedUrls 中的本地项按本地顺序追加（本设备未同步的新增）
 * - 其余本地独有项一律视为过期副本丢弃（他端已删除，Codex review 问题 1）
 *
 * @param {object} input
 * @param {Array} input.serverItems 服务器队列快照
 * @param {Array} input.localItems 本地队列
 * @param {Object<string,string>} input.tombstones 删除墓碑 { url: deletedAtISO }（快照∪当前）
 * @param {Object<string,string>} input.addedUrls 新增记录 { url: addedAtISO }
 * @returns {Array} 合并后的队列
 */
export const mergeDirtyQueueOnPull = ({ serverItems, localItems, tombstones, addedUrls }) => {
  const tombstonedUrls = new Set(Object.keys(tombstones || {}))
  const added = addedUrls || {}
  const server = serverItems || []
  const local = localItems || []

  const serverUrls = new Set(server.map(a => a?.url).filter(Boolean))
  const merged = server.filter(a => a?.url && !tombstonedUrls.has(a.url))
  local.forEach(item => {
    if (item?.url && added[item.url] && !serverUrls.has(item.url)) {
      merged.push(item)
    }
  })
  return merged
}
