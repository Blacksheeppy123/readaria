# Onboarding Experience 用户摘要语言混杂

## 问题描述

中文体验账户 `onboarding-experience-zh` 的 Feed 列表中，部分文章显示英文摘要，部分文章显示中文摘要。

### 用户操作步骤
1. 登录中文体验账户
2. 进入 Feed 列表
3. 浏览 starter pack 文章卡片

### 实际表现 vs 预期表现
- **实际**：同一中文体验账户中，摘要语言混杂，部分文章为英文摘要
- **预期**：中文体验账户的文章摘要应稳定显示中文

## 原因定位

### 根本原因

系统已经有 `article_summaries(global_article_id, language)` 这层按语言缓存，但读取链路并不彻底：

1. Feed 列表 / 详情 / TTS 元数据等场景虽然部分地方会查 `article_summaries`
2. 一旦对应语言缓存缺失，又会回退到 `global_articles.summary`
3. 而 `global_articles.summary` 在 RSS 刷新时会被最后一次生成摘要的用户语言覆盖

结果就是：
- 某篇共享文章如果最后一次被英文用户生成过摘要，`global_articles.summary` 可能是英文
- 中文体验账户如果该文章尚未生成 `zh` 的 `article_summaries`，就会读到英文

### 具体流程问题

1. `feed_refresher.py` 按用户语言生成摘要并写入 `article_summaries`
2. 同时调用 `update_article_summary(...)`
3. 旧实现会把这份语言特定摘要继续回写到 `global_articles.summary`
4. 其他用户读取文章时，如果自己的语言缓存缺失，就会读到这份被污染的共享摘要

### 相关代码位置
- `backend/utils/feed_refresher.py`
- `backend/storage/database.py`
  - `get_user_articles`
  - `get_user_article_by_url`
  - `get_user_article_metadata`
  - `get_user_article_metadata_with_fallback`
  - `search_user_articles_pg`
  - `update_article_summary`
- `scripts/backfill_experience_article_summaries.py`

## 修复方案

1. 读取文章时，统一优先使用 `article_summaries(language)`，仅在缺失时回退到 `global_articles.summary`
2. 停止将语言特定 AI 摘要回写到 `global_articles.summary`，避免继续污染共享字段
3. 提供回填脚本，为 `onboarding-experience-zh/en` 补齐缺失的语言化摘要缓存

## 修复状态

- [x] 问题定位
- [x] 文档记录
- [x] 代码修复
- [ ] 测试验证

## 修复记录

**修复文件**:
- `backend/storage/database.py`
- `backend/api/main.py`
- `scripts/backfill_experience_article_summaries.py`

**修复时间**: 2026-04-30

**修改内容**:
- 用户文章详情 / 搜索 / TTS 元数据统一支持按 `preferred_language` 读取 `article_summaries`
- 停止将语言特定摘要写回 `global_articles.summary`
- 新增体验账户摘要缓存回填脚本，用于修复历史缺失数据

## 验证建议

1. 本地运行相关单测
2. 线上执行：
   - `source venv/bin/activate`
   - `python scripts/backfill_experience_article_summaries.py --user onboarding-experience-zh`
3. 重新登录中文体验账户，确认 Feed 列表摘要恢复为中文

## 相关提交

- 待提交
