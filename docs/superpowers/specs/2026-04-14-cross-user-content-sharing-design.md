# 跨用户内容共享架构设计方案

> 文档状态：设计完成  
> 创建日期：2026-04-12  
> 关联文档：[todo.md](./todo.md) Phase 2 - 成本优化

---

## 1. 项目背景与目标

### 1.1 现状问题

当前 Jasmine 架构中，同一 RSS 源被多个用户订阅时存在严重冗余：

```
用户A订阅 https://example.com/rss
  → user_feeds.id = 1
    → 抓取文章 → articles.id = 100 (feed_id=1)
      → TTS缓存 key = "tts-1|alloy|article_100"

用户B订阅 https://example.com/rss  
  → user_feeds.id = 2
    → 抓取文章 → articles.id = 101 (feed_id=2)  ← 重复抓取
      → TTS缓存 key = "tts-1|alloy|article_101"  ← 重复生成
```

**资源浪费统计（估算）**：
- 文章存储：N 倍冗余（N = 订阅同一源的用户数）
- TTS 生成成本：N 倍 API 调用费用
- AI 摘要成本：N 倍 LLM 调用费用

### 1.2 设计目标

1. **文章去重**：相同 URL 的文章只存储一份
2. **TTS 共享**：同一文章的语音缓存跨用户复用
3. **AI 摘要共享**：全局生成一次，所有用户可见
4. **渐进迁移**：不影响现有功能，平滑过渡
5. **API 兼容**：前端无需修改
6. **新用户 Feed 预筛选**：基于 `global_articles` 数据，建立可验证的 starter pack 机制，确保推荐给新用户的 feed 已有高质量内容，避免空 feed 和低质量内容进入 onboarding 流程

---

## 2. 架构设计

### 2.1 核心数据模型

#### 2.1.1 全局文章表（global_articles）

存储去重后的文章内容，是跨用户共享的核心。

```sql
CREATE TABLE global_articles (
    id SERIAL PRIMARY KEY,
    url VARCHAR(2048) NOT NULL UNIQUE,  -- 文章唯一标识
    content_hash VARCHAR(64) NOT NULL,  -- SHA256哈希，用于检测内容变更
    title TEXT NOT NULL,
    author VARCHAR(255),
    published_at TIMESTAMP WITH TIME ZONE,
    content TEXT,
    summary TEXT,                       -- 全局AI摘要（跨用户共享）
    source_feed_url VARCHAR(1024),      -- 首次发现的RSS源URL
    source_type_id VARCHAR(64) REFERENCES source_types(id),
    word_count INTEGER,
    reading_time INTEGER,
    cover_image TEXT,
    language VARCHAR(10) DEFAULT 'zh',
    keywords JSONB DEFAULT '[]',
    entities JSONB DEFAULT '[]',
    sentiment_score DOUBLE PRECISION,
    first_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 核心索引
CREATE INDEX idx_global_articles_url ON global_articles(url);
CREATE INDEX idx_global_articles_content_hash ON global_articles(content_hash);
CREATE INDEX idx_global_articles_published ON global_articles(published_at DESC);
```

#### 2.1.2 用户文章关联表（user_article_refs）

维护用户与全局文章的订阅关系，支持用户级个性化字段。

```sql
CREATE TABLE user_article_refs (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    global_article_id INTEGER NOT NULL REFERENCES global_articles(id) ON DELETE CASCADE,
    legacy_article_id INTEGER,          -- Phase 1 兼容层：指向旧 articles.id
    feed_id INTEGER NOT NULL REFERENCES user_feeds(id) ON DELETE CASCADE,
    user_summary TEXT,                  -- 用户私有摘要（预留扩展）
    is_favorited BOOLEAN DEFAULT FALSE,
    folder_name VARCHAR(100),
    user_tags TEXT[],
    notes TEXT,
    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, global_article_id, feed_id)
);

-- 核心索引
CREATE INDEX idx_uar_user_feed ON user_article_refs(user_id, feed_id);
CREATE INDEX idx_uar_global_article ON user_article_refs(global_article_id);
CREATE INDEX idx_uar_user_article ON user_article_refs(user_id, global_article_id);
CREATE INDEX idx_uar_legacy_article ON user_article_refs(legacy_article_id);
```

#### 2.1.3 TTS 缓存表（tts_cache）

关联全局文章，实现跨用户的 TTS 缓存共享。

```sql
CREATE TABLE tts_cache (
    id SERIAL PRIMARY KEY,
    global_article_id INTEGER NOT NULL REFERENCES global_articles(id) ON DELETE CASCADE,
    voice VARCHAR(50) NOT NULL,
    engine VARCHAR(50) NOT NULL,        -- openai/azure/google/kokoro
    cache_key VARCHAR(255) NOT NULL UNIQUE,
    file_path VARCHAR(512) NOT NULL,
    file_size INTEGER,
    duration_seconds INTEGER,
    format VARCHAR(10) DEFAULT 'mp3',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_accessed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    access_count INTEGER DEFAULT 0,
    UNIQUE(global_article_id, voice, engine)
);

-- 核心索引
CREATE INDEX idx_tts_cache_article ON tts_cache(global_article_id);
CREATE INDEX idx_tts_cache_key ON tts_cache(cache_key);
CREATE INDEX idx_tts_cache_engine ON tts_cache(engine, voice);
```

### 2.2 数据流架构

#### 2.2.1 RSS 抓取流程（新）

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           RSS 抓取流程                                       │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  1. Scheduler 触发抓取 (feed_scheduler.py)                                   │
│         │                                                                    │
│         ▼                                                                    │
│  2. RSSFetcher.fetch_feed(feed_url)                                          │
│         │                                                                    │
│         ▼                                                                    │
│  3. 解析文章列表 → 每篇文章：                                                │
│         ├── 生成 content_hash = SHA256(content)                              │
│         └── 标准化 URL（去除 tracking 参数）                                 │
│         │                                                                    │
│         ▼                                                                    │
│  4. DatabaseManager.save_articles_batch()                                    │
│         │                                                                    │
│         ├───► 检查 global_articles.url 是否存在                              │
│         │         │                                                          │
│         │         ├───► 存在：比较 content_hash                              │
│         │         │         │                                                │
│         │         │         ├───► hash 相同：跳过内容更新                    │
│         │         │         └───► hash 不同：更新内容（版本控制预留）        │
│         │         │                                                            │
│         │         └───► 不存在：创建 global_articles 记录                    │
│         │                   │                                                │
│         │                   └───► 触发 AI 摘要生成（异步）                   │
│         │                                                                    │
│         └───► 创建 user_article_refs 关联                                    │
│                   (user_id, global_article_id, feed_id)                      │
│                                                                              │
│  5. TTS 预生成（Pro 用户白名单）                                             │
│         │                                                                    │
│         └───► 检查 tts_cache 是否已存在                                      │
│                   │                                                          │
│                   ├───► 存在：跳过                                           │
│                   └───► 不存在：生成并写入缓存                               │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### 2.2.2 TTS 播放流程（共享机制）

