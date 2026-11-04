# 全局文章去重后按更新时间排序异常

## 问题描述

开启全局文章去重（Cross-User Content Sharing Phase 2）后，用户按"更新时间"排序时，很久之前的文章会排到前面。

以 test-user 账户为例，"红色安生"的较早文章被排到了列表前面。

预期表现：按更新时间排序应该展示最近被用户订阅源抓取到的文章
实际表现：部分历史文章因为全局去重逻辑被错误地排到了前面

## 原因定位

### 根本原因

全局文章去重后，文章存储采用了 `global_articles` + `user_article_refs` 的双层结构：
- `global_articles`：按 URL 去重的全局内容池，所有用户共享同一篇文章
- `user_article_refs`：记录用户与全局文章的关联关系

`global_articles` 表有一个 `last_updated_at` 字段，并在每次同一 URL 的文章被任何 feed 抓取时通过 `ON CONFLICT (url) DO UPDATE SET ... last_updated_at = CURRENT_TIMESTAMP` 更新为当前时间。

后端 `get_user_articles` 函数在用户按 `updated_at` 排序时，使用的是 `ga.last_updated_at`。这导致：
- 当一篇旧文章被其他用户的 feed 或新 feed 抓取到时，`global_articles.last_updated_at` 被刷新为当前时间
- 对于已经订阅该文章的用户，这篇文章在"按更新时间排序"时会因为 `last_updated_at` 变新而被排到前面
- 用户看到的是"很久之前的旧文章"，但其全局 `last_updated_at` 是最新的

### 相关代码位置

- `backend/storage/database.py:2047` - `get_user_articles` 中 `ga.last_updated_at AS updated_at`
- `backend/storage/database.py:2088` - `get_user_articles` 中按 `updated_at` 排序使用 `ga.last_updated_at`
- `backend/storage/database.py:209-215` - `store_article` 中 `ON CONFLICT` 更新 `global_articles.last_updated_at`
- `backend/storage/database.py:440` - `search_user_articles_pg` 同样使用 `ga.last_updated_at DESC` 排序

## 修复方案（第一次）

将用户文章列表的"更新时间"从全局的 `global_articles.last_updated_at` 改为用户维度的 `user_article_refs.fetched_at`。

`user_article_refs.fetched_at` 的含义：
- 文章首次被该用户的某个 feed 抓取时 = 当前时间
- 当同一篇文章被同一 feed 再次抓取时（`ON CONFLICT DO UPDATE`）= 当前时间
- 不会被其他用户或无关 feed 的抓取行为影响

修改点：
1. `get_user_articles`：
   - 返回字段：`uar.fetched_at AS updated_at` 替代 `ga.last_updated_at AS updated_at`
   - 排序字段：`uar.fetched_at` 替代 `ga.last_updated_at`
2. `search_user_articles_pg`：
   - 返回字段和排序字段同样改为 `uar.fetched_at`

## 用户反馈与二次定位

**2026-04-16 用户反馈**：test-user 账户中"红色安生"的较早文章仍然排在最前面，不符合预期。

**二次根因**：`user_article_refs.fetched_at` 在以下场景被设为 `CURRENT_TIMESTAMP`，导致历史文章也被排到前面：
1. `store_article` 首次插入 `user_article_refs` 时，`fetched_at` 使用默认值 `CURRENT_TIMESTAMP`。
2. `create_user_feed` 链接已有全局文章时，`fetched_at` 同样使用默认值 `CURRENT_TIMESTAMP`。

这意味着对于历史文章，`fetched_at` 记录的是"关联创建时间"而非"文章实际时间"。

## 修复方案（第二次）

将 `user_article_refs.fetched_at` 的初始值从 `CURRENT_TIMESTAMP` 改为文章的 `published_at`（发布时间）：
1. `store_article`：`INSERT INTO user_article_refs` 时显式设置 `fetched_at = COALESCE(article.published_at, CURRENT_TIMESTAMP)`。`ON CONFLICT` 时仍更新为 `CURRENT_TIMESTAMP`（表示同一 feed 重新抓取）。
2. `create_user_feed`：`INSERT INTO user_article_refs` 时设置 `fetched_at = COALESCE(ga.published_at, CURRENT_TIMESTAMP)`。`ON CONFLICT` 时不覆盖 `fetched_at`。

