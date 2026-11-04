import assert from 'node:assert/strict'
import test from 'node:test'

import {
  shouldAdoptServerState,
  isSnapshotStale,
  needsFollowUpSync,
  mergeDirtyQueueOnPull
} from '../../src/services/queue/queueSyncPolicy.js'

const item = (url, extra = {}) => ({ url, title: `t:${url}`, ...extra })

// ==================== shouldAdoptServerState ====================

test('shouldAdoptServerState: clean local + unchanged seq → server wins', () => {
  assert.equal(shouldAdoptServerState(false, 3, 3), true)
})

test('shouldAdoptServerState: dirty local never adopts server wholesale', () => {
  assert.equal(shouldAdoptServerState(true, 3, 3), false)
})

test('shouldAdoptServerState: mutation during fetch blocks server-wins even if not dirty', () => {
  // 拉取期间的删除可能已被在途 doSync 推送并清除 dirty，但 seq 必然变化
  assert.equal(shouldAdoptServerState(false, 3, 4), false)
})

// ==================== isSnapshotStale ====================

test('isSnapshotStale: seq changed during fetch → stale', () => {
  assert.equal(isSnapshotStale(3, 4), true)
  assert.equal(isSnapshotStale(3, 3), false)
})

// ==================== needsFollowUpSync ====================

test('needsFollowUpSync: pending or seq change requires follow-up', () => {
  assert.equal(needsFollowUpSync(true, 1, 1), true)
  assert.equal(needsFollowUpSync(false, 1, 2), true)
  assert.equal(needsFollowUpSync(false, 1, 1), false)
})

// ==================== mergeDirtyQueueOnPull ====================

test('merge: tombstoned server items are filtered (local delete wins over server snapshot)', () => {
  const merged = mergeDirtyQueueOnPull({
    serverItems: [item('a'), item('y')],
    localItems: [item('a')],
    tombstones: { y: '2026-07-21T01:00:00Z' },
    addedUrls: {}
  })
  assert.deepEqual(merged.map(i => i.url), ['a'])
})

test('merge: only addedUrls locals are appended, in local order', () => {
  const merged = mergeDirtyQueueOnPull({
    serverItems: [item('a'), item('b')],
    localItems: [item('a'), item('b'), item('x2'), item('x1')],
    tombstones: {},
    addedUrls: { x1: '2026-07-21T01:00:00Z', x2: '2026-07-21T00:59:00Z' }
  })
  assert.deepEqual(merged.map(i => i.url), ['a', 'b', 'x2', 'x1'])
})

test('merge: stale local-only copy is dropped — the 2026-07-21 resurrection bug', () => {
  // Android 设备持有过期副本 Y（早上已在 iPhone 删除并同步），自身无 dirty 操作记录
  // 若设备因其他原因 dirty（如离线 reorder），Y 不得被并回
  const merged = mergeDirtyQueueOnPull({
    serverItems: [item('a')],
    localItems: [item('a'), item('y-stale')],
    tombstones: {},
    addedUrls: {}
  })
  assert.deepEqual(merged.map(i => i.url), ['a'])
})

test('merge: device B dirty-adds X while device A deleted Y (Codex review problem 1)', () => {
  // B 离线新增 X（addedUrls={X}），期间 A 删除 Y 并同步成功；B 拉取合并：
  // Y 不在服务器、不在 addedUrls → 丢弃；X 追加保留
  const merged = mergeDirtyQueueOnPull({
    serverItems: [item('a')],
    localItems: [item('a'), item('y'), item('x')],
    tombstones: {},
    addedUrls: { x: '2026-07-21T05:30:00Z' }
  })
  assert.deepEqual(merged.map(i => i.url), ['a', 'x'])
})

test('merge: re-added item already on server is not duplicated', () => {
  const merged = mergeDirtyQueueOnPull({
    serverItems: [item('a'), item('b')],
    localItems: [item('a'), item('b')],
    tombstones: {},
    addedUrls: { b: '2026-07-21T06:00:00Z' }
  })
  assert.deepEqual(merged.map(i => i.url), ['a', 'b'])
})

test('merge: delete-then-readd before sync keeps the item (tombstone revoked by add)', () => {
  // 删除 Y（墓碑）后又重新加入（墓碑撤销、记入 addedUrls）
  const merged = mergeDirtyQueueOnPull({
    serverItems: [item('a'), item('y')],
    localItems: [item('a'), item('y')],
    tombstones: {},
    addedUrls: { y: '2026-07-21T06:05:00Z' }
  })
  assert.deepEqual(merged.map(i => i.url), ['a', 'y'])
})

test('merge: tombstone snapshot covers deletion during fetch', () => {
  // GET 在删除前发出（快照含 Y），删除发生在拉取在途期间：墓碑快照需过滤 Y
  const merged = mergeDirtyQueueOnPull({
    serverItems: [item('a'), item('y')],
    localItems: [item('a')],
    tombstones: { y: '2026-07-21T07:00:00Z' },
    addedUrls: {}
  })
  assert.deepEqual(merged.map(i => i.url), ['a'])
})

test('merge: clearQueue semantics — all urls tombstoned, nothing appended', () => {
  const merged = mergeDirtyQueueOnPull({
    serverItems: [item('a'), item('b')],
    localItems: [],
    tombstones: { a: '2026-07-21T08:00:00Z', b: '2026-07-21T08:00:00Z' },
    addedUrls: {}
  })
  assert.deepEqual(merged, [])
})

test('merge: items without url are filtered out', () => {
  const merged = mergeDirtyQueueOnPull({
    serverItems: [item('a'), { title: 'no-url' }],
    localItems: [item('a'), { title: 'no-url', id: 1 }],
    tombstones: {},
    addedUrls: {}
  })
  assert.deepEqual(merged.map(i => i.url), ['a'])
})

test('merge: tolerates empty/undefined inputs', () => {
  assert.deepEqual(
    mergeDirtyQueueOnPull({ serverItems: [], localItems: [], tombstones: undefined, addedUrls: undefined }),
    []
  )
  assert.deepEqual(
    mergeDirtyQueueOnPull({ serverItems: undefined, localItems: [item('x')], tombstones: {}, addedUrls: { x: 't' } }),
    [item('x')]
  )
})