> **Phase 1 兼容说明**：外部 API 的 `{article_id}` 仍是 `legacy articles.id`，
> 服务层先做 `legacy_article_id → global_article_id` 映射，再进入共享缓存逻辑。

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         TTS 播放请求                                         │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  用户请求 GET /api/v1/tts/play/{article_id}                                  │
│         │                                                                    │
│         ▼                                                                    │
│  0. ID 映射（Phase 1 兼容层）                                                │
│         │                                                                    │
│         ├───► 查询 user_article_refs                                         │
│         │         WHERE legacy_article_id = %s                               │
│         │                                                                    │
│         ├───► 获取 global_article_id                                         │
│         │                                                                    │
│         └───► 无映射 → 返回 404                                              │
│                                                                              │
│         ▼                                                                    │
│  1. 权限检查（用户是否可访问该文章）                                         │
│         │                                                                    │
│         ├───► 查询 user_article_refs                                         │
│         │         WHERE user_id = %s AND global_article_id = %s              │
│         │                                                                    │
│         └───► 无权限 → 返回 403                                              │
│                                                                              │
│         ▼                                                                    │
│  2. 查询 TTS 缓存                                                            │
│         │                                                                    │
│         ├───► SELECT * FROM tts_cache                                        │
│         │         WHERE global_article_id = %s AND voice = %s                │
│         │                                                                    │
│         ├───► 命中：                                                         │
│         │         1. 更新 access_count++, last_accessed_at                   │
│         │         2. 返回 file_path 直接流式传输                             │
│         │                                                                    │
│         └───► 未命中：                                                       │
│                   1. 启动异步生成任务                                        │
│                   2. 返回 202 Accepted + 状态轮询接口                        │
│                   3. 生成完成后写入 tts_cache                                │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### 2.2.3 新用户 Starter Pack 内容预验证机制

全局文章表为新用户 onboarding 提供了内容可验证的基础：

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     Starter Pack Feed 预验证流程                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  1. 运营/系统维护一个候选 feed 池（多语言）                                    │
│         ├── 每个候选 feed 有：feed_url、期望语言、内容质量评分                  │
│         └── 通过定时脚本扫描或人工审核进入候选池                               │
│                                                                              │
│  2. 定时验证任务（每 4 小时运行一次）                                          │
│         │                                                                    │
│         ├── 对候选池中的每个 feed_url，执行 RSS 抓取测试                      │
│         ├── 解析文章列表，检查：                                              │
│         │    • 文章数量 >= 3（有内容）                                        │
│         │    • 平均内容长度 >= 300 字符（非摘要/链接聚合型）                   │
│         │    • 最近 7 天有更新（活跃源）                                      │
│         │    • HTML 标签占比合理（非纯广告/垃圾内容）                         │
│         │                                                                    │
│         └── 将验证结果写入 feed_validation 表：                               │
│              (feed_url, is_valid, last_validated_at, article_count,           │
│               avg_content_length, last_article_at, language)                  │
│                                                                              │
│  3. 新用户 onboarding 时，前端请求 /api/v1/onboarding/starter-pack            │
│         │                                                                    │
│         ├── 后端根据用户语言筛选候选 feed                                     │
│         ├── 只返回 feed_validation.is_valid = true 的 feed                    │
│         ├── 同时返回每个 feed 的最新文章数、最近更新时间                        │
│         └── 若有效 feed < 4，触发告警并启用兜底列表                           │
│                                                                              │
│  4. 用户点击 "Quick Start" 后                                                 │
│         ├── 创建 user_feeds 订阅                                              │
│         ├── 已有 global_articles 的文章通过 user_article_refs 立即关联        │
│         ├── 无需等待后台抓取，刷新文章列表即有内容                              │
│         └── 对于尚无 global_articles 的新 feed，触发首次异步抓取              │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

**关键收益**：
- 内容池质量可量化、可监控，不再依赖静态配置文件中的 "希望可用" 的 feed
- 不同语言的新用户只看到已验证有内容的同语言 feed
- 订阅后立即有内容（global_articles 已存在时），极大提升 landing 体验

### 2.3 API 兼容性策略

**原则**：所有现有 API 路径保持不变，外部 `article_id` 在 Phase 1 仍使用 legacy `articles.id`，内部通过 `user_article_refs` 建立 global_articles ↔ legacy_articles 映射。

#### 2.3.0 Public ID 兼容性策略（关键）

Phase 1 期间，**下游依赖（TTS、收藏、阅读历史、播客、搜索）继续消费 legacy `articles.id`**，不直接暴露 `global_articles.id`。原因：
- 这些表和 API 的 `article_id` 契约已被前端、TTS 播放、收藏状态等广泛依赖。
- 一次性全量迁移会导致边界过大，风险不可控。

**兼容层实现**：
1. `user_article_refs` 增加 `legacy_article_id` 字段（可空，Phase 1 期间由双写逻辑填充）。
2. 文章列表查询返回 `legacy_article_id as article_id`，而非 `ga.id`。
3. TTS、收藏、阅读状态等 API 仍按原有 `articles.id` 工作，内部如有需要再通过 `user_article_refs` 查找 `global_article_id`。
4. Phase 2（未来）再统一将 public API 的 `article_id` 迁移到 `global_articles.id`。

```sql
-- user_article_refs 增加 legacy_article_id
ALTER TABLE user_article_refs ADD COLUMN legacy_article_id INTEGER;
CREATE INDEX idx_uar_legacy_article ON user_article_refs(legacy_article_id);
```

#### 2.3.1 文章列表接口适配

```python
# /api/v1/feeds/{feed_id}/articles
async def get_feed_articles(feed_id: int, current_user: User):
    """
    新实现：从 user_article_refs + global_articles 联查
    对外暴露的 article_id 仍是 legacy articles.id，保证下游兼容
    """
    query = """
        SELECT 
            uar.legacy_article_id as article_id,  -- 兼容层：对外仍用旧 ID
            ga.title,
            ga.url,
            ga.summary,
            ga.content,
            ga.author,
            ga.published_at,
            ga.word_count,
            ga.reading_time,
            ga.cover_image,
            uar.fetched_at as created_at,
            uar.is_favorited,
            uar.folder_name,
            uar.user_tags,
            -- 阅读状态关联查询（仍用 legacy_article_id）
            urh.is_read,
            urh.read_at,
            urh.scroll_position
        FROM user_article_refs uar
        JOIN global_articles ga ON uar.global_article_id = ga.id
        LEFT JOIN user_reading_history urh 
            ON urh.user_id = uar.user_id 
            AND urh.article_id = uar.legacy_article_id
        WHERE uar.feed_id = %s 
          AND uar.user_id = %s
        ORDER BY ga.published_at DESC
        LIMIT %s OFFSET %s
    """
    # 返回结构与旧接口完全一致，article_id 仍是 legacy ID，前端无需修改
```

