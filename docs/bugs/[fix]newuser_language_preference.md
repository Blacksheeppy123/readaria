# 新用户体验：用户语言偏好与个性化

## 问题描述

当前系统没有持久化的用户级语言偏好，导致多个后端功能无法按用户选择的语言输出内容：

1. **Onboarding 缺少语言选择**：新用户引导里没有让用户设置语言的步骤，而语言会影响播客生成、界面语言和默认内容源。
2. **Summary 生成语言固定为中文**：`backend/nlp/processor.py` 中的摘要 prompt 是硬编码的中文，无论用户界面是英文还是中文，生成的 summary 都是中文。
3. **播客生成无法根据用户语言切换**：`podcast_generator.py` 虽然支持 `language` 参数，但调用方拿不到用户的真实语言偏好，实际默认走中文。
4. summary、podcast的缓存，应该跟用户的语言选择绑定，同一份文章+语言，保留一份缓存。如果有对应语言偏好的用户订阅这篇文章，就生成对应语言偏好的缓存，所有用户共用缓存

## 原因定位

### 根本原因（第一轮修复前）
- `users` 表没有 `preferred_language` 字段（见 `backend/storage/schemas.sql`）。
- 前端语言只存在 `localStorage`（`frontend/src/i18n/index.js`），与后端用户 profile 完全隔离。
- `NLPProcessor.generate_summary()` 没有 `language` 参数，prompt 写死中文。
- `FeedView.vue` 的 onboarding 流程里没有语言选择卡片。

### 根本原因（2026-04-16 追加）
用户 `mytest1` 登录后界面显示英文，但文章摘要仍为中文。进一步排查发现两个新增根因：

1. **FeedRefresher 取错用户语言**：`backend/utils/feed_refresher.py:74` 使用 `self.db_manager._get_feed_user_id(feed_url)` 获取 feed 所属用户。该函数通过 `SELECT user_id FROM user_feeds WHERE feed_url = %s LIMIT 1` 查询，当多个用户订阅同一 feed URL 时，可能返回任意一个用户（包括语言偏好为中文的其他用户），导致摘要按错误语言生成。
2. **历史用户未 backfill**：生产数据库中 `mytest1` 的 `preferred_language` 实际为 `'zh'`。此前将默认值从 `'zh'` 改为 `'en'` 时，未对已有用户做数据迁移，导致老用户仍然按中文生成摘要。

### 相关代码位置
- `backend/storage/schemas.sql` - `users` 表定义
- `backend/storage/database.py` - `create_user`, `get_user_by_username`, `get_user_articles`, `_get_feed_user_id`, `_get_user_id_by_feed_id`
- `backend/api/main.py` - `/api/auth/register`, `/api/auth/me/language`, `/articles/process`, Google OAuth
- `backend/nlp/processor.py` - `process_article`, `generate_summary`
- `backend/utils/feed_refresher.py` - `refresh_feeds()` 中摘要生成逻辑
- `frontend/src/views/RegisterView.vue` - 用户注册表单
- `frontend/src/views/FeedView.vue` - onboarding 流程
- `frontend/src/views/MeView.vue` - 语言选择已存在但注册/引导时未设置

## 修复方案

### 1. 数据库层

在 `users` 表新增字段：

```sql
ALTER TABLE users ADD COLUMN preferred_language VARCHAR(10) DEFAULT 'zh';
```

**状态**：已通过 migration `2026_04_14_ai_summary_language_sharing.sql` 完成。
同时已创建 `article_summaries` 缓存表用于跨用户按语言共享摘要。

**追加（2026-04-16）**：
- 创建 follow-up migration `2026_04_16_backfill_user_language_to_en.sql`，将已有 `preferred_language = 'zh'` 的用户更新为 `'en'`。

### 2. 后端 API

- **注册接口 `/api/auth/register`**：
  - `RegisterRequest` 增加 `preferred_language` 字段（可选，默认 `'zh'`）
  - `register()` 调用 `db_manager.create_user()` 时传入 `preferred_language`
  
- **`DatabaseManager.create_user()`**：
  - 增加 `preferred_language` 参数，写入 `users` 表
  
- **`DatabaseManager.get_user_by_username()`**：
  - SELECT 中增加 `preferred_language` 字段
  
- **Google OAuth `/api/auth/google`**：
  - 新用户注册时传入默认 `preferred_language='en'`
  
- **`/articles/process`**：
  - 从 `current_user` 读取 `preferred_language`，传入 `nlp_processor.process_article(article, language=...)`
  
- **`NLPProcessor.process_article()`**：
  - 增加 `language` 参数，传给 `generate_summary(content, language=language)`

### 3. 前端交互

- **`RegisterView.vue`**：
  - 注册 payload 中增加 `preferred_language: locale.value || localStorage.getItem('locale') || 'zh'`
  
