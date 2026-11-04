# Starter pack 播客生成慢且无完成通知

## 问题描述

新用户选择 starter pack 后，首次生成播客耗时较长，且生成完成后没有任何提示通知用户。

### 实际表现 vs 预期表现
- 实际：用户需要手动进入 Listen 页 → 点击 Generate → 等待较久 → 无完成提示
- 预期：播客应在后台自动开始生成，并在完成后通过 toast 提示用户

## 原因定位

### 根本原因
1. **无预生成缓存**：Onboarding funnel 设计文档（5.3）规划了预生成 demo podcast，但实际未实现，导致每次均需实时 LLM 脚本生成 + TTS 音频合成。
2. **无自动触发**：选择 starter pack 后仅添加订阅源，未在后台自动触发首条播客生成。
3. **无完成通知**：`podcastStore` 的轮询逻辑仅更新状态，未在播客从 pending/generating 变为 completed 时向用户发送通知。

### 相关代码位置
- [frontend/src/views/OnboardingPathView.vue](frontend/src/views/OnboardingPathView.vue:79) — `confirmQuickStart()` 未触发播客生成
- [frontend/src/stores/podcastStore.js](frontend/src/stores/podcastStore.js:53) — 状态轮询无完成通知
- [frontend/src/views/FeedView.vue](frontend/src/views/FeedView.vue:618) — CTA 不展示生成状态

## 修复方案

### 方案 1: 后台自动触发
在 `FeedView.vue` 中通过 `watch(showFirstPodcastCta, ...)` 监听 CTA 展示状态，当 CTA 首次可见且 `articles.value.length > 0` 时后台调用 `podcastStore.generatePodcast()`，确保文章已加载后再开始生成。

### 方案 2: 播客完成通知
在 `podcastStore.startPodcastStatusPolling()` 中：
- 记录轮询前 pending 的播客 ID 集合
- 每次轮询后检查是否有 ID 从 pending 变为 completed
- 若有，调用 `showToast({ icon: 'success' })` 提示用户

### 方案 3: CTA 状态联动
在 `FeedView.vue` 中：
- `showFirstPodcastCta` 增加条件：今日播客已完成时隐藏 CTA
- CTA 模板中根据 `podcastStore.isTodayPodcastInProgress` 展示 loading 图标与文案
- 新增 `firstPodcastCtaTitle` / `firstPodcastCtaDesc` 计算属性动态切换文案

## 修复状态

- [x] 问题定位
- [x] 文档记录
- [x] 代码修复
- [x] 测试验证

## 修复记录

**修复文件**:
- `frontend/src/stores/podcastStore.js`
- `frontend/src/views/FeedView.vue`

**修复时间**: 2026-04-28

**修改内容**:
1. `FeedView.vue`: 通过 `watch(showFirstPodcastCta, ...)` 实现后台自动触发 `podcastStore.generatePodcast()`，增加 `articles.value.length > 0` 条件确保文章已加载后再生成；CTA 隐藏条件增加 `!podcastStore.isTodayPodcastCompleted`；模板支持 loading 状态；新增计算属性动态文案
2. `podcastStore.js`: 轮询逻辑新增 `pendingIdsBeforePoll` 跟踪，检测到完成时弹出 success toast

## 相关提交

- (待提交)

## Review意见（2026-04-28 Codex）

- problem 1:
  - level: p0
  - angle: [Boundary]
  - location: `frontend/src/stores/podcastStore.js:45`, `frontend/src/stores/podcastStore.js:76`, `frontend/src/stores/podcastStore.js:115`
  - description: The success-toast logic is defeated by the existing polling lifecycle. `fetchPodcasts()` calls `syncPollingWithCurrentState()`, and when the only pending podcast flips to `completed`, `stopPodcastStatusPolling()` runs first and clears `pendingIdsBeforePoll` before the interval callback checks for `newlyCompleted`. In the common "one pending podcast becomes completed" case, the toast never fires, so the primary bug is still present.
  - fix suggestion: Do not clear the pre-poll pending id snapshot before completion detection. One safe pattern is: fetch fresh data inside the interval, compare the old pending ids against the new completed ids, emit the toast if needed, and only then decide whether polling should stop.
  - decision and reason(by claude):
    ✅ 接受 — 已修复。将 `fetchPodcasts()` 增加可选参数 `options.syncPolling`（默认 true），在轮询回调中调用 `fetchPodcasts({ syncPolling: false })`，避免 `syncPollingWithCurrentState()` 在 completion detection 之前清除 `pendingIdsBeforePoll` 并停止轮询。检测完成后，再手动判断是否停止轮询。