#### 2.3.2 分阶段迁移矩阵

| 表/模块 | Phase 1（当前） | Phase 2（未来） | 说明 |
|---------|----------------|----------------|------|
| `global_articles` | 新建，双写填充 | 主存储 | 去重后全局共享 |
| `user_article_refs` | 新建，含 `legacy_article_id` | 移除 `legacy_article_id`，`global_article_id` 成为主键 | 用户-文章订阅映射 |
| `articles` | **保留**，双写兼容 | 逐步废弃/归档 | 旧文章表 |
| `user_reading_history` | **不改**，继续引用 `articles.id` | 迁移到 `global_articles.id` | 阅读历史 |
| `user_saved_articles` | **不改**，继续引用 `articles.id` | 迁移到 `global_articles.id` | 收藏关系 |
| `podcast_articles` | **不改**，继续引用 `articles.id` | 迁移到 `global_articles.id` | 播客内容关联 |
| `audio_play_history` | **不改**，继续引用 `articles.id` | 迁移到 `global_articles.id` | 音频播放记录 |
| 文章列表 API | 返回 `legacy_article_id` | 返回 `global_articles.id` | 对外契约 |
| TTS/收藏/阅读 API | 输入/输出 `articles.id` | 输入/输出 `global_articles.id` | 对外契约 |

**Phase 1 的核心目标**：在不改变任何 public API 契约的前提下，完成存储层去重和 TTS/摘要成本节省。

---

## 3. 关键算法设计

### 3.1 内容哈希生成

```python
import hashlib
from bs4 import BeautifulSoup

def generate_content_hash(content: str, url: str = None) -> str:
    """
    生成文章内容哈希，用于去重和变更检测
    
    策略：
    1. 清洗 HTML 标签
    2. 规范化空白字符
    3. 截取前 5000 字符（平衡精度和性能）
    4. SHA256 哈希
    """
    # 清洗 HTML
    soup = BeautifulSoup(content or "", "html.parser")
    text = soup.get_text(separator=' ', strip=True)
    
    # 规范化
    text = ' '.join(text.split())  # 合并多余空白
    text = text.lower()  # 统一小写
    
    # 截取（避免过长内容影响性能）
    content_sample = text[:5000]
    
    # 混入 URL 作为盐值（防止完全不同文章恰好内容相似）
    if url:
        content_sample = f"{url}::{content_sample}"
    
    return hashlib.sha256(content_sample.encode('utf-8')).hexdigest()
```

### 3.2 URL 标准化

```python
from urllib.parse import urlparse, urlunparse, parse_qs, urlencode

def normalize_url(url: str) -> str:
    """
    标准化 URL，去除 tracking 参数
    
    处理的参数：
    - UTM 参数 (utm_source, utm_medium, etc.)
    - 常见跟踪参数 (fbclid, gclid, etc.)
    """
    TRACKING_PARAMS = {
        'utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 'utm_content',
        'fbclid', 'gclid', 'ttclid', 'wickedid', 'dclid', 'zanpid',
        'ref', 'referrer', 'source', 'from'
    }
    
    parsed = urlparse(url)
    
    # 过滤查询参数
    query_params = parse_qs(parsed.query)
    filtered_params = {
        k: v for k, v in query_params.items() 
        if k.lower() not in TRACKING_PARAMS
    }
    
    # 重建 URL
    new_query = urlencode(filtered_params, doseq=True)
    
    # 规范化路径（去除尾部斜杠）
    path = parsed.path.rstrip('/')
    
    return urlunparse((
        parsed.scheme.lower(),
        parsed.netloc.lower(),
        path,
        parsed.params,
        new_query,
        ''  # 去除 fragment
    ))
```

### 3.3 双写一致性保证

```python
class ArticleStorageManager:
    """
    双写阶段的一致性管理器
    """
    
    async def save_article_with_dual_write(
        self, 
        article: Dict, 
        user_id: str, 
        feed_id: int
    ) -> Tuple[int, bool]:
        """
        双写保存文章
        
        Returns:
            (global_article_id, is_new)
        """
        url = normalize_url(article['url'])
        content_hash = generate_content_hash(article['content'], url)
        
        async with self.transaction() as txn:
            # 1. 先读取旧 content_hash，用于判断是否是新文章或内容变更
            old_row = await txn.fetchrow("""
                SELECT id, content_hash FROM global_articles WHERE url = $1
            """, url)
            old_hash = old_row['content_hash'] if old_row else None
            
            # 2. 获取或创建 global_article
            global_article_id = await txn.fetchval("""
                INSERT INTO global_articles 
                    (url, content_hash, title, author, published_at, 
                     content, summary, source_feed_url, source_type_id,
                     word_count, reading_time, cover_image)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
                ON CONFLICT (url) DO UPDATE SET
                    content_hash = EXCLUDED.content_hash,
                    title = EXCLUDED.title,
                    author = EXCLUDED.author,
                    published_at = EXCLUDED.published_at,
                    content = EXCLUDED.content,
                    summary = EXCLUDED.summary,
                    source_feed_url = EXCLUDED.source_feed_url,
                    word_count = EXCLUDED.word_count,
                    reading_time = EXCLUDED.reading_time,
                    cover_image = EXCLUDED.cover_image,
                    last_updated_at = CURRENT_TIMESTAMP
                RETURNING id
            """, url, content_hash, article['title'], 
                article.get('author'), article.get('published_at'),
                article['content'], article.get('summary'),
                article.get('source'), 'rss',
                article.get('word_count'), article.get('reading_time'),
                article.get('cover_image'))
            
            # 3. 判断是否是新文章（之前不存在，或 content_hash 发生变化）
            is_new = (old_hash is None) or (old_hash != content_hash)
            
            # 4. 【双写】同时写入旧表（保持兼容性），并获取 legacy_article_id
            legacy_article_id = await txn.fetchval("""
                INSERT INTO articles 
                    (feed_id, source_type_id, title, url, author, published_at,
                     summary, content, content_hash, language, word_count,
                     reading_time, cover_image, source, tags, metadata)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16)
                ON CONFLICT (feed_id, url) DO UPDATE SET
                    title = EXCLUDED.title,
                    summary = EXCLUDED.summary,
                    content = EXCLUDED.content,
                    content_hash = EXCLUDED.content_hash,
                    updated_at = CURRENT_TIMESTAMP
                RETURNING id
            """, feed_id, 'rss', article['title'], url,
                article.get('author'), article.get('published_at'),
                article.get('summary'), article['content'], content_hash,
                article.get('language', 'zh'), article.get('word_count'),
                article.get('reading_time'), article.get('cover_image'),
                article.get('source'), json.dumps(article.get('tags', [])),
                json.dumps(article.get('metadata', {})))
            
            # 5. 创建用户关联，并记录 legacy_article_id（兼容层）
            await txn.execute("""
                INSERT INTO user_article_refs 
                    (user_id, global_article_id, legacy_article_id, feed_id)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (user_id, global_article_id, feed_id) DO UPDATE SET
                    legacy_article_id = EXCLUDED.legacy_article_id
            """, user_id, global_article_id, legacy_article_id, feed_id)
            
        return global_article_id, is_new
```