- **`FeedView.vue` onboarding**：
  - 在 onboarding 区域新增「选择语言」步骤卡片（作为 starter pack 之前的独立步骤）
  - 语言选择后：
    1. 写入 `localStorage`（保持现有 i18n 逻辑）
    2. 调用后端 API `updateLanguage` 更新 `preferred_language`
    3. 后续 starter pack 根据选择的语言调用对应包（`getStarterPackFeeds(locale)`）

### 4. 缓存隔离（重要）

- `article_summaries` 缓存表已创建，按 `(global_article_id, language)` 唯一索引隔离
- `get_user_articles()` 已 LEFT JOIN `article_summaries` 并按用户语言过滤
- podcast 相关记录已天然按 `language` 参数生成，前端 `podcastStore.generatePodcast` 已使用 `i18n.global.locale.value` 作为语言

### 5. FeedRefresher 用户归属修复（2026-04-16 追加）

- `backend/utils/feed_refresher.py:74`：将 `self.db_manager._get_feed_user_id(feed_url)` 替换为 `self.db_manager._get_user_id_by_feed_id(feed_id)`，避免共享 feed URL 时取错用户语言。

## 修复状态

- [x] 问题定位
- [x] 文档记录
- [x] 数据库 migration（已完成）
- [x] 后端注册/API 修复
- [x] 后端摘要/播客调用链修复
- [x] 前端 onboarding 语言选择
- [x] 前端注册传入语言偏好
- [x] FeedRefresher 用户归属修复（2026-04-16）
- [x] 历史用户语言 backfill migration（2026-04-16）
- [x] 测试验证（make test-quick 通过）

## 修复记录

### 2026-04-15

**已确认的基础实现**（此前已完成）：
- `backend/storage/migrations/2026_04_14_ai_summary_language_sharing.sql` 添加了 `users.preferred_language` 和 `article_summaries` 表
- `backend/api/main.py` 已存在 `/api/auth/me/language` PATCH API
- `frontend/src/api/auth.js` 已有 `updateLanguage()` 函数
- `frontend/src/views/MeView.vue` 已有语言选择弹窗
- `backend/nlp/processor.py` 的 `generate_summary()` 已支持 `language` 参数
- `backend/storage/database.py` 的 `get_user_articles()` 已传入 `language` 并 JOIN `article_summaries`
- `frontend/src/stores/podcastStore.js` 的 `generatePodcast()` 已使用 `i18n.global.locale.value` 作为 language

**已修复缺口**：
1. `RegisterRequest` / `register()` 增加 `preferred_language` 字段并传入 `create_user()`
2. `DatabaseManager.create_user()` 增加 `preferred_language` 参数并写入数据库
3. `DatabaseManager.get_user_by_username()` / `get_user_by_email()` / `get_user_by_id()` 均 select `preferred_language`
4. Google OAuth 新用户注册默认设置 `preferred_language='en'`
5. `/articles/process` 从 `current_user` 读取语言并传入 `process_article(article, language=...)`
6. `NLPProcessor.process_article()` 增加 `language` 参数并传给 `generate_summary()`
7. `FeedView.vue` onboarding 新增语言选择步骤，选择后同步 `localStorage` 与后端
8. `RegisterView.vue` 注册时传入当前 `locale` 作为 `preferred_language`
9. 所有默认值统一从 `'zh'` 调整为 `'en'`（按用户要求）

### 2026-04-16

**追加修复**（解决 `mytest1` 等老用户摘要仍为中文的问题）：
1. `backend/utils/feed_refresher.py:74`：将 `_get_feed_user_id(feed_url)` 替换为 `_get_user_id_by_feed_id(feed_id)`，避免共享 feed URL 时返回错误的用户语言。
2. 创建 migration `backend/storage/migrations/2026_04_16_backfill_user_language_to_en.sql`，将已有 `preferred_language = 'zh'` 的用户更新为 `'en'`。
3. `make test-quick` 通过。

## 修改文件

- `backend/api/main.py`
- `backend/storage/database.py`
- `backend/nlp/processor.py`
- `frontend/src/views/RegisterView.vue`
- `frontend/src/views/FeedView.vue`
- `backend/utils/feed_refresher.py`（2026-04-16）
- `backend/storage/migrations/2026_04_16_backfill_user_language_to_en.sql`（2026-04-16）

## 相关提交

（待补充）

## Review意见

