# Onboarding Starter Pack Slow Activation And Feed Count

## 问题描述

2026-05-17 新注册账号 `mytest1` 选择英文 starter pack 后，初始化耗时约 30 秒到 1 分钟，体验过慢。

同时，前端体验上看到 starter pack 相关来源数量像是 9 个，疑似比原始 starter pack 预期更多，可能来自英文体验用户的复制数据。

## 原因定位

### 根本原因

生产日志显示，`POST /api/v1/onboarding/starter-pack/activate?language=en` 从 2026-05-17 14:37:57 到 14:38:45，共约 48 秒。

耗时主要来自后端 `activate_starter_pack_feeds()` 在返回前逐个调用 `link_global_articles_to_feed()`，为每个 starter feed 同步链接已有 `global_articles` 历史文章。

`global_articles.source_feed_url` 当前没有索引，链接时需要按 feed URL 扫描全局文章表；英文 starter pack 中部分源历史文章量很大，导致首次激活明显变慢。

`mytest1` 实际 active feed 是 8 个：

- FOXNews.com: 2636 refs
- Business Insider: 1351 refs
- Fortune: 1224 refs
- Axios: 466 refs
- Ars Technica: 355 refs
- The Atlantic: 283 refs
- Vox: 158 refs
- Popular Science: 143 refs

用户看到 9 个来源入口时，前端 Feed 页还会额外添加一个 `All Sources` tab，因此 UI 上会显示 `1 + 8`。

### 相关代码位置

- `backend/api/main.py`: `activate_starter_pack`
- `backend/storage/database.py`: `activate_starter_pack_feeds`, `link_global_articles_to_feed`
- `backend/config/onboarding_starter_pack.py`: starter pack feed 定义
- `frontend/src/views/FeedView.vue`: `feedTabs` 会添加 `All Sources`

## 修复方案

- 为 `global_articles(source_feed_url)` 增加索引，减少按 feed URL 查找历史文章的扫描成本。
- 将英文 starter pack 从 8 个源收敛到 5 个高信号源，和中文 starter pack 的体量接近，并减少默认初始化时需要链接的历史文章数量。
- starter pack 激活返回前只同步每个源最近 20 篇文章，保证首屏有内容；完整历史文章通过 `BackgroundTasks` 调用原有全量链接逻辑补齐，避免用户等待。
- 保留完整 discovery feed catalog，不影响用户后续手动添加更多源。

## 修复状态

- [x] 问题定位
- [x] 文档记录
- [x] 代码修复
- [ ] 测试验证

## 修复记录

**修复文件**:
- `backend/config/onboarding_starter_pack.py`
- `frontend/src/config/recommendedFeeds.js`
- `backend/storage/schemas.sql`
- `backend/storage/migrations/2026_05_17_add_global_articles_source_feed_url_index.sql`
- `docs/bugs/2026-05-17-onboarding-starter-pack-slow-and-feed-count.md`
- `backend/storage/database.py`
- `backend/api/main.py`
- `tests/backend/storage/test_cross_user_sharing.py`

**修复时间**: 2026-05-17

**修改内容**:
- 英文 starter pack 移除 Fortune、Business Insider、FOXNews.com，保留 The Atlantic、Popular Science、Vox、Axios、Ars Technica。
- 增加 `idx_global_articles_source_feed_url` 索引定义和迁移。
- `link_global_articles_to_feed()` 支持 `limit` 参数；`activate_starter_pack_feeds()` 同步阶段使用 `limit=20`。
- `activate_starter_pack` API 在同步首屏文章后调度后台全量 backfill，并返回 `initial_link_limit` / `backfill_scheduled` 便于线上验证。

## 验证建议

1. 在生产数据库执行新增索引迁移后，重新注册英文新用户并选择 starter pack。
2. 确认 `activate` 请求耗时显著低于 `mytest1` 的 48 秒基线，并且响应包含 `initial_link_limit=20`、`backfill_scheduled=true`。
3. 确认新英文用户默认 active feeds 为 5 个，Feed 页 source tabs 为 `All Sources + 5`。
4. 等待后台补齐任务完成后，确认该用户的 `user_article_refs` 数量继续增长到完整历史量。