### 3.4 Starter Pack Feed 验证算法

```python
# backend/services/feed_validation.py

import asyncio
from datetime import datetime, timedelta
from typing import List, Dict
from bs4 import BeautifulSoup
import feedparser

from backend.storage.database import DatabaseManager

MIN_ARTICLE_COUNT = 3
MIN_AVG_CONTENT_LENGTH = 300
MAX_HTML_RATIO = 0.7
RECENCY_DAYS = 7


async def validate_candidate_feeds(db: DatabaseManager):
    """
    定时任务：每 4 小时运行一次，验证候选 feed 池的内容质量。
    """
    candidates = await db.fetch("""
        SELECT feed_url, feed_name, language FROM feed_validation
    """)
    
    for candidate in candidates:
        result = await evaluate_single_feed(candidate['feed_url'])
        
        await db.execute("""
            UPDATE feed_validation
            SET is_valid = $1,
                article_count = $2,
                avg_content_length = $3,
                last_article_at = $4,
                last_validated_at = CURRENT_TIMESTAMP,
                validation_metadata = $5
            WHERE feed_url = $6
        """,
            result['is_valid'],
            result['article_count'],
            result['avg_content_length'],
            result['last_article_at'],
            result['metadata'],
            candidate['feed_url']
        )


async def evaluate_single_feed(feed_url: str) -> Dict:
    """
    抓取并评估单个 feed 的内容质量。
    """
    try:
        # 使用现有 RSSFetcher 或 feedparser 抓取
        parsed = feedparser.parse(feed_url)
        entries = parsed.entries[:20]  # 最多评估前 20 条
        
        if len(entries) < MIN_ARTICLE_COUNT:
            return _invalid_result("文章数量不足")
        
        content_lengths = []
        recent_count = 0
        last_article_at = None
        html_heavy_count = 0
        
        for entry in entries:
            content = _extract_content(entry)
            plain_text = BeautifulSoup(content, "html.parser").get_text(separator=' ', strip=True)
            content_lengths.append(len(plain_text))
            
            # HTML 占比检查
            if len(content) > 0 and len(plain_text) / len(content) < (1 - MAX_HTML_RATIO):
                html_heavy_count += 1
            
            # 时间检查
            published = _parse_published_at(entry)
            if published:
                if not last_article_at or published > last_article_at:
                    last_article_at = published
                if published > datetime.now(published.tzinfo) - timedelta(days=RECENCY_DAYS):
                    recent_count += 1
        
        avg_length = sum(content_lengths) // max(len(content_lengths), 1)
        html_ratio = html_heavy_count / max(len(entries), 1)
        
        is_valid = (
            len(entries) >= MIN_ARTICLE_COUNT and
            avg_length >= MIN_AVG_CONTENT_LENGTH and
            recent_count >= 1 and
            html_ratio <= MAX_HTML_RATIO
        )
        
        return {
            'is_valid': is_valid,
            'article_count': len(entries),
            'avg_content_length': avg_length,
            'last_article_at': last_article_at,
            'metadata': {
                'recent_count': recent_count,
                'html_heavy_ratio': html_ratio,
                'reason': None if is_valid else _reason_text(
                    avg_length, recent_count, html_ratio
                )
            }
        }
        
    except Exception as e:
        return _invalid_result(f"抓取异常: {str(e)}")


def _extract_content(entry) -> str:
    """从 feed entry 中提取最完整的内容"""
    if hasattr(entry, 'content'):
        return entry.content[0].value
    return getattr(entry, 'summary', '') or getattr(entry, 'description', '')


def _parse_published_at(entry) -> datetime:
    """解析 entry 的发布时间"""
    import time
    published_parsed = getattr(entry, 'published_parsed', None)
    if published_parsed:
        return datetime.fromtimestamp(time.mktime(published_parsed))
    return None


def _invalid_result(reason: str) -> Dict:
    return {
        'is_valid': False,
        'article_count': 0,
        'avg_content_length': 0,
        'last_article_at': None,
        'metadata': {'reason': reason}
    }


def _reason_text(avg_length, recent_count, html_ratio) -> str:
    if avg_length < MIN_AVG_CONTENT_LENGTH:
        return "内容长度不足"
    if recent_count < 1:
        return "近期无更新"
    if html_ratio > MAX_HTML_RATIO:
        return "HTML/广告占比过高"
    return "未知"
```

---

## 4. 迁移策略

### 4.1 三阶段迁移计划

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         渐进式迁移时间线                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  Week 1-2: 双写阶段                                                          │
│  ┌─────────────┐                                                             │
│  │ • 部署新表结构                                                             │
│  │ • 修改抓取逻辑，新文章双写                                                 │
│  │ • 查询仍走旧表                                                             │
│  │ • 每日运行一致性校验脚本                                                   │
│  └─────────────┘                                                             │
│         │                                                                    │
│         ▼                                                                    │
│  Week 3: 切换阶段                                                            │
│  ┌─────────────┐                                                             │
│  │ • 查询切换到新架构                                                         │
│  │ • 旧表停止写入                                                           │
│  │ • 监控错误率和性能                                                         │
│  │ • 准备回滚方案                                                             │
│  └─────────────┘                                                             │
│         │                                                                    │
│         ▼                                                                    │
│  Week 4+: 清理阶段（可选）                                                   │
│  ┌─────────────┐                                                             │
│  │ • 历史数据迁移（低优先级）                                                 │
│  │ • 删除旧表（确认稳定后）                                                   │
│  │ • 清理双写代码                                                             │
│  └─────────────┘                                                             │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 4.2 数据库迁移脚本