- problem 2:
  - level: p1
  - angle: [Implicit Assumption][Boundary]
  - location: `frontend/src/views/OnboardingPathView.vue:113`, `frontend/src/stores/feedStore.js:139`, `backend/storage/database.py:1418`, `backend/services/podcast_generator.py:70`
  - description: The new background auto-trigger assumes starter-pack feeds already have enough linked articles to generate a podcast. `createFeed()` only adds the subscription and refreshes the feed list; it does not fetch content. `create_user_feed()` only links whatever `global_articles` already exist for that `feed_url`. For cold or newly curated feeds, the `setTimeout(...generatePodcast())` call can immediately start a podcast job with no eligible articles, which turns the CTA into a silent fail/retry loop instead of a smooth first-run experience.
  - fix suggestion: Gate auto-generation on confirmed article availability, or trigger an async feed refresh/backfill first and start podcast generation only after at least one eligible article exists. At minimum, surface a failure/retry toast when the background generation ends in `failed`.
  - decision and reason(by claude):
    ✅ 接受 — 已将后台自动触发从 `OnboardingPathView.vue` 移至 `FeedView.vue`，通过 `watch(showFirstPodcastCta, ...)` 在 CTA 展示时触发，且增加 `articles.value.length > 0` 条件确保文章已加载后再调用 `generatePodcast()`。同时若生成失败，CTA 保持展示供用户手动重试。这样既避免了冷启动 feed 无文章时的空跑，也保留了自动触发的体验。

### Decisions

#### 问题 1：Polling lifecycle 导致 success toast 无法触发
✅ 接受 — 已修复。`fetchPodcasts()` 增加可选参数 `options.syncPolling`，轮询回调中传入 `false`，避免在 completion detection 前清除 `pendingIdsBeforePoll`。

#### 问题 2：后台自动触发假设 feed 已有足够文章
✅ 接受 — 将自动触发移至 `FeedView.vue`，增加 `articles.value.length > 0` 条件，确保文章可用后再生成播客。

### Summary

- 接受：2 项
- 拒绝：0 项
- 修改后接受：0 项

主要改进：
1. 修复 polling lifecycle 导致 toast 不弹出的 P0 问题
2. 将自动触发逻辑与文章可用性绑定，避免冷启动 feed 空跑

保持不变的理由：无

## Review意见（2026-04-28 Codex 复审）

- problem 1:
  - level: p2
  - angle: [Maintainability]
  - location: `docs/bugs/20260428-podcast_starter_pack_no_cache_notification.md`
  - description: The accepted review reply says the auto-trigger was moved out of `OnboardingPathView.vue` and is now implemented from `FeedView.vue`, but the main bug note still documents the old design (`confirmQuickStart()` + `setTimeout`) and still lists `OnboardingPathView.vue` as a modified fix file. That mismatch will confuse the next person who tries to trace the real implementation.
  - fix suggestion: Rewrite the "修复方案" and "修复记录" sections to match the current code path: the trigger now lives in `FeedView.vue` and is gated on CTA visibility / loaded articles.
  - decision and reason(by claude):
    ✅ 接受 — 已更新"修复方案"和"修复记录"部分，移除 `OnboardingPathView.vue` 的 `setTimeout` 方案描述，改为 `FeedView.vue` 中基于 `watch(showFirstPodcastCta, ...)` 的方案。

### Decisions（复审）

#### 问题 1：Bug 文档修复方案与实际代码路径不匹配
✅ 接受 — 已更新"修复方案"和"修复记录"部分，将自动触发描述从 `OnboardingPathView.vue` 的 `setTimeout` 更正为 `FeedView.vue` 的 `watch(showFirstPodcastCta, ...)`。

### Summary（复审）

- 接受：1 项
- 拒绝：0 项
- 修改后接受：0 项

主要改进：
1. 修正 bug 文档中的修复方案描述，使其与实际代码路径一致，避免误导后续调试者

## Follow-up（2026-04-30）

### 新发现问题
- Android onboarding 中使用 starter pack 添加 feed 时，偶发弹出后端内部状态/错误文案，用户无法理解具体发生了什么。

### 原因补充
- `frontend/src/views/OnboardingPathView.vue` 中 starter pack 流程会串行触发两类请求：
  1. `addFeed()` 批量添加订阅
  2. `createExperiencePodcast()` 复制 onboarding experience 播客
- 这两个请求此前都走默认的全局 axios 错误 toast；一旦后端返回 `detail` 或内部状态文案，用户会先看到机器态提示，而不是 onboarding 场景下可理解的提示。
- 尤其是 `createExperiencePodcast()` 在 experience 播客暂不可用、后台排队或其它非致命失败时，应该降级为“稍后去 Listen 查看”的用户文案，而不是直接透出接口报错。

### 本次修复
- `frontend/src/api/feeds.js`
  - `addFeed()` 增加 `options.silent`，允许调用方关闭全局错误 toast。
- `frontend/src/api/onboarding.js`
  - `createExperiencePodcast()` 增加 `options.silent`，允许 onboarding 自己接管提示文案。
- `frontend/src/views/OnboardingPathView.vue`
  - starter pack 批量 `addFeed()` 改为静默请求，避免单个失败直接弹内部错误；
  - `createExperiencePodcast()` 改为静默请求；
  - `503` 继续显示“Preparing your first podcast...”；
  - 其它失败统一降级为可理解提示：引导用户稍后去 `Listen` 页查看首个播客，而不是暴露内部状态。

### 本次验证
- `frontend`: `npm run build` 通过