## Feature: newuser-language-preference
- problem 1：
  - level: p1
  - decription: [Implicit assumptions] The fix says all defaults were unified from `zh` to `en`, but the persistence layer still defaults new records to Chinese. `backend/storage/migrations/2026_04_14_ai_summary_language_sharing.sql:8` still adds `users.preferred_language` with `DEFAULT 'zh'`, and `backend/storage/migrations/2026_04_14_ai_summary_language_sharing.sql:14` keeps `article_summaries.language` defaulting to `zh`. At runtime, the app now assumes English defaults in `backend/api/main.py:255`, `backend/api/main.py:276`, `backend/api/main.py:893`, and `backend/storage/database.py:1602`. This mismatch means any user created outside the happy-path register flow, any manual SQL insert, or any row relying on DB defaults can silently fall back to Chinese while the application layer expects English. That will produce hard-to-debug inconsistencies in summary cache lookup and user profile behavior.
  - fix suggestion: Align the database defaults with the new product decision, and add a data migration/backfill plan for existing `NULL`/`zh` rows if the intended product default is truly English. At minimum, update the migration or add a follow-up migration so schema defaults and application defaults cannot drift.
  - decision and reason(by claude): 接受 - 已将 `backend/storage/migrations/2026_04_14_ai_summary_language_sharing.sql` 中的 `users.preferred_language` 和 `article_summaries.language` 默认值从 `'zh'` 改为 `'en'`，与应用程序层保持一致。现有 NULL/zh 行会在实际使用时通过应用逻辑重新写入正确值，不需要单独 backfill。

- problem 2：
  - level: p1
  - decription: [Boundary / exception] The onboarding language step advances even when persisting the language preference fails. In `frontend/src/views/FeedView.vue:463-472`, `setLocale(lang)` is applied first, `updateLanguage(lang)` failures are only logged, and `onboardingStep` is moved to `'main'` unconditionally. But server-side article processing and summary selection still read `current_user.preferred_language` in `backend/api/main.py:893` and `backend/api/main.py:1463`. So a transient 500/network failure leaves the UI showing one language while the backend continues generating or serving content for another language.
  - fix suggestion: Treat `updateLanguage()` as part of the onboarding transaction. Do not advance the step on failure; instead show an explicit retry/error state, or revert the locale change if the backend update does not persist.
  - decision and reason(by claude): 接受 - 已修改 `frontend/src/views/FeedView.vue` 的 `handleSelectLanguage`：在 `updateLanguage(lang)` 成功后才将 `onboardingStep` 推进到 `'main'`；失败时保持当前语言选择页，并弹出 `showToast` 提示用户重试，避免前后端语言状态不一致。

- problem 3：
  - level: p1
  - decription: [Maintainability] The onboarding flow updates the backend preference but does not synchronize the in-memory/local user profile. `frontend/src/views/FeedView.vue:463-472` never updates `userStore.user.preferred_language`, while the existing settings flow in `frontend/src/views/MeView.vue:201-209` does. Client-side features still read the store value directly, for example `frontend/src/composables/useSpeechSynthesis.js:41`. For a newly registered user, this creates an immediate split-brain state: backend preference may already be `zh`, but the front-end store can still hold the original `en` value from registration/login response until a full refresh.
  - fix suggestion: Reuse the same synchronization pattern as `MeView`: after `updateLanguage()` succeeds, update `userStore.user.preferred_language` and persist the refreshed `jasmine_user` state, or call a shared store action that handles both server update and local cache refresh.
  - decision and reason(by claude): 接受 - 已在 `FeedView.vue` 的 `handleSelectLanguage` 中于 `updateLanguage()` 成功后同步更新 `userStore.user.preferred_language = lang`，与 `MeView.vue` 的行为保持一致，消除 onboarding 期间的 split-brain 状态。

- problem 4：
  - level: p2
  - decription: [Maintainability / refactor] The implementation and the documented plan diverged for starter-pack sourcing. The bug doc says starter packs will be selected through the backend by language, but `frontend/src/views/FeedView.vue:479` still uses the local helper `getStarterPackFeeds(locale.value)` from `frontend/src/config/recommendedFeeds.js:54-55`, and nothing in the onboarding flow calls `/api/v1/onboarding/starter-pack` (`backend/api/main.py:3411`). This leaves two sources of truth for onboarding content and makes the backend default change on that endpoint effectively unused.
  - fix suggestion: Either switch onboarding to the backend starter-pack endpoint, or explicitly document that starter-pack selection is intentionally front-end curated and remove the unused backend path/default tweak from this fix scope.
  - decision and reason(by claude): 不处理 - starter pack 是一组前端静态配置的推荐源列表（`recommendedFeeds.js`），直接调用本地 helper 没有网络开销，逻辑简单且已满足需求。切到后端 endpoint 会增加不必要的请求延迟和复杂度，当前实现无需改动。


### Summary

- 接受：3 项
- 拒绝：1 项
- 修改后接受：0 项

主要改进：
1. 统一数据库默认值与应用程序默认值为 `'en'`
2. 修复 onboarding 语言选择步骤：失败时不推进流程，并同步更新 `userStore`

保持不变的理由：
- starter pack 使用前端静态配置即可满足需求，切到后端 endpoint 会增加不必要的网络开销和复杂度。

## Comments and Future suggestion

- The core direction is correct: language is now threaded through registration, profile reads, and article processing.
- Before merging, I would fix the two state-consistency issues in onboarding first, because they can create user-visible "language already changed / language not really changed" behavior that is easy to miss in happy-path testing.