```sql
-- =============================================
-- 迁移脚本: 001_create_global_article_tables.sql
-- 运行时机: 双写阶段开始前
-- =============================================

-- 1. 创建全局文章表
CREATE TABLE IF NOT EXISTS global_articles (
    id SERIAL PRIMARY KEY,
    url VARCHAR(2048) NOT NULL UNIQUE,
    content_hash VARCHAR(64) NOT NULL,
    title TEXT NOT NULL,
    author VARCHAR(255),
    published_at TIMESTAMP WITH TIME ZONE,
    content TEXT,
    summary TEXT,
    source_feed_url VARCHAR(1024),
    source_type_id VARCHAR(64) REFERENCES source_types(id),
    word_count INTEGER,
    language VARCHAR(10) DEFAULT 'zh',
    keywords JSONB DEFAULT '[]',
    entities JSONB DEFAULT '[]',
    sentiment_score DOUBLE PRECISION,
    first_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. 创建索引
CREATE INDEX idx_global_articles_url ON global_articles(url);
CREATE INDEX idx_global_articles_content_hash ON global_articles(content_hash);
CREATE INDEX idx_global_articles_published ON global_articles(published_at DESC);
CREATE INDEX idx_global_articles_first_seen ON global_articles(first_seen_at);

-- 3. 创建全文搜索索引
CREATE INDEX idx_global_articles_title_search 
    ON global_articles USING GIN(to_tsvector('simple', title));
CREATE INDEX idx_global_articles_content_search 
    ON global_articles USING GIN(to_tsvector('simple', COALESCE(content, summary)));

-- 4. 创建用户文章关联表
CREATE TABLE IF NOT EXISTS user_article_refs (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    global_article_id INTEGER NOT NULL REFERENCES global_articles(id) ON DELETE CASCADE,
    legacy_article_id INTEGER,          -- Phase 1 兼容层：指向旧 articles.id
    feed_id INTEGER NOT NULL REFERENCES user_feeds(id) ON DELETE CASCADE,
    user_summary TEXT,
    is_favorited BOOLEAN DEFAULT FALSE,
    folder_name VARCHAR(100),
    user_tags TEXT[],
    notes TEXT,
    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, global_article_id, feed_id)
);

CREATE INDEX idx_uar_user_feed ON user_article_refs(user_id, feed_id);
CREATE INDEX idx_uar_global_article ON user_article_refs(global_article_id);
CREATE INDEX idx_uar_user_article ON user_article_refs(user_id, global_article_id);
CREATE INDEX idx_uar_legacy_article ON user_article_refs(legacy_article_id);

-- 5. 创建 TTS 缓存表
CREATE TABLE IF NOT EXISTS tts_cache (
    id SERIAL PRIMARY KEY,
    global_article_id INTEGER NOT NULL REFERENCES global_articles(id) ON DELETE CASCADE,
    voice VARCHAR(50) NOT NULL,
    engine VARCHAR(50) NOT NULL,
    cache_key VARCHAR(255) NOT NULL UNIQUE,
    file_path VARCHAR(512) NOT NULL,
    file_size INTEGER,
    duration_seconds INTEGER,
    format VARCHAR(10) DEFAULT 'mp3',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_accessed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    access_count INTEGER DEFAULT 0,
    UNIQUE(global_article_id, voice, engine)
);

CREATE INDEX idx_tts_cache_article ON tts_cache(global_article_id);
CREATE INDEX idx_tts_cache_key ON tts_cache(cache_key);

-- 6. Feed 预验证表（支撑 Starter Pack 质量筛选）
CREATE TABLE IF NOT EXISTS feed_validation (
    id SERIAL PRIMARY KEY,
    feed_url VARCHAR(2048) NOT NULL UNIQUE,
    feed_name VARCHAR(255),
    language VARCHAR(10) DEFAULT 'zh',
    is_valid BOOLEAN DEFAULT false,
    article_count INTEGER DEFAULT 0,
    avg_content_length INTEGER DEFAULT 0,
    last_article_at TIMESTAMP WITH TIME ZONE,
    last_validated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    validation_metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_feed_validation_valid ON feed_validation(is_valid, language);
CREATE INDEX idx_feed_validation_validated_at ON feed_validation(last_validated_at);

-- 7. 更新时间触发器（使用新函数名，避免覆盖生产环境现有的 update_updated_at_column）
CREATE OR REPLACE FUNCTION update_last_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.last_updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_global_articles_updated_at 
    BEFORE UPDATE ON global_articles 
    FOR EACH ROW EXECUTE FUNCTION update_last_updated_at_column();

-- feed_validation 使用 updated_at 字段，需要单独的触发器函数
CREATE OR REPLACE FUNCTION update_feed_validation_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_feed_validation_updated_at 
    BEFORE UPDATE ON feed_validation 
    FOR EACH ROW EXECUTE FUNCTION update_feed_validation_updated_at_column();
```

### 4.3 历史数据迁移脚本（可选）

```sql
-- =============================================
-- 迁移脚本: 002_migrate_historical_data.sql
-- 运行时机: 切换阶段后，低峰期执行
-- 说明: 将旧表数据迁移到新架构
-- =============================================

-- 1. 迁移文章到 global_articles
-- 注意：此脚本必须在应用层执行（或创建 PL/Python 函数），
-- 因为 PostgreSQL 原生不支持 Python/URL 解析库的 SHA256 规范化逻辑。
-- 以下展示应用层迁移的核心 SQL 结构，实际 URL 需先经 normalize_url() 处理。
INSERT INTO global_articles (
    url, content_hash, title, author, published_at,
    content, summary, source_feed_url, source_type_id,
    word_count, reading_time, cover_image, language,
    first_seen_at, last_updated_at
)
SELECT 
    normalized_url,  -- 应用层已调用 normalize_url(a.url)
    encode(digest(COALESCE(a.content, ''), 'sha256'), 'hex') as content_hash,
    a.title,
    a.author,
    a.published_at,
    a.content,
    a.summary,
    a.source as source_feed_url,
    a.source_type_id,
    a.word_count,
    a.reading_time,
    a.cover_image,
    a.language,
    a.created_at as first_seen_at,
    a.updated_at as last_updated_at
FROM (
    -- 子查询去重：同一 normalized_url 只保留最新的一条
    SELECT DISTINCT ON (normalized_url) *
    FROM (
        SELECT *, normalize_url(url) as normalized_url FROM articles
    ) sub
    ORDER BY normalized_url, updated_at DESC
) a
WHERE NOT EXISTS (
    SELECT 1 FROM global_articles ga WHERE ga.url = a.normalized_url
)
ON CONFLICT (url) DO NOTHING;

-- 2. 创建用户关联（URL 必须经过同样的 normalize_url 处理）
INSERT INTO user_article_refs (
    user_id, global_article_id, legacy_article_id, feed_id, fetched_at
)
SELECT 
    uf.user_id,
    ga.id as global_article_id,
    a.id as legacy_article_id,
    a.feed_id,
    a.created_at as fetched_at
FROM articles a
JOIN user_feeds uf ON a.feed_id = uf.id
JOIN global_articles ga ON ga.url = normalize_url(a.url)
ON CONFLICT (user_id, global_article_id, feed_id) DO NOTHING;

-- 3. 统计报告
SELECT 
    'global_articles' as table_name,
    COUNT(*) as count
FROM global_articles
UNION ALL
SELECT 
    'user_article_refs' as table_name,
    COUNT(*) as count
FROM user_article_refs;
```