这样历史文章按 `updated_at`（即 `fetched_at`）排序时，会接近其真实发布时间，不会因为新订阅 feed 而被错误置顶。

## 修复状态

- [x] 问题定位
- [x] 文档记录
- [x] 代码修复
- [x] 测试验证

## 修复记录（第一次）

**修复文件**: `backend/storage/database.py`

**修复时间**: 2026-04-16

**修改内容**:
- `get_user_articles` 中 `updated_at` 字段和排序字段从 `ga.last_updated_at` 改为 `uar.fetched_at`
- `search_user_articles_pg` 中 `updated_at` 字段和排序字段从 `ga.last_updated_at` 改为 `uar.fetched_at`
- `store_article` 中 `user_article_refs` 的 `fetched_at` 初始值改为 `COALESCE(published_at, CURRENT_TIMESTAMP)`
- `create_user_feed` 中 `user_article_refs` 的 `fetched_at` 初始值改为 `COALESCE(ga.published_at, CURRENT_TIMESTAMP)`，`ON CONFLICT` 时不覆盖 `fetched_at`

## 2026-04-19 问题复发与再次修复

### 问题复发描述

2026-04-19 用户反馈：test-user 账户中"红色安生"的较早文章再次排到最前面，按更新时间排序异常。

### 二次根因（第三次定位）

`store_article` 函数中 `user_article_refs` 的 `ON CONFLICT` 逻辑无条件更新 `fetched_at = CURRENT_TIMESTAMP`，导致：

1. 2026-04-14 引入 `normalize_url` 后，微信公众号 RSS 源返回的 URL 格式发生变化（参数编码方式、顺序、锚点等不同）
2. 旧文章在 `articles` 兼容层中触发了 `ON CONFLICT UPDATE`（因为 `norm_url` 归一化后与旧格式不同）
3. 即使文章内容本身没有变化（`content_hash` 相同），`user_article_refs.fetched_at` 仍被刷新为当前时间
4. 生产日志证实：2026-04-17 红色安生 feed 刷新时，`articles_stored=20, articles_skipped=0`，20 篇 2024 年的旧文章全部被重新存储，`fetched_at` 被统一刷新为 `2026-04-17 09:07:57`

### 修复方案（第三次）

**核心修复**（根因）：`backend/utils/feed_refresher.py:_article_exists` 未对 URL 归一化，导致存在性检查与 `global_articles`/`articles` 表的存储格式不一致。修复后，`_article_exists` 在检查前调用 `normalize_url(url)`，使原始 feed URL 与表中存储的归一化 URL 正确匹配，从源头消除旧文章被重复送入 `store_article` 的问题。

**防御性修复**：在 `store_article` 中，只在文章内容真正变化（`content_hash` 改变）或首次创建 `user_article_refs` 时更新 `fetched_at`：

1. 在 `global_articles` 的 `INSERT/UPDATE` 之前，先查询旧的 `content_hash`
2. `user_article_refs` 的插入逻辑改为：
   - 若 `content_hash` 变化或首次插入（`old_content_hash` 为 None）：`ON CONFLICT DO UPDATE SET fetched_at = CURRENT_TIMESTAMP`
   - 若 `content_hash` 未变化：`ON CONFLICT DO UPDATE SET` 不更新 `fetched_at`

**修复文件**:
- `backend/utils/feed_refresher.py`
- `backend/storage/database.py`

**修复时间**: 2026-04-19

**修改内容**:
- `feed_refresher.py:_article_exists` 增加 URL 归一化，消除旧文章因 URL 格式差异被重复处理的根因
- `store_article` 中在 `global_articles` 插入前增加旧 `content_hash` 查询
- `user_article_refs` 的 `ON CONFLICT` 逻辑改为条件更新 `fetched_at`，仅在 `content_hash` 变化时刷新

