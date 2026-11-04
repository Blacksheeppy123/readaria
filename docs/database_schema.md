# Readaria 数据库设计文档

> **版本**: v4.0（开源自托管版）
> **更新日期**: 2026-11-04
> **Schema 唯一数据源**: [`backend/storage/schemas.sql`](../backend/storage/schemas.sql)

本文是当前表结构的概览。字段、约束、索引和触发器以 `schemas.sql` 为准；`backend/storage/migrations/` 中的增量 SQL 主要用于理解历史演进。

## 查看实际结构

在自托管部署目录执行（数据库名按实际配置调整）：

```bash
docker compose exec postgres psql -U postgres -d readaria -c '\dt'
docker compose exec postgres psql -U postgres -d readaria -c '\d <table_name>'
```

修改结构前，应同时检查 `schemas.sql`、相关迁移、`DatabaseManager` 查询以及调用方，不要仅依据本文修改数据库。

## ID 类型约定

| 表 | 主键类型 | 说明 |
|---|---|---|
| `users` | `VARCHAR(64)` | 所有 `user_id` 外键必须匹配 |
| `source_types` | `VARCHAR(64)` | 被文章和订阅源引用 |
| 其他使用自增主键的表 | `INTEGER` / `SERIAL` | 创建外键时保持类型一致 |
| `user_queues`、`user_playback_state` | `VARCHAR(64)`（`user_id`） | 每用户一行，同时引用 `users.id` |

## 表概览（22 张表）

### 用户与订阅源

- `users` — 用户账号、认证方式、语言相关的 TTS 音色偏好，以及自动刷新/自动播客开关。
- `user_sessions` — 登录会话的 token 哈希、过期时间和访问时间。
- `source_types` — 内容源类型，例如 RSS 及可扩展的平台类型。
- `user_feeds` — 用户订阅源、平台、抓取配置、活跃状态和最近抓取时间。

### 文章内容

- `articles` — 用户私有维度的文章兼容层，关联 `user_feeds`。
- `global_articles` — 跨用户共享的文章主表，按 URL 唯一，减少重复抓取与内容存储。
- `user_article_refs` — 用户与共享文章的关联，记录来源 feed、个人摘要、收藏、标签和笔记。

### 阅读与播放状态

- `user_saved_articles` — 收藏，兼容私有 `article_id` 与共享 `global_article_id`。
- `user_reading_history` — 已读状态、阅读时长和滚动位置。
- `audio_play_history` — 文章与播客播放历史及进度。
- `user_queues` — 每用户的 JSONB 播放队列。
- `user_playback_state` — 每用户的播放列表、当前位置、倍速和当前文章快照。
- `user_feedback` — 用户反馈、可选前端日志快照和处理状态。

### 抓取、验证与缓存

- `feed_update_logs` — 每次 feed 刷新的状态、文章计数和错误信息。
- `feed_validation` — 候选 feed 的有效性、语言、文章数量与最近验证结果。
- `tts_cache` — 共享文章对应的 TTS 文件元数据，按文章、音色和引擎去重。

### Podcast

- `podcasts` — 播客主表，包含生成状态、音频缓存键、来源和可选分享 token。
- `podcast_articles` — 播客与私有/共享文章的关联、顺序、重要性和时间段。
- `podcast_scripts` — 完整脚本、生成信息、预估时长和建议问题。
- `podcast_conversations` — 播客问答上下文与父子追问关系。
- `podcast_play_progress` — 每用户每播客的播放位置与完成状态。

### 用量观测

- `user_usage_daily` — 每日 TTS、播客和 AI 摘要用量统计。当前自托管版仅用于观测，不参与功能门控。

## 主要外键关系

```text
users
├── user_sessions
├── user_feeds
│   ├── articles
│   └── user_article_refs
├── user_saved_articles
├── user_reading_history
├── user_feedback
├── podcasts
│   ├── podcast_articles
│   ├── podcast_scripts
│   ├── podcast_conversations
│   └── podcast_play_progress
├── podcast_conversations
├── podcast_play_progress
├── user_usage_daily
├── audio_play_history
├── user_queues
├── user_playback_state
└── user_article_refs

source_types
├── user_feeds
├── articles
└── global_articles

global_articles
├── user_article_refs
├── user_saved_articles
├── user_reading_history
├── podcast_articles
├── audio_play_history
└── tts_cache

podcast_conversations
└── podcast_conversations (parent_conversation_id)
```

上述用户及内容关系大多使用 `ON DELETE CASCADE`，具体以字段定义为准。`audio_play_history.item_id` 是配合 `item_type` 使用的多态标识，不是直接外键；`feed_update_logs.feed_id` 也未声明外键。清理这些数据时不要假设数据库会自动级联。

## 设计要点

### 共享文章与私有元数据分离

`global_articles` 保存可复用的正文和抓取元数据，`user_article_refs` 保存用户视角的信息。`articles` 仍作为私有文章兼容层存在，因此部分关联表同时保留 `article_id` 与 `global_article_id` 两条路径。编写查询时必须明确使用哪条路径，并处理其中一列为 `NULL` 的情况。

### 音频缓存与播放记录

`tts_cache` 以共享文章、音色和引擎为边界记录缓存文件，允许跨用户复用相同音频。`audio_play_history` 则记录每个用户自己的播放状态，不应与缓存元数据混用。

### 时间戳与触发器

多数时间戳使用 `TIMESTAMP WITH TIME ZONE`，部分历史表使用不带时区的 `TIMESTAMP`。`update_updated_at_column()` 等触发器自动维护若干 `updated_at` / `last_updated_at` 字段。迁移或手动写入时应保留目标表原有的时间语义和触发器行为。

## 迁移文件

- 目录：[`backend/storage/migrations/`](../backend/storage/migrations/)
- 命名约定：`YYYY_MM_DD_<topic>.sql`（少量早期文件使用其他日期格式）
- 当前完整结构：[`backend/storage/schemas.sql`](../backend/storage/schemas.sql)
- 初始化入口：`manage.py db init --production` 使用当前初始化脚本；执行前检查目标数据库，避免在含数据的实例上重复初始化。

历史迁移可能描述已经调整的旧结构，不能替代当前 `schemas.sql`。