---

## 5. 测试方案

### 5.1 单元测试

```python
# tests/unit/test_content_hash.py

import pytest
from backend.utils.content_hash import generate_content_hash, normalize_url

class TestContentHash:
    def test_same_content_same_hash(self):
        content = "这是一篇测试文章。"
        hash1 = generate_content_hash(content)
        hash2 = generate_content_hash(content)
        assert hash1 == hash2
        assert len(hash1) == 64  # SHA256 hex length
    
    def test_html_tags_removed(self):
        content_with_html = "<p>这是一篇测试文章。</p>"
        content_plain = "这是一篇测试文章。"
        hash1 = generate_content_hash(content_with_html)
        hash2 = generate_content_hash(content_plain)
        assert hash1 == hash2
    
    def test_whitespace_normalized(self):
        content1 = "这是   一篇    测试文章。"
        content2 = "这是 一篇 测试文章。"
        hash1 = generate_content_hash(content1)
        hash2 = generate_content_hash(content2)
        # 注意：根据策略决定是否合并所有空白
        # 这里假设我们合并多余空白
        assert hash1 == hash2

class TestURLNormalization:
    def test_remove_utm_params(self):
        url = "https://example.com/article?utm_source=newsletter&utm_medium=email"
        normalized = normalize_url(url)
        assert "utm_source" not in normalized
        assert "utm_medium" not in normalized
        assert normalized == "https://example.com/article"
    
    def test_preserve_essential_params(self):
        url = "https://example.com/article?id=123&page=2&utm_source=test"
        normalized = normalize_url(url)
        assert "id=123" in normalized
        assert "page=2" in normalized
        assert "utm_source" not in normalized
```

### 5.1.2 Feed 质量验证单元测试

```python
# tests/unit/test_feed_validation.py

import pytest
from datetime import datetime, timedelta
from backend.services.feed_validation import evaluate_single_feed, _extract_content

class TestFeedValidation:
    def test_empty_feed_invalid(self):
        """空 feed 应判定为无效"""
        result = evaluate_single_feed("https://test.example.com/empty")
        assert result['is_valid'] is False
        assert result['metadata']['reason'] == "文章数量不足"
    
    def test_short_content_feed_invalid(self):
        """内容过短的 feed 应判定为无效"""
        # Mock 数据：每篇文章只有 50 字符
        result = evaluate_single_feed("https://test.example.com/short")
        assert result['is_valid'] is False
        assert "内容长度不足" in result['metadata']['reason']
    
    def test_stale_feed_invalid(self):
        """长期未更新的 feed 应判定为无效"""
        # Mock 数据：所有文章都是 30 天前的
        result = evaluate_single_feed("https://test.example.com/stale")
        assert result['is_valid'] is False
        assert "近期无更新" in result['metadata']['reason']
    
    def test_high_quality_feed_valid(self):
        """高质量 feed 应判定为有效"""
        result = evaluate_single_feed("https://test.example.com/good")
        assert result['is_valid'] is True
        assert result['article_count'] >= 3
        assert result['avg_content_length'] >= 300
        assert result['last_article_at'] is not None
```

### 5.2 集成测试

```python
# tests/integration/test_cross_user_sharing.py

import pytest
import asyncio

class TestCrossUserSharing:
    """
    测试跨用户内容共享核心流程
    """
    
    async def test_same_article_shared_between_users(self, db, test_users):
        """
        测试：两个用户订阅同一 RSS 源，文章只存储一次
        """
        user_a, user_b = test_users[0], test_users[1]
        feed_url = "https://test.example.com/rss"
        
        # 1. 两个用户订阅同一源
        feed_a = await create_test_feed(db, user_a.id, feed_url)
        feed_b = await create_test_feed(db, user_b.id, feed_url)
        
        # 2. 模拟抓取（同一篇文章）
        article_data = {
            "title": "Test Article",
            "url": "https://test.example.com/post/1",
            "content": "This is test content.",
            "published_at": "2026-01-01T00:00:00Z"
        }
        
        # 3. 分别为两个用户保存
        global_id_a = await save_article_for_user(
            db, article_data, user_a.id, feed_a.id
        )
        global_id_b = await save_article_for_user(
            db, article_data, user_b.id, feed_b.id
        )
        
        # 4. 验证：global_article_id 相同
        assert global_id_a == global_id_b
        
        # 5. 验证：global_articles 表中只有一条记录
        count = await db.fetchval(
            "SELECT COUNT(*) FROM global_articles WHERE url = $1",
            article_data["url"]
        )
        assert count == 1
        
        # 6. 验证：user_article_refs 表中有两条记录
        ref_count = await db.fetchval(
            "SELECT COUNT(*) FROM user_article_refs WHERE global_article_id = $1",
            global_id_a
        )
        assert ref_count == 2
    
    async def test_tts_cache_shared(self, db, test_users):
        """
        测试：TTS 缓存在用户间共享
        """
        user_a, user_b = test_users[0], test_users[1]
        
        # 1. 创建共享文章
        global_article_id = await create_test_global_article(db)
        
        # 2. 用户 A 请求 TTS
        cache_key_a = await request_tts(
            db, global_article_id, user_a.id, voice="alloy"
        )
        
        # 3. 用户 B 请求同一文章 TTS
        cache_key_b = await request_tts(
            db, global_article_id, user_b.id, voice="alloy"
        )
        
        # 4. 验证：使用相同缓存
        assert cache_key_a == cache_key_b
        
        # 5. 验证：tts_cache 表中只有一条记录
        cache_count = await db.fetchval(
            "SELECT COUNT(*) FROM tts_cache WHERE global_article_id = $1",
            global_article_id
        )
        assert cache_count == 1
        
        # 6. 验证：access_count 为 2
        access_count = await db.fetchval(
            "SELECT access_count FROM tts_cache WHERE global_article_id = $1",
            global_article_id
        )
        assert access_count == 2
    
    async def test_starter_pack_only_returns_validated_feeds(self, db, client):
        """
        测试：Starter Pack API 只返回已验证的高质量 feed
        """
        # 1. 插入一个有效 feed 和一个无效 feed
        await db.execute("""
            INSERT INTO feed_validation 
                (feed_url, feed_name, language, is_valid, article_count, avg_content_length)
            VALUES 
                ('https://valid.example.com/rss', 'Valid Feed', 'zh', true, 10, 1200),
                ('https://invalid.example.com/rss', 'Invalid Feed', 'zh', false, 1, 50)
        """)
        
        # 2. 为有效 feed 预写入 global_articles
        await db.execute("""
            INSERT INTO global_articles 
                (url, content_hash, title, source_feed_url, language)
            VALUES 
                ('https://valid.example.com/post/1', 'hash1', 'Post 1', 'https://valid.example.com/rss', 'zh')
        """)
        
        # 3. 调用 onboarding starter-pack 接口
        response = await client.get("/api/v1/onboarding/starter-pack?language=zh")
        assert response.status_code == 200
        data = response.json()
        
        # 4. 验证只返回有效 feed
        feed_urls = [f['feed_url'] for f in data['feeds']]
        assert 'https://valid.example.com/rss' in feed_urls
        assert 'https://invalid.example.com/rss' not in feed_urls
        
        # 5. 验证返回了文章统计信息
        valid_feed = next(f for f in data['feeds'] if f['feed_url'] == 'https://valid.example.com/rss')
        assert valid_feed['article_count'] == 10
        assert valid_feed['avg_content_length'] == 1200
```

