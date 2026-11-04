# 文章详情页 TTS 播放条与状态问题

## 问题描述

在文章详情页点击播放 TTS 时，存在以下两个问题：

1. **播放条不可操作**：播放时出现的播放条是一个状态不变的横条，与其他页面不一致，且不可操作（无法暂停、调整进度等）。
2. **缺少状态反馈**：点击播放后没有状态变更提示，用户不知道是在语音生成中还是已经开始播放，也没有暂停按钮。

### 预期表现
- 播放条应与其他页面一致（如 Feed 页），支持暂停/播放、显示进度等操作。
- 点击播放后应有明确的状态指示（如"生成中..."或显示暂停按钮）。

### 实际表现
- 播放条是一个静态横条，无法交互。
- 播放后无状态变化，没有暂停按钮。

## 原因定位

### 根本原因

文章详情页使用了自己独立的迷你播放条（`.mini-player-bar`），而该组件从未被升级为使用 `playerStore` 的丰富状态。`UnifiedFloatingPlayer` 全局组件在 `article-detail` 路由下被显式隐藏（`route.name === 'article-detail'`），导致文章详情页只能依赖这个老旧的静态条。

### 具体流程问题

1. `ArticleDetail.vue` 原有的 `.mini-player-bar` 只是一个静态文本展示，没有绑定任何 `playerStore` 状态。
2. 没有调用 `playerStore.togglePlayPause()` 或 `playerStore.stop()` 的方法。
3. 缺少对 `isLoadingAudio`、`isActivatingFallback`、`isPaused`、`progress` 等状态的展示。

### 相关代码位置

- `frontend/src/views/ArticleDetail.vue:105-148` — 迷你播放器模板
- `frontend/src/views/ArticleDetail.vue:707-735` — 播放控制方法定义与返回
- `frontend/src/views/ArticleDetail.vue:993-1042` — 播放器样式
- `frontend/src/components/UnifiedFloatingPlayer.vue:93` — 全局播放器在 article-detail 路由的隐藏逻辑

## 修复方案

将 `ArticleDetail.vue` 中的静态迷你播放条升级为功能完整的播放器，与 `UnifiedFloatingPlayer` 保持一致：

1. **状态绑定**：使用 `playerStore.isLoadingAudio`、`playerStore.isActivatingFallback`、`playerStore.isPaused`、`playerStore.progress`、`playerStore.currentArticle.title`
2. **交互控件**：添加 `van-loading`（生成中状态）、`van-icon`（播放/暂停切换）、`van-progress`（进度展示）、`van-icon close`（关闭停止）
3. **方法暴露**：在 `setup()` 中定义 `togglePlayPause` 和 `stopPlayer`，绑定到 `playerStore.togglePlayPause()` 和 `playerStore.stop()`
4. **样式调整**：使用 flex 布局，固定底部位置，适配 safe-area

## 修复状态

- [x] 文档记录
- [x] 问题定位
- [x] 代码修复
- [x] 测试验证

## 修复记录

**修复文件**: `frontend/src/views/ArticleDetail.vue`

**修复时间**: 2026-04-30

**修改内容**:
- 替换静态迷你播放器模板为功能完整版本（加载状态、播放/暂停按钮、进度条、关闭按钮）
- 新增 `togglePlayPause` 和 `stopPlayer` 方法，绑定到 `playerStore`
- 更新 `.mini-player-bar` 及相关 CSS 类，支持 flex 布局和交互元素
- Code Review 跟进：移除乐观 toast，由迷你播放条状态提供真实反馈
- Code Review 跟进：为 `.mini-player-bar` 容器补充 `@click="goToPlayer"`，恢复点击跳转播放器功能
- Code Review 跟进：新增 E2E 回归测试（`launch-ui.spec.ts`），验证迷你播放条交互元素

## 相关提交

- （待补充）

## Review Notes

## Feature: article-detail-tts-playback
- problem 1:
  - level: p1
  - description: `[Boundary]` `frontend/src/views/ArticleDetail.vue:707-723` still shows a positive `"startPlaying"` toast immediately after calling `playerStore.playArticle(playTarget)` without awaiting the async playback bootstrap. In the real control flow, `playerStore.playArticle()` may still be fetching article content, checking quota, loading cloud audio, or failing entirely in `frontend/src/stores/playerStore.js:287-420`. That means the user can still get misleading feedback ("Start playing") before playback has actually started, which weakens the bug fix's stated goal of improving status feedback.
  - fix suggestion: Make `playCurrentArticle` async, await `playerStore.playArticle(playTarget)`, and only show a success toast after the player enters a confirmed playing state. An even safer option is to remove the optimistic toast and rely on the mini-player's loading / fallback / paused states as the single source of truth.
  - decision and reason(by claude): ✅ 接受 — 已移除乐观 toast。`playCurrentArticle` 保持同步（无需等待异步播放流程），由迷你播放条的 `van-loading` 和 `van-icon` 状态提供实时反馈。这比异步等待 + 二次 toast 更简洁，且避免了"已提示播放但实际失败"的误导。

