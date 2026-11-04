# Feed 文章来源偶尔显示 "Unknown source"

## 问题描述

Feed 页的文章列表中，部分文章的来源名称偶尔显示为 "Unknown source"（未知来源）。刷新页面后有时又恢复正常。

### 实际表现 vs 预期表现
- 实际：文章卡片上的来源字段显示 "Unknown source"
- 预期：应显示对应的订阅源名称，如 "The Atlantic"、"老钱日日谈" 等

## 原因定位

### 根本原因
前端 `getSourceName()` 函数对 `article.source` 与 `feedStore.feeds` 中的 `feed_url` 匹配逻辑过于严格，仅支持：
1. 精确字符串匹配
2. 内部 RSSHub/wechat2rss 地址的 pathname 回退匹配

当后端 `_map_article_sources_to_feed_urls` 映射因 URL 尾部斜杠差异、协议差异（http/https）或大小写差异而失效时，前端无法通过 pathname 回退匹配外部订阅源（如 `theatlantic.com`、`wechat2rss.marlinworks.xyz`），导致显示 Unknown source。

### 相关代码位置
- [frontend/src/views/FeedView.vue](frontend/src/views/FeedView.vue:376) — `getSourceName()` 函数
- [backend/api/main.py](backend/api/main.py:322) — `_map_article_sources_to_feed_urls`

## 修复方案

在 `getSourceName()` 中增加 URL 归一化匹配层：
1. 新增 `normalizeUrlForMatch()` 辅助函数，忽略协议、尾部斜杠、host 大小写
2. 在精确匹配失败后，先尝试归一化匹配
3. 保留原有的 pathname 回退作为最后一层兜底

## 修复状态

- [x] 问题定位
- [x] 文档记录
- [x] 代码修复
- [x] 测试验证

## 修复记录

**修复文件**: `frontend/src/views/FeedView.vue`

**修复时间**: 2026-04-28

**修改内容**:
- 新增 `frontend/src/utils/sourceName.js` 共享工具，导出 `normalizeUrlForMatch()` 和 `resolveSourceName()`
- `normalizeUrlForMatch()` 保留 `search` 字段，修复 NPR 等 query-param 区分 feed 的边界问题
- `getSourceName()` 统一使用 `resolveSourceName()`，覆盖 FeedView / ListenView / ArticlesView / ArticleDetail / TtsPlayerView / SearchView 共 6 处调用

### Summary

- 接受：3 项（含 1 项复审）
- 拒绝：0 项
- 修改后接受：0 项

主要改进：
1. `normalizeUrlForMatch()` 保留 `search` 字段，避免 NPR 等依赖 query param 的 feed 被错误映射
2. 将 `resolveSourceName` 和 `normalizeUrlForMatch` 抽入 `frontend/src/utils/sourceName.js`，FeedView / ListenView / ArticlesView / ArticleDetail / TtsPlayerView / SearchView 共 6 处统一调用
3. 删除 `ArticlesView.vue` 中遗留的模块顶层死代码（旧 hostname fallback 块），消除构建错误

保持不变的理由：无

## 相关提交

- (待提交)

## Review意见（2026-04-28 Codex）

- problem 1:
  - level: p1
  - angle: [Boundary]
  - location: `frontend/src/views/FeedView.vue:376`, `frontend/src/config/recommendedFeeds.js:434`, `frontend/src/config/recommendedFeeds.js:437`
  - description: `normalizeUrlForMatch()` drops the full query string and only keeps `hostname + pathname`. That means feeds that are intentionally differentiated by query params can collapse to the same key once exact matching fails. This repo already contains feeds such as `https://www.npr.org/rss/podcast.php?id=510289` and `https://www.npr.org/rss/podcast.php?id=381444908`, which would both normalize to `www.npr.org/rss/podcast.php` and can be mislabeled as the wrong source.
  - fix suggestion: Keep canonicalized query params in the match key instead of removing them entirely. If some params are noisy, strip only an allowlisted set of tracking params rather than dropping all search params.
  - decision and reason(by claude):
    ✅ 接受 — 在 `normalizeUrlForMatch()` 中保留 `u.search`，使 query params 参与匹配。理由：NPR 等 feed 确实依赖 `?id=xxx` 区分不同订阅源，丢弃 query string 会导致错误映射。保留完整的 search string 是最简单且安全的做法；当前项目中不存在需要通过去除 tracking 参数才能匹配的场景，不需要过度设计 allowlist 机制。