### 5.3 数据一致性校验脚本

```python
# scripts/validate_migration.py

import asyncio
import logging
from backend.storage.database import DatabaseManager

logger = logging.getLogger(__name__)

async def validate_migration(db: DatabaseManager):
    """
    验证新旧架构数据一致性
    应在双写阶段每日运行
    """
    results = {
        "passed": True,
        "checks": []
    }
    
    # 检查 1：URL 覆盖度
    # 必须在应用层调用 normalize_url() 进行比较，与双写/迁移逻辑保持一致
    old_urls = {normalize_url(row['url']) async for row in db.iter("SELECT DISTINCT url FROM articles")}
    global_urls = {row['url'] async for row in db.iter("SELECT url FROM global_articles")}
    covered = old_urls & global_urls
    coverage = (len(covered) / len(old_urls) * 100.0) if old_urls else 100.0
    
    check_result = {
        "name": "URL Coverage (Normalized)",
        "metric": f"{coverage:.2f}%",
        "threshold": "> 99%",
        "passed": coverage > 99
    }
    results["checks"].append(check_result)
    if not check_result["passed"]:
        results["passed"] = False
        logger.error(f"URL coverage too low: {coverage}%")
    
    # 检查 2：文章数量匹配
    old_count = await db.fetchval("SELECT COUNT(*) FROM articles")
    new_count = await db.fetchval("SELECT COUNT(*) FROM user_article_refs")
    
    count_diff = abs(old_count - new_count)
    check_result = {
        "name": "Article Count Match",
        "metric": f"diff = {count_diff}",
        "threshold": "< 100",
        "passed": count_diff < 100
    }
    results["checks"].append(check_result)
    
    # 检查 3：TTS 缓存有效性
    invalid_tts = await db.fetchval("""
        SELECT COUNT(*) FROM tts_cache tc
        WHERE NOT EXISTS (
            SELECT 1 FROM global_articles ga WHERE ga.id = tc.global_article_id
        )
    """)
    
    check_result = {
        "name": "TTS Cache Orphans",
        "metric": f"orphans = {invalid_tts}",
        "threshold": "= 0",
        "passed": invalid_tts == 0
    }
    results["checks"].append(check_result)
    
    # 输出报告
    logger.info("=" * 50)
    logger.info("Migration Validation Report")
    logger.info("=" * 50)
    for check in results["checks"]:
        status = "✅ PASS" if check["passed"] else "❌ FAIL"
        logger.info(f"{status} | {check['name']}: {check['metric']} (threshold: {check['threshold']})")
    
    return results

if __name__ == "__main__":
    # 可配置为定时任务或 CI 步骤
    asyncio.run(validate_migration())
```

---

## 6. 性能优化

### 6.1 数据库查询优化

```sql
-- 优化后的文章列表查询（使用游标分页替代 OFFSET）
-- 适用于无限滚动场景

-- 首次查询
SELECT 
    ga.id, ga.title, ga.url, ga.summary, ga.published_at
FROM user_article_refs uar
JOIN global_articles ga ON uar.global_article_id = ga.id
WHERE uar.user_id = $1 
  AND uar.feed_id = $2
  AND ga.published_at < $3  -- 上一页最后一条的时间
ORDER BY ga.published_at DESC
LIMIT $4;

-- 关键复合索引
CREATE INDEX idx_uar_user_feed_published 
    ON user_article_refs(user_id, feed_id, fetched_at DESC)
    INCLUDE (global_article_id);
```

### 6.2 缓存策略

```python
# Redis 缓存层

class ArticleCache:
    """
    多级缓存策略
    """
    
    # L1: 热点文章（最近7天）
    HOT_ARTICLE_TTL = 3600  # 1小时
    
    # L2: 普通文章
    NORMAL_ARTICLE_TTL = 300  # 5分钟
    
    async def get_article(self, global_article_id: int):
        # 1. 尝试从 Redis 获取
        cache_key = f"article:{global_article_id}"
        cached = await redis.get(cache_key)
        if cached:
            return json.loads(cached)
        
        # 2. 从数据库获取
        article = await db.fetchrow(
            "SELECT * FROM global_articles WHERE id = $1",
            global_article_id
        )
        
        # 3. 写入缓存
        if article:
            ttl = self.HOT_ARTICLE_TTL if self._is_hot(article) else self.NORMAL_ARTICLE_TTL
            await redis.setex(cache_key, ttl, json.dumps(dict(article)))
        
        return article
    
    def _is_hot(self, article):
        """判断是否为热点文章（最近7天发布）"""
        from datetime import datetime, timedelta
        return article['published_at'] > datetime.now() - timedelta(days=7)
```

### 6.3 预期性能指标

| 指标 | 当前架构 | 新架构（预期） | 优化幅度 |
|------|----------|----------------|----------|
| 存储空间（文章） | N × 文章大小 | 1 × 文章大小 | N 倍减少 |
| TTS API 调用 | N × 请求/文章 | 1 × 请求/文章 | N 倍减少 |
| AI 摘要调用 | N × 请求/文章 | 1 × 请求/文章 | N 倍减少 |
| 文章列表查询 | 50ms | 30ms | 40% 提升 |
| 内存缓存命中率 | 60% | 85% | 25% 提升 |

---

## 7. 风险评估与回滚方案

### 7.1 风险矩阵