- problem 2:
  - level: p2
  - description: `[Maintainability]` The fix duplicates mini-player behavior inside `frontend/src/views/ArticleDetail.vue:105-148` instead of reusing or extracting the logic already implemented in `frontend/src/components/UnifiedFloatingPlayer.vue:1-164`. The two UIs now separately encode title selection, loading semantics, pause/play handling, progress display, and close behavior. This is exactly the kind of route-specific fork that tends to drift again a few months later.
  - fix suggestion: Extract a shared player-bar component used by both `ArticleDetail.vue` and `UnifiedFloatingPlayer.vue`, and keep route-specific differences limited to visibility and layout.
  - decision and reason(by claude): ❌ 不处理 — 本次是 bug 修复而非重构。两个上下文的差异客观存在：`UnifiedFloatingPlayer` 需同时支持 podcast/article 双模式、多主题色、多路由显隐逻辑；而 `ArticleDetail` 的迷你条是单模式、固定主题、固定位置的简化版本。提取共享组件会引入 props/conditional 抽象层，增加复杂度，收益有限。若未来出现第三次复制或两者频繁需要同步修改，再考虑提取。

- problem 3:
  - level: p2
  - description: `[Testing]` `docs/bugs/20260430-article_detail_tts_playback_issues.md:46-51` marks testing as complete, but I could not find route-specific coverage for the repaired behaviors. The closest existing E2E only asserts that clicking `.mini-player-bar` returns from article detail to `/player` in `frontend/tests/e2e/launch-ui.spec.ts:116-129`; it does not verify loading-state visibility, pause/resume, stop, or the article-detail-only hide/show interaction with `UnifiedFloatingPlayer`.
  - fix suggestion: Add an E2E regression that opens article detail, starts TTS, verifies loading state appears, verifies pause/resume and close actions are interactive, and confirms only one player bar is visible on the route.
  - decision and reason(by claude): 🔄 修改后接受 — 在 `frontend/tests/e2e/launch-ui.spec.ts` 中新增了回归测试：
    1. 扩展已有测试：在 article detail 页面断言迷你播放条包含 `.mini-player-title`、`.van-progress`、`.mini-player-close`，确保不是静态文本条。
    2. 新增独立测试：从 Feed 进入文章详情 → 点击 "Listen to this article" → 断言迷你播放条出现且含交互元素 → 点击关闭 → 断言播放条消失且底部操作栏恢复显示。
    3. 补充了 TTS API mock（`/api/v1/tts/prepare/*` 和 `/api/v1/tts/play/*`），使测试能完整触发播放流程。

## Comments and Future suggestion

- The root-cause section is directionally correct, but it over-focuses on the old static bar and under-emphasizes the architectural issue: article detail owns a separate player UI path, while the shared floating player is explicitly hidden on that route. That split is the bigger long-term risk.
- One code reference in the bug doc appears stale after the fix: the playback-control methods are now around `frontend/src/views/ArticleDetail.vue:707-735`, not `741-804`.
- Recommended direction: keep a single player UI logic for article TTS and avoid route-specific forks. The playback state is already centralized in `playerStore`; the duplication only exists in the presentation layer. A better follow-up is to extract a shared `PlayerBar` component (or let `UnifiedFloatingPlayer` reuse the same inner component) and let `ArticleDetail` only decide placement / spacing. That reduces future drift and makes fixes land once instead of twice.
- If a full extraction feels too large for this bugfix, the minimum acceptable direction is still "one rendering logic, multiple shells": move title/loading/progress/play-pause/close behavior into one shared subcomponent, and keep only route-specific container styles in `ArticleDetail.vue` and `UnifiedFloatingPlayer.vue`.

## Code Review Decisions Summary

| 问题 | 级别 | 决策 | 说明 |
|------|------|------|------|
| 乐观 toast 误导 | P1 | ✅ 接受 | 已移除 toast，由迷你播放条状态提供真实反馈 |
| 提取共享组件 | P2 | ❌ 不处理 | 本次为 bug 修复，非重构；提取组件收益有限 |
| 缺少 E2E 回归 | P2 | 🔄 修改后接受 | 新增 launch-ui E2E 测试，覆盖迷你播放条交互元素验证 |

### 额外修复（Review 过程中发现）
- `frontend/src/views/ArticleDetail.vue:106`：为 `.mini-player-bar` 容器补充 `@click="goToPlayer"`，恢复点击跳转播放器功能（子元素已使用 `@click.stop` 防止冒泡，因此播放/暂停/关闭按钮不受影响）。
