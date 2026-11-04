# 新用户体验：内容池质量与订阅管理

## 问题描述

1. **Starter Pack 内容质量不稳定**
   - 有些源没有内容。
   - 有些源只有几句话加原始链接。
   - 有些源内容格式混乱（大量 HTML/广告），展示效果差。
   - 当前 `starterPackFeedsZh` 中混入了英文源（Hacker News、TechCrunch、GitHub Blog），中文用户会得到英文内容。

2. **订阅后列表为空**
   - 新用户点击 starter pack 一键订阅后，feed 列表是空的，没有初始文章，landing 体验差。

3. **Feed 筛选排序不合理**
   - Feed 页顶部的内容源筛选按 `created_at DESC`（订阅时间）排序，而不是按最近有文章更新的时间排序，用户无法快速找到活跃源。

## 根因定位

1. **Starter Pack 质量控制**
   - 后端 `get_starter_pack_feeds()` 在 `is_valid=true` 的源不足 `min_valid_count=4` 时会**回退到未验证的源**（`backend/storage/database.py`），导致低质量源进入推荐。
   - 前端 `frontend/src/config/recommendedFeeds.js` 的 `starterPackFeedsZh` 硬编码了英文源，且没有与后端 `feed_validation` 表打通。
   - `feed_validation` 表的候选池较小，只有部分源被录入验证。

2. **订阅后无内容**
   - `FeedView.vue` 的 `handleStarterPack()` 只调用了 `feedStore.fetchFeeds(true)` 和 `onRefresh()`，但 feed 刚被订阅时可能还没有文章。
   - 虽然全局文章复用已上线，但如果该源此前**从未被任何用户订阅过**，则 `global_articles` 中也没有缓存文章。

3. **Feed 排序**
   - `get_user_feeds()` 按 `created_at DESC` 排序，没有关联文章表取最近更新时间。

## 修复方案

### A. Starter Pack 质量控制

1. **移除回退逻辑**
   修改 `get_starter_pack_feeds(language, min_valid_count=4)`：若验证通过的源不足，**不再回退到未验证源**，而是直接返回已有的 valid feeds（哪怕只有 1 个），前端做降级展示（如提示"发现更多源"）。

2. **清理语言包**
   - `starterPackFeedsZh`：移除英文源，补充纯中文高质量源（如「豆瓣热门书评」「Solidot」「虎嗅」等需验证后确认）。
   - `starterPackFeedsEn`：保持现有英文源，补充更多国际主流源。

3. **扩大候选验证池**
   - 将 `recommendedFeeds` 中所有中文和英文源批量插入 `feed_validation` 表作为候选。
   - 复用现有的 `backend/services/feed_validation.py` 定时任务（建议每 4 小时运行）持续评估候选池。
   - 验证标准（已有）：
     - 至少 3 篇文章
     - 平均纯文本长度 ≥ 300
     - 近期 7 天内有更新
     - HTML/广告占比 ≤ 0.7

4. **外部优质源调研**
   为了建立更高质量的初始内容池，可以调研并接入以下公开资源：
   - **[timqian/chinese-independent-blogs](https://github.com/timqian/chinese-independent-blogs)**：提供 CSV + OPML，专注中文独立博客（编程/科技为主），可作为中文候选源池。
   - **[saveweb/rss-list](https://github.com/saveweb/rss-list)**：提供约 1,900 个中文独立博客/播客的 OPML，定期发布 release，可用于批量扩充验证池。
   - **[AboutRSS/ALL-about-RSS](https://github.com/AboutRSS/ALL-about-RSS)**：RSS 生态资源导航，可用于发现更多分类源。
   - **抓取竞品可行性**：
     - Feedly / Inoreader 的推荐源通常不直接暴露 OPML，需要用户手动导出。
     - 更可行的方案是从上述开源社区维护的 OPML/CSV 中定期导入高质量源，而不是抓取竞品网站。
   - **建议动作**：写一个脚本 `scripts/import_opml_to_validation.py`，读取 OPML/CSV 并写入 `feed_validation` 表，每月手动或自动更新一次。

### B. 订阅后自动获取内容

考虑到全局文章复用已上线，逻辑应调整为：

1. **后端新增批量刷新接口**（如 `POST /api/v1/feeds/refresh-batch`）
   - 接收 `feed_ids` 列表
   - 对每个 feed：
     - 先检查 `global_articles` 是否已有该 feed 的文章缓存
     - 若有，直接建立 `user_article_refs` 关联
     - 若无，触发一次 RSS 抓取（复用现有抓取逻辑），抓取后建立关联

2. **前端 `handleStarterPack()` 订阅完成后**
   - 收集成功订阅的 `feed_ids`
   - 调用 `POST /api/v1/feeds/refresh-batch`
   - 等待/轮询完成后调用 `onRefresh()` 刷新文章列表

3. **语言隔离（配合语言偏好修复）**
   - summary / tts / 播客的缓存需要按语言隔离。若同一篇文章对不同语言用户生成 summary，应分别缓存，避免中英文混用。
   - 在 `article_summaries` 等缓存表确保有 `language` 字段参与唯一索引。

### C. Feed 按最近更新时间排序

1. **方案 C1（推荐，低侵入）**
   - 在 `get_user_feeds()` 的 SQL 中 JOIN `global_articles`（或 `articles`）获取每个 feed 的 `MAX(published_at)`，按该时间 DESC 排序。
   - 优点：无需改表结构
   - 缺点：查询略复杂，但用户 feed 数量通常不多，性能可接受

2. **方案 C2（性能优化）**
   - 在 `user_feeds` 表新增 `last_article_at` 冗余字段
   - 在定时抓取任务中更新该字段
   - `get_user_feeds()` 直接按 `last_article_at DESC` 排序

建议先实施方案 C1，若后续有性能瓶颈再迁移到 C2。

## 验收标准
- [ ] Starter Pack 只返回 `is_valid=true` 的源，不再混入未验证源
- [ ] `starterPackFeedsZh` 不再包含英文源
- [ ] 新用户订阅 starter pack 后，文章列表在数秒内出现初始内容（已有缓存则立即出现）
- [ ] Feed 页顶部筛选按最近文章更新时间排序，而非订阅时间
- [ ] `feed_validation` 候选池扩大至 `recommendedFeeds` 全部源 + 外部优质源（至少调研并录入一批）
- [ ] 同篇文章不同语言用户的 summary/tts 缓存不冲突