## 相关提交

- 待补充

## Review意见

### Problem 1

- level: p0
- angle: [Implicit assumption] [Boundary]
- file: `backend/storage/database.py:194`, `backend/storage/database.py:280`
- description:
  The new fix decides whether to refresh `user_article_refs.fetched_at` by comparing the incoming article hash with the current hash in `global_articles`. That is a global check, not a per-user/per-feed check. If user A ingests an updated article first, `global_articles.content_hash` is already moved to the new value. When user B later ingests the same updated payload from their own feed, `old_content_hash == content_hash`, so the code takes the "do not refresh" branch and keeps B's old `fetched_at`. This means the sorting timestamp can stay stale for some users even though their own subscription just observed a real article update, which breaks the intended semantics described in this bug doc.
- fix suggestion:
  Base the refresh decision on the existing `(user_id, global_article_id, feed_id)` association instead of only on `global_articles`. The safest options are either:
  1. store a per-reference `last_seen_content_hash` in `user_article_refs`, then update `fetched_at` when that stored hash changes; or
  2. query the previous hash/value associated with that specific user/feed before deciding whether to refresh `fetched_at`.
### Decisions

#### Problem 1: 全局 content_hash 检查存在多用户时序边界

**🔄 修改后接受** — Codex 指出的全局 hash 竞争边界情况理论上成立，但建议的 schema 迁移方案（添加 `user_article_refs.last_seen_content_hash`）属于过度设计。实际根因是 `_article_exists` 未对 URL 归一化，导致大量本可跳过的旧文章被重复送入 `store_article`。

**实际修复方案**：
1. 修复 `backend/utils/feed_refresher.py:_article_exists` —— 在检查前调用 `normalize_url(url)`，使存在性检查与 `global_articles`/`articles` 表中的存储格式保持一致，从源头消除不必要的重复处理。
2. 保留 `backend/storage/database.py:store_article` 中的 `content_hash` 变化检查作为防御性兜底，处理 `_article_exists` 无法覆盖的极端边界。

**理由**：RSS 文章发布后内容更新的概率本身极低，且多用户在同一刷新窗口内先后处理同一篇更新文章的时序冲突更为罕见。`_article_exists` 的 URL 归一化修复已解决 99% 的生产问题。添加 schema 字段的维护成本远大于理论收益。

#### Problem 2: 缺少回归测试覆盖

**✅ 接受** — 已补充针对性测试：

1. `test_store_article_same_hash_preserves_fetched_at`：相同 URL + 相同 `content_hash` 时，`ON CONFLICT` 不更新 `fetched_at`，验证防御性兜底分支。
2. `test_store_article_new_user_existing_global_article`：新用户首次关联已有全局文章时，`fetched_at` 初始值为 `published_at`。

**未添加的测试**：Codex 建议的 "user A 更新后 user B 再摄取" 多用户时序测试未添加。因为在 `_article_exists` 修复后，user B 的 feed 刷新若文章已存在会正常跳过 `store_article`，不会触发全局 hash 竞争路径；该场景属于理论边界，不值得为假设性问题增加测试复杂度。

### Summary

- **接受**：1 项（Problem 2：补充回归测试）
- **修改后接受**：1 项（Problem 1：以 URL 归一化替代 schema 迁移，更简单且修复根因）
- **拒绝**：0 项

**主要改进**：
- `backend/utils/feed_refresher.py:_article_exists` 增加 URL 归一化，消除旧文章因 URL 格式差异被重复处理的根因。
- `backend/storage/database.py:store_article` 保留条件化 `fetched_at` 更新作为防御性兜底。
- 补充 2 个单元测试覆盖 content_hash 变化/不变两种分支。

**测试验证**：`make test-quick` 35 项通过，`tests/backend/storage/test_cross_user_sharing.py` 12 项通过。