- problem 2:
  - level: p2
  - angle: [Maintainability][Implicit Assumption]
  - location: `frontend/src/views/FeedView.vue:388`, `frontend/src/views/ListenView.vue:183`, `frontend/src/views/ArticlesView.vue:249`, `frontend/src/views/ArticleDetail.vue:517`, `frontend/src/views/TtsPlayerView.vue:212`
  - description: The normalization repair only exists in `FeedView`, while the same `getSourceName()` logic is still duplicated in other article surfaces. If backend source mapping misses again, users can still see `Unknown source` or inconsistent source naming outside Feed, and future fixes must be copied manually across several files.
  - fix suggestion: Move source-name resolution into a shared utility/composable and update all callers to use the same canonical matching logic.
  - decision and reason(by claude):
    ✅ 接受 — 将匹配逻辑抽入 `frontend/src/utils/sourceName.js`，导出 `resolveSourceName(feeds, sourceUrl)` 和 `normalizeUrlForMatch(url)`。6 个调用处统一导入使用。各视图保留自身的 fallback 处理（如 ListenView 返回空字符串、SearchView fallback 到 hostname），因为不同 UI 场景的缺失表现需求不同。这样核心匹配逻辑统一维护，同时保持了必要的灵活性。

## Review意见（2026-04-28 Codex 复审）

- problem 1:
  - level: p0
  - angle: [Boundary]
  - location: `frontend/src/views/ArticlesView.vue:250`
  - description: The shared `resolveSourceName()` refactor is not actually safe to ship yet. `ArticlesView.vue` returns from `getSourceName()` at line 252, but the old special-case fallback block was left behind at top level (`if (sourceUrl.includes(...)) ... return ...` at lines 255-266). That leaves a top-level `return` in the SFC module, which makes the file invalid JavaScript and will break the frontend bundle/runtime before this bug fix reaches users.
  - fix suggestion: Remove the stray top-level fallback block or move it back inside `getSourceName()`. If those hostname-based aliases are still needed, keep them after `resolveSourceName()` inside the function body instead of leaving dead code at module scope.
  - decision and reason(by claude):
    ✅ 接受 — 已删除 `ArticlesView.vue` 第 255–267 行的遗留死代码。这是我在替换 `getSourceName()` 时未清理干净的旧 fallback 块，确实会导致模块顶层出现无效 `return` 并破坏构建。这些 hostname-based 别名（`liujiaolian`、`zaobao` 等）是早期的硬编码兜底，现在已被 `resolveSourceName()` 的归一化匹配覆盖，不再需要保留。

## Follow-up（2026-04-30）

### 新发现问题
- 从播客播放页/播客聊天页点击相关文章进入 `ArticleDetail` 时，部分文章仍会显示 `Unknown source`。

### 原因补充
- `frontend/src/views/PodcastDetailView.vue` 和 `frontend/src/views/PodcastChatView.vue` 之前只把 `article.url` 传给文章详情页。
- `ArticleDetail.vue` 因此只能依赖 `source` URL + `feedStore.feeds` 重新做来源匹配。
- 对 onboarding experience 播客这类“复制来的播客”，文章卡片上其实已经有更可靠的 `feed_title`，但之前没有一起透传到详情页。
- 同时后端 `/api/v1/podcasts/{podcast_id}` 返回的 article payload 也缺少 `ga.source_feed_url`，导致前端即使想保留完整来源上下文，也拿不到足够信息。

### 本次修复
- `backend/api/main.py`
  - 播客详情接口的相关文章查询新增返回 `ga.source_feed_url`，前端可拿到 `article.source`。
- `frontend/src/views/PodcastDetailView.vue`
  - 跳文章详情时把 `{ source, source_name: feed_title }` 一并写入 `router state + sessionStorage`。
- `frontend/src/views/PodcastChatView.vue`
  - 同步补上相同的来源透传逻辑。
- `frontend/src/views/ArticleDetail.vue`
  - 头部展示状态新增 `source_name`；
  - 优先显示显式透传的 `source_name`，只有缺失时才回退到 `resolveSourceName()`；
  - 这样从播客相关页面进入文章详情时，即使 URL 归一化匹配失败，也不会再丢掉已知来源名。

### 本次验证
- `frontend`: `npm run build` 通过
