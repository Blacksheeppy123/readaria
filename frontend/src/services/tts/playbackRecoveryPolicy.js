/**
 * Playback Recovery Policy - 纯函数决策模块
 *
 * 把"何时自动恢复播放 / 何时预取下一篇 / 暂停如何分类"等决策抽成纯函数，
 * 便于 node:test 单元测试，避免散落在 composable 里无法覆盖。
 *
 * 背景: docs/bugs/20260721-tts_background_playback_failures.md
 */

/**
 * 分类一次 pause 事件
 * @param {Object} input
 * @param {boolean} input.manualPause - 用户主动暂停（含 Media Session 暂停键）
 * @param {boolean} input.internalTransition - 内部换源（分段切换/恢复重载）进行中
 * @param {boolean} input.ended - audio.ended 属性（自然播完）
 * @returns {'manual'|'internal'|'ended'|'unintended'}
 */
export function classifyPause({ manualPause = false, internalTransition = false, ended = false } = {}) {
  if (internalTransition && !manualPause) return 'internal'
  if (manualPause) return 'manual'
  if (ended) return 'ended'
  return 'unintended'
}

/**
 * 非预期暂停后是否允许立即自动恢复
 * 仅在前台可见时自动恢复；后台暂停可能是其他 app 抢走音频焦点，不抢回来。
 * @param {Object} input
 * @param {string} input.classification - classifyPause 的结果
 * @param {string} input.visibilityState - document.visibilityState
 * @param {boolean} input.online - navigator.onLine
 */
export function shouldAutoResumeAfterPause({ classification, visibilityState = 'visible', online = true } = {}) {
  if (classification !== 'unintended') return false
  if (visibilityState !== 'visible') return false
  if (!online) return false
  return true
}

/**
 * 回前台（visibilitychange → visible）时是否应 reconcile 恢复播放
 * @param {Object} input
 * @param {boolean} input.manualPause - 用户主动暂停 → 尊重，不恢复
 * @param {boolean} input.suppressAutoResume - 自然结束/用户停止 → 不恢复
 * @param {boolean} input.hasSession - 存在当前文章和音频会话
 * @param {boolean} input.elementStopped - audio 元素已暂停或已结束
 * @param {boolean} input.online
 */
export function shouldResumeOnForeground({
  manualPause = false,
  suppressAutoResume = false,
  hasSession = false,
  elementStopped = false,
  online = true
} = {}) {
  if (!hasSession) return false
  if (manualPause) return false
  if (suppressAutoResume) return false
  if (!online) return false
  return elementStopped
}

/**
 * 看门狗：元素自认为在播但进度不前进（iOS 静默断流/内核挂起）判定
 * @param {Object} input
 * @param {boolean} input.paused - audio.paused
 * @param {boolean} input.ended - audio.ended
 * @param {boolean} input.manualPause
 * @param {boolean} input.internalTransition
 * @param {boolean} input.seeking - seek 进行中（pendingSeek）
 * @param {boolean} input.recovering - 恢复流程进行中
 * @param {boolean} input.hasSession - 存在音频源
 * @param {number} input.currentTime - 本次采样的 audio.currentTime
 * @param {number} input.lastTime - 上次采样的 audio.currentTime
 * @param {boolean} input.online
 */
export function isPlaybackStagnant({
  paused = true,
  ended = false,
  manualPause = false,
  internalTransition = false,
  seeking = false,
  recovering = false,
  hasSession = false,
  currentTime = 0,
  lastTime = 0,
  online = true
} = {}) {
  if (!hasSession) return false
  if (paused || ended) return false
  if (manualPause || internalTransition || seeking || recovering) return false
  if (!online) return false
  return Math.abs((currentTime || 0) - (lastTime || 0)) < 0.05
}

/**
 * store idle 轮询收口：中途（0 < currentTime < totalTime）停滞时
 * 应保留会话并标记为可恢复暂停，而不是清空 currentArticle。
 * @param {Object} input
 * @param {number} input.currentTime
 * @param {number} input.totalTime
 */
export function shouldPreserveAsPaused({ currentTime = 0, totalTime = 0 } = {}) {
  return totalTime > 0 && currentTime > 0 && currentTime < totalTime
}

/**
 * 是否应触发"下一篇"客户端预取（timeupdate 驱动）
 * @param {Object} input
 * @param {number} input.currentTime
 * @param {number} input.totalTime
 * @param {boolean} input.hasNext - playlist 中存在带 id 的下一篇
 * @param {boolean} input.prefetched - 已预取成功
 * @param {boolean} input.inFlight - 预取进行中
 * @param {number} input.lastAttemptAt - 上次尝试时间戳（ms）
 * @param {number} input.now - 当前时间戳（ms）
 * @param {number} [input.thresholdSec=75] - 剩余多少秒内开始预取
 * @param {number} [input.retryMs=10000] - 失败/未就绪重试间隔
 */
export function shouldPrefetchNextTrack({
  currentTime = 0,
  totalTime = 0,
  hasNext = false,
  prefetched = false,
  inFlight = false,
  lastAttemptAt = 0,
  now = 0,
  thresholdSec = 75,
  retryMs = 10000
} = {}) {
  if (!hasNext || prefetched || inFlight) return false
  if (totalTime <= 0) return false
  if (totalTime - currentTime > thresholdSec) return false
  if (lastAttemptAt && now - lastAttemptAt < retryMs) return false
  return true
}
