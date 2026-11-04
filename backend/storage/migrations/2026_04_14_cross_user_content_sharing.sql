-- =============================================
-- Migration: Cross-User Content Sharing (Phase 1)
-- Date: 2026-04-14
-- Description: Create global_articles, user_article_refs, tts_cache, feed_validation tables
-- =============================================

-- 1. 创建全局文章表（内容去重池）
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
    reading_time INTEGER,
    cover_image TEXT,
    language VARCHAR(10) DEFAULT 'zh',
    keywords JSONB DEFAULT '[]',
    entities JSONB DEFAULT '[]',
    sentiment_score DOUBLE PRECISION,
    first_seen_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    last_updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_global_articles_url ON global_articles(url);
CREATE INDEX IF NOT EXISTS idx_global_articles_content_hash ON global_articles(content_hash);
CREATE INDEX IF NOT EXISTS idx_global_articles_published ON global_articles(published_at DESC);
CREATE INDEX IF NOT EXISTS idx_global_articles_first_seen ON global_articles(first_seen_at);

-- 创建全文搜索索引
CREATE INDEX IF NOT EXISTS idx_global_articles_title_search
    ON global_articles USING GIN(to_tsvector('simple', title));
CREATE INDEX IF NOT EXISTS idx_global_articles_content_search
    ON global_articles USING GIN(to_tsvector('simple', COALESCE(content, summary)));

-- 2. 创建用户文章关联表
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
    fetched_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, global_article_id, feed_id)
);

CREATE INDEX IF NOT EXISTS idx_uar_user_feed ON user_article_refs(user_id, feed_id);
CREATE INDEX IF NOT EXISTS idx_uar_global_article ON user_article_refs(global_article_id);
CREATE INDEX IF NOT EXISTS idx_uar_user_article ON user_article_refs(user_id, global_article_id);
CREATE INDEX IF NOT EXISTS idx_uar_legacy_article ON user_article_refs(legacy_article_id);

-- 3. 创建 TTS 缓存表
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
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    last_accessed_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    access_count INTEGER DEFAULT 0,
    UNIQUE(global_article_id, voice, engine)
);

CREATE INDEX IF NOT EXISTS idx_tts_cache_article ON tts_cache(global_article_id);
CREATE INDEX IF NOT EXISTS idx_tts_cache_key ON tts_cache(cache_key);

-- 4. 创建 Feed 预验证表（支撑 Starter Pack 质量筛选）
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

CREATE INDEX IF NOT EXISTS idx_feed_validation_valid ON feed_validation(is_valid, language);
CREATE INDEX IF NOT EXISTS idx_feed_validation_validated_at ON feed_validation(last_validated_at);

-- 5. 更新时间触发器（global_articles 使用 last_updated_at）
CREATE OR REPLACE FUNCTION update_last_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.last_updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS update_global_articles_updated_at ON global_articles;
CREATE TRIGGER update_global_articles_updated_at
    BEFORE UPDATE ON global_articles
    FOR EACH ROW EXECUTE FUNCTION update_last_updated_at_column();

-- 6. feed_validation 使用 updated_at 字段，需要单独的触发器函数
CREATE OR REPLACE FUNCTION update_feed_validation_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS update_feed_validation_updated_at ON feed_validation;
CREATE TRIGGER update_feed_validation_updated_at
    BEFORE UPDATE ON feed_validation
    FOR EACH ROW EXECUTE FUNCTION update_feed_validation_updated_at_column();