| 风险点 | 概率 | 影响 | 缓解措施 | 责任人 |
|--------|------|------|----------|--------|
| 数据不一致 | 中 | 高 | 双写阶段 + 校验脚本 | 后端团队 |
| 查询性能下降 | 低 | 高 | 充分索引 + 缓存 + 压测 | DBA |
| 迁移失败需回滚 | 低 | 高 | 蓝绿部署 + 快速切换开关 | 运维团队 |
| TTS 缓存丢失 | 低 | 中 | 备份原缓存 + 预热新缓存 | 后端团队 |
| API 兼容性问题 | 低 | 高 | 完整回归测试 | QA团队 |
| 数据库锁竞争 | 中 | 中 | 分时段迁移 + 事务优化 | DBA |

### 7.2 回滚方案

```python
# core/config/settings.py

class Settings:
    # 功能开关
    USE_GLOBAL_ARTICLE_ARCHITECTURE: bool = True  # 可快速回滚
    DUAL_WRITE_MODE: bool = False  # 双写阶段开启
    
    # 回滚策略
    FALLBACK_TO_LEGACY_QUERY: bool = False  # 紧急回滚开关
```

**回滚触发条件：**
1. 错误率 > 1%（持续 5 分钟）
2. 平均响应时间 > 500ms（持续 10 分钟）
3. 数据一致性校验失败
4. 用户投诉文章丢失/重复

**回滚步骤（5分钟内完成）：**
1. 切换 `FALLBACK_TO_LEGACY_QUERY = True`
2. 重启 API 服务
3. 查询自动切回旧表
4. 分析问题，修复后重新上线

---

## 8. 实施计划

### 8.1 任务分解

```
Week 1: 基础设施
├── Day 1-2: 数据库迁移脚本编写与测试（含 feed_validation 表）
├── Day 3-4: 内容哈希与 URL 标准化工具
├── Day 5: Code Review + 合并

Week 2: 核心逻辑 + Feed 验证
├── Day 1-2: 双写逻辑实现（ArticleStorageManager）
├── Day 3: 查询适配层（API 兼容性）
├── Day 4: Feed 验证服务实现（抓取、评分、落库）
├── Day 5: 集成测试（含跨用户共享 + Feed 验证）+ Bug 修复

Week 3: 切换与监控
├── Day 1: 灰度发布（5% 流量）
├── Day 2-3: 全量切换 + 监控
├── Day 4: 性能优化（根据监控数据）
├── Day 4: 部署 feed 验证定时任务，填充首批候选 feed 数据
└── Day 5: 稳定性验证，确认核心 feeds 已通过质量校验

Week 4: 优化与清理 + Onboarding 前置
├── Day 1-2: 历史数据迁移（低峰期）
├── Day 3: TTS 缓存预热优化
├── Day 4: 提供 `/api/v1/onboarding/starter-pack` 接口，按语言返回已验证 feeds
└── Day 5: 文档更新 + 复盘，为 Phase 2（新用户 onboarding 改造）做好准备
```

### 8.2 依赖关系

```
数据库迁移脚本
    │
    ├──► 内容哈希工具
    │        │
    │        └──► 双写逻辑
    │                 │
    │                 ├──► 查询适配层 ◄───┐
    │                 │                      │
    │                 └──► TTS 缓存适配     │
    │                                      │
    ├──► 数据校验脚本 ──────────────────────┤
    │                                      │
    └──► Feed 验证表 ──► Feed 验证服务      │
                              │             │
                              └──► starter-pack API
                                           │
    ┌──────────────────────────────────────┘
    │
    ▼
集成测试 → 灰度发布 → 全量上线 → onboarding Phase 2
```

---

## 9. 监控与告警

### 9.1 关键指标

```yaml
# monitoring/metrics.yml

metrics:
  # 业务指标
  - name: article_reuse_ratio
    description: 文章共享复用率（越高说明去重效果越好）
    query: |
      1.0 - (SELECT COUNT(*)::float FROM global_articles) / 
            NULLIF((SELECT COUNT(*)::float FROM user_article_refs), 0)
    alert: < 0.3  # 复用率低于30%时告警（即大量文章未被共享）

  - name: tts_cache_hit_ratio
    description: TTS缓存命中率
    query: |
      sum(rate(tts_cache_hits[5m])) / 
      sum(rate(tts_requests[5m]))
    alert: < 0.8

  # 性能指标
  - name: article_query_latency_p99
    description: 文章查询P99延迟
    query: histogram_quantile(0.99, rate(article_query_duration_bucket[5m]))
    alert: > 200ms

  - name: db_connection_pool_usage
    description: 数据库连接池使用率
    query: db_pool_active / db_pool_max
    alert: > 0.8

  # 数据一致性
  - name: data_consistency_check_failures
    description: 数据一致性校验失败次数
    query: sum(increase(validation_failures[1h]))
    alert: > 0
```

### 9.2 告警配置

```python
# 伪代码示例
ALERT_RULES = [
    {
        "name": "HighErrorRate",
        "condition": "error_rate > 0.01",
        "duration": "5m",
        "severity": "critical",
        "action": "page_oncall"
    },
    {
        "name": "DataInconsistency",
        "condition": "validation_failures > 0",
        "duration": "0m",  # 立即告警
        "severity": "critical",
        "action": "page_oncall + auto_rollback_check"
    },
    {
        "name": "LowCacheHitRate",
        "condition": "tts_cache_hit_ratio < 0.5",
        "duration": "10m",
        "severity": "warning",
        "action": "notify_team"
    }
]
```

---

## 10. 附录

### 10.1 术语表

| 术语 | 定义 |
|------|------|
| global_article | 全局文章，去重后的文章实体，跨用户共享 |
| user_article_ref | 用户文章关联，用户与全局文章的订阅关系 |
| content_hash | 内容哈希，用于检测文章内容是否相同 |
| dual_write | 双写，同时写入新旧两套表 |
| TTS | Text-to-Speech，文本转语音 |

### 10.2 参考文档

- [数据库 Schema](./database_schema.md)
- [TTS 架构设计](./[plan]tts_upgrade_implementation.md)
- [部署文档](./deployment_summary.md)
- [测试指南](./TESTING_GUIDE.md)

### 10.3 决策记录

| 日期 | 决策 | 原因 | 替代方案 |
|------|------|------|----------|
| 2026-04-12 | 采用全局文章表架构 | 数据模型清晰，扩展性好 | 内容哈希索引、URL主键化 |
| 2026-04-12 | 渐进式迁移 | 风险可控，可随时回滚 | 一次性迁移 |
| 2026-04-12 | URL 作为唯一标识 | 简单可靠 | 内容相似度匹配 |
| 2026-04-12 | 全局共享 AI 摘要 | 最大化成本节省 | 个人定制摘要 |

---

**文档版本**: 1.0  
**最后更新**: 2026-04-12  
**作者**: Claude Code  
**评审状态**: 待评审
