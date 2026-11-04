# TTS 自动播放下一篇文章时文章信息缺失

## 问题描述

使用 mytest1 账户，播放完一篇文章后自动进入下一篇文章播放时：
- 播放页（player page）文章标题显示为 "No title"
- 底部状态栏（mini player）文章信息缺失，只显示 "Playing..."
- 音频播放本身正常进行

**预期表现**：自动切换到下一篇文章后，播放页和状态栏应正确显示新文章的标题、来源等信息。

**实际表现**：文章信息全部缺失/空白，但音频正常播放。

## 原因定位

### 根本原因

**竞态条件（Race Condition）**：音频播放结束（`ended` 事件）后、`playArticle` 中新的 `newTts.loadAudio()` 被调用前，playerStore 中旧的 `statusSyncInterval` 仍在运行。此时 `newTTS.isPlaying / isPaused / isLoading` 全为 false，导致 `idleSyncTicks` 在约 1 秒内累积到 10，触发 `clearInactiveCurrentArticle()` 将 `currentArticle` 清空为 `null`。随后 `playArticle` 继续执行并重新设置 `currentArticle = fullArticle`，但 UI 已渲染出缺失状态。

### 具体流程问题

1. 文章 A 播放结束 → `useTTS` 触发 `ended` 事件
2. `ended` 事件处理中同步设置 `isPlaying = false, isPaused = false`
3. 同步调用 `playerStore.onPlaybackEnd()`（无 await）
4. `onPlaybackEnd` → `playNext()` → `playArticle(playlist[1])`
5. 在 `playArticle` 内部，如果 `article.content` 为空，需先 `await getArticleByUrl()` 获取完整文章（耗时几百毫秒~数秒）
6. 在此期间，旧的 `statusSyncInterval`（每 100ms）仍在运行
7. interval 检查 `newTTS.isPlaying || isPaused || isLoading` → 全为 false
8. `idleSyncTicks` 连续累加，1 秒内达到 10
9. 触发 `clearInactiveCurrentArticle()` → `currentArticle.value = null`
10. 随后 `playArticle` 继续执行，`currentArticle.value = fullArticle`，但中间出现了 `null` 窗口

### 相关代码位置

- `frontend/src/stores/playerStore.js:249` — `playArticle` 函数，旧的 interval 清除太晚
- `frontend/src/stores/playerStore.js:893` — `onPlaybackEnd` 函数，未在切换前清除 interval
- `frontend/src/stores/playerStore.js:376-416` — interval 逻辑，`idleSyncTicks >= 10` 触发清除
- `frontend/src/stores/playerStore.js:231-241` — `clearInactiveCurrentArticle`，将 `currentArticle` 设为 null

## 修复方案

1. 在 `playArticle` 函数**最开头**立即调用 `clearStatusSyncInterval()`，确保旧 interval 不会在新播放启动过程中误判
2. 在 `onPlaybackEnd` 函数开头也调用 `clearStatusSyncInterval()`，作为双重保护

## 修复状态

- [x] 问题定位
- [x] 文档记录
- [x] 代码修复
- [x] Codex review
- [ ] 测试验证

## 修复记录

**修复文件**: `frontend/src/stores/playerStore.js`

**修复时间**: 2026-05-17

**修改内容**:
- `playArticle` 函数开头增加 `clearStatusSyncInterval()` 调用，防止旧 interval 在切换过程中因状态空闲误判为播放结束
- `onPlaybackEnd` 函数开头增加 `clearStatusSyncInterval()` 调用，作为自动连播时的双重保护

## 相关提交

（待提交）

## Review意见

## Feature: TTS auto-next article metadata preservation
- problem 1：
  - level: p2
  - decription: [Verification] The implemented fix addresses the documented race: `frontend/src/stores/playerStore.js:255` clears the previous status-sync interval at the start of `playArticle()`, before the async `getArticleByUrl()` gap, and `frontend/src/stores/playerStore.js:895` clears it again when `onPlaybackEnd()` starts. That prevents the old interval from reaching `idleSyncTicks >= 10` and calling `clearInactiveCurrentArticle()` while the next article is still being hydrated. I did not find a remaining blocking issue in this path. The remaining risk is that this race has no focused automated regression test, so a later refactor could move interval cleanup after the async fetch again without being caught.
  - fix suggestion: Add a targeted frontend store/composable test, or an e2e regression with mocked/delayed `getArticleByUrl()`, that finishes article A, delays article B hydration for more than 1 second, and asserts `currentArticle`/mini-player metadata never becomes empty before article B starts loading.
  - decision and reason(by claude):


## Comments and Future suggestion

Review passed for the current fix. The code change is intentionally narrow and closes the interval race described in this bug document. Manual validation should still cover the exact mytest1 auto-next flow on the deployed app because the current frontend test suite does not appear to include a playerStore race regression for this scenario.
