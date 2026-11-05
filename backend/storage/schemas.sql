-- ============================================================================
-- Readaria 数据库 Schema（生产环境真实映射）
-- 最后同步: 2026-11-04
-- 数据源: 工作生产库 PostgreSQL 14.20（pg_dump --schema-only）
-- 内容: 生产 schema 减去 newsroom 故事流水线、邀请码和订阅模块（共 11 张表）
-- 表数量: 24
--
-- ID 类型说明:
--   users.id, source_types.id → VARCHAR(64)
--   source_proposals.id       → BIGSERIAL
--   其他自增 id               → SERIAL
--   创建外键时必须匹配父表 ID 类型
--
-- 与原始生产转储的两处有意差异:
--   1. 移除 source_proposals_vertical_id_fkey，因为 verticals 已移除。
--   2. users.preferred_language 使用迁移和注册代码要求的默认值 'en'。
-- ============================================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp" WITH SCHEMA public;

-- ============================================================================
-- 触发器函数
-- ============================================================================

CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION update_last_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.last_updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION update_feed_validation_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ========== 用户系统 ==========

CREATE TABLE users (
    id VARCHAR(64) PRIMARY KEY,
    username VARCHAR(50) NOT NULL CONSTRAINT users_username_key UNIQUE,
    email VARCHAR(100) NOT NULL CONSTRAINT users_email_key UNIQUE,
    full_name VARCHAR(100),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    password_hash VARCHAR(255),
    is_active BOOLEAN DEFAULT true,
    is_superuser BOOLEAN DEFAULT false,
    avatar_url TEXT,
    auto_refresh_enabled BOOLEAN NOT NULL DEFAULT true,
    preferred_language VARCHAR(10) DEFAULT 'en',
    auto_podcast_enabled BOOLEAN NOT NULL DEFAULT false,
    auth_provider VARCHAR(20) DEFAULT 'password',
    first_podcast_grace_credit_used BOOLEAN DEFAULT false,
    invite_code_status VARCHAR(20) DEFAULT NULL,
    tts_voice_zh VARCHAR(100) DEFAULT NULL,
    tts_voice_en VARCHAR(100) DEFAULT NULL
);

COMMENT ON COLUMN users.auto_refresh_enabled IS
    'Controls whether user feeds are included in scheduled automatic refreshes.';

CREATE INDEX idx_users_auto_podcast ON users(auto_podcast_enabled)
    WHERE auto_podcast_enabled = true;
CREATE INDEX idx_users_auto_refresh ON users(auto_refresh_enabled)
    WHERE auto_refresh_enabled = true;

CREATE TRIGGER update_users_updated_at BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TABLE user_sessions (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL
        CONSTRAINT user_sessions_user_id_fkey REFERENCES users(id) ON DELETE CASCADE,
    token_hash VARCHAR(255) NOT NULL,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    last_accessed TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_user_sessions_expires ON user_sessions(expires_at);
CREATE INDEX idx_user_sessions_token ON user_sessions(token_hash);
CREATE INDEX idx_user_sessions_user_id ON user_sessions(user_id);

-- ========== 内容源与抓取 ==========

CREATE TABLE source_types (
    id VARCHAR(64) PRIMARY KEY,
    name VARCHAR(50) NOT NULL CONSTRAINT source_types_name_key UNIQUE,
    display_name VARCHAR(100) NOT NULL,
    description TEXT,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE user_feeds (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL
        CONSTRAINT user_feeds_user_id_fkey REFERENCES users(id) ON DELETE CASCADE,
    source_type_id VARCHAR(64) NOT NULL
        CONSTRAINT user_feeds_source_type_id_fkey REFERENCES source_types(id),
    feed_name VARCHAR(255) NOT NULL,
    feed_url TEXT NOT NULL,
    feed_config JSONB DEFAULT '{}',
    is_active BOOLEAN DEFAULT true,
    last_fetched_at TIMESTAMP WITH TIME ZONE,
    fetch_interval_minutes INTEGER DEFAULT 60,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    platform VARCHAR(50) NOT NULL DEFAULT 'rss',
    CONSTRAINT user_feeds_user_id_feed_url_key UNIQUE(user_id, feed_url)
);

COMMENT ON COLUMN user_feeds.platform IS
    'Feed platform type: rss, wechat, bilibili, twitter, xiaohongshu, etc.';

CREATE INDEX idx_user_feeds_active ON user_feeds(is_active);
CREATE INDEX idx_user_feeds_last_fetched ON user_feeds(last_fetched_at);
CREATE INDEX idx_user_feeds_platform ON user_feeds(platform);
CREATE INDEX idx_user_feeds_user_id ON user_feeds(user_id);

CREATE TRIGGER update_user_feeds_updated_at BEFORE UPDATE ON user_feeds
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TABLE feed_update_logs (
    id SERIAL PRIMARY KEY,
    feed_id INTEGER NOT NULL,
    started_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    status VARCHAR(20),
    articles_fetched INTEGER DEFAULT 0,
    stored_count INTEGER DEFAULT 0,
    failed_count INTEGER DEFAULT 0,
    error_message TEXT
);

CREATE INDEX idx_feed_update_logs_feed_id ON feed_update_logs(feed_id);
CREATE INDEX idx_feed_update_logs_started ON feed_update_logs(started_at DESC);

CREATE TABLE feed_validation (
    id SERIAL PRIMARY KEY,
    feed_url VARCHAR(2048) NOT NULL CONSTRAINT feed_validation_feed_url_key UNIQUE,
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

CREATE TRIGGER update_feed_validation_updated_at BEFORE UPDATE ON feed_validation
    FOR EACH ROW EXECUTE FUNCTION update_feed_validation_updated_at_column();

-- ========== 文章与跨用户内容共享 ==========

CREATE TABLE articles (
    id SERIAL PRIMARY KEY,
    feed_id INTEGER NOT NULL
        CONSTRAINT articles_feed_id_fkey REFERENCES user_feeds(id) ON DELETE CASCADE,
    source_type_id VARCHAR(64) NOT NULL
        CONSTRAINT articles_source_type_id_fkey REFERENCES source_types(id),
    title TEXT NOT NULL,
    url TEXT NOT NULL,
    author VARCHAR(255),
    published_at TIMESTAMP WITH TIME ZONE,
    summary TEXT,
    content TEXT,
    content_hash VARCHAR(64),
    language VARCHAR(10) DEFAULT 'zh',
    word_count INTEGER,
    reading_time INTEGER,
    keywords JSONB DEFAULT '[]',
    entities JSONB DEFAULT '[]',
    sentiment_score DOUBLE PRECISION,
    source VARCHAR(255),
    tags JSONB DEFAULT '[]',
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    cover_image TEXT,
    CONSTRAINT articles_feed_id_url_key UNIQUE(feed_id, url)
);

CREATE INDEX idx_articles_content_search ON articles USING GIN(
    to_tsvector('simple', COALESCE(content, summary))
);
CREATE INDEX idx_articles_created_at ON articles(created_at);
CREATE INDEX idx_articles_feed_id ON articles(feed_id);
CREATE INDEX idx_articles_published_at ON articles(published_at);
CREATE INDEX idx_articles_source ON articles(source);
CREATE INDEX idx_articles_title_search ON articles USING GIN(to_tsvector('simple', title));

CREATE TRIGGER update_articles_updated_at BEFORE UPDATE ON articles
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TABLE global_articles (
    id SERIAL PRIMARY KEY,
    url VARCHAR(2048) NOT NULL CONSTRAINT global_articles_url_key UNIQUE,
    content_hash VARCHAR(64) NOT NULL,
    title TEXT NOT NULL,
    author VARCHAR(255),
    published_at TIMESTAMP WITH TIME ZONE,
    content TEXT,
    summary TEXT,
    source_feed_url VARCHAR(1024),
    source_type_id VARCHAR(64)
        CONSTRAINT global_articles_source_type_id_fkey REFERENCES source_types(id),
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

CREATE INDEX idx_global_articles_content_hash ON global_articles(content_hash);
CREATE INDEX idx_global_articles_content_search ON global_articles USING GIN(
    to_tsvector('simple', COALESCE(content, summary))
);
CREATE INDEX idx_global_articles_first_seen ON global_articles(first_seen_at);
CREATE INDEX idx_global_articles_published ON global_articles(published_at DESC);
CREATE INDEX idx_global_articles_source_feed_url ON global_articles(source_feed_url);
CREATE INDEX idx_global_articles_title_search ON global_articles USING GIN(
    to_tsvector('simple', title)
);
CREATE INDEX idx_global_articles_url ON global_articles(url);

CREATE TRIGGER update_global_articles_updated_at BEFORE UPDATE ON global_articles
    FOR EACH ROW EXECUTE FUNCTION update_last_updated_at_column();

CREATE TABLE article_summaries (
    id SERIAL PRIMARY KEY,
    global_article_id INTEGER NOT NULL
        CONSTRAINT article_summaries_global_article_id_fkey
        REFERENCES global_articles(id) ON DELETE CASCADE,
    language VARCHAR(10) NOT NULL DEFAULT 'zh',
    summary TEXT NOT NULL,
    generated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT article_summaries_global_article_id_language_key
        UNIQUE(global_article_id, language)
);

CREATE INDEX idx_article_summaries_article ON article_summaries(global_article_id);
CREATE INDEX idx_article_summaries_lang ON article_summaries(language);

CREATE TRIGGER update_article_summaries_updated_at BEFORE UPDATE ON article_summaries
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TABLE user_article_refs (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL
        CONSTRAINT user_article_refs_user_id_fkey REFERENCES users(id) ON DELETE CASCADE,
    global_article_id INTEGER NOT NULL
        CONSTRAINT user_article_refs_global_article_id_fkey
        REFERENCES global_articles(id) ON DELETE CASCADE,
    legacy_article_id INTEGER,
    feed_id INTEGER NOT NULL
        CONSTRAINT user_article_refs_feed_id_fkey REFERENCES user_feeds(id) ON DELETE CASCADE,
    user_summary TEXT,
    is_favorited BOOLEAN DEFAULT false,
    folder_name VARCHAR(100),
    user_tags TEXT[],
    notes TEXT,
    fetched_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT user_article_refs_user_id_global_article_id_feed_id_key
        UNIQUE(user_id, global_article_id, feed_id)
);

CREATE INDEX idx_uar_global_article ON user_article_refs(global_article_id);
CREATE INDEX idx_uar_legacy_article ON user_article_refs(legacy_article_id);
CREATE INDEX idx_uar_user_article ON user_article_refs(user_id, global_article_id);
CREATE INDEX idx_uar_user_feed ON user_article_refs(user_id, feed_id);

-- ========== 用户阅读、收藏与反馈 ==========

CREATE TABLE user_saved_articles (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL
        CONSTRAINT user_saved_articles_user_id_fkey REFERENCES users(id) ON DELETE CASCADE,
    article_id INTEGER,
    global_article_id INTEGER
        CONSTRAINT user_saved_articles_global_article_id_fkey
        REFERENCES global_articles(id) ON DELETE CASCADE,
    folder_name VARCHAR(100),
    notes TEXT,
    tags TEXT[],
    saved_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT user_saved_articles_user_id_article_id_key UNIQUE(user_id, article_id),
    CONSTRAINT unique_user_saved_global_article UNIQUE(user_id, global_article_id)
);

CREATE INDEX idx_user_saved_article ON user_saved_articles(article_id);
CREATE INDEX idx_user_saved_global_article ON user_saved_articles(global_article_id);
CREATE INDEX idx_user_saved_user ON user_saved_articles(user_id);

CREATE TABLE user_reading_history (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL
        CONSTRAINT user_reading_history_user_id_fkey REFERENCES users(id) ON DELETE CASCADE,
    article_id INTEGER,
    is_read BOOLEAN DEFAULT false,
    read_at TIMESTAMP,
    read_duration INTEGER DEFAULT 0,
    scroll_position DOUBLE PRECISION DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    global_article_id INTEGER
        CONSTRAINT user_reading_history_global_article_id_fkey
        REFERENCES global_articles(id) ON DELETE CASCADE,
    CONSTRAINT user_reading_history_user_id_article_id_key UNIQUE(user_id, article_id),
    CONSTRAINT unique_user_reading_global_article UNIQUE(user_id, global_article_id)
);

CREATE INDEX idx_reading_global_article ON user_reading_history(global_article_id);
CREATE INDEX idx_reading_read_at ON user_reading_history(read_at DESC);
CREATE INDEX idx_reading_user_article ON user_reading_history(user_id, article_id);
CREATE INDEX idx_reading_user_is_read ON user_reading_history(user_id, is_read);

CREATE TABLE user_feedback (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL
        CONSTRAINT user_feedback_user_id_fkey REFERENCES users(id) ON DELETE CASCADE,
    message TEXT NOT NULL,
    attach_logs BOOLEAN DEFAULT false,
    status VARCHAR(20) DEFAULT 'open'
        CONSTRAINT user_feedback_status_check CHECK(status IN ('open', 'resolved', 'ignored')),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    frontend_logs JSONB DEFAULT '[]'
);

CREATE INDEX idx_user_feedback_created_at ON user_feedback(created_at DESC);
CREATE INDEX idx_user_feedback_status ON user_feedback(status);
CREATE INDEX idx_user_feedback_user_id ON user_feedback(user_id);

CREATE TRIGGER update_user_feedback_updated_at BEFORE UPDATE ON user_feedback
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ========== Podcast 系统 ==========

CREATE TABLE podcasts (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL
        CONSTRAINT podcasts_user_id_fkey REFERENCES users(id) ON DELETE CASCADE,
    title VARCHAR(255) NOT NULL,
    description TEXT,
    style VARCHAR(50) DEFAULT 'deep_dive',
    duration INTEGER,
    cover_image VARCHAR(512),
    generation_status VARCHAR(20) DEFAULT 'pending',
    generation_started_at TIMESTAMP,
    generation_completed_at TIMESTAMP,
    generation_error TEXT,
    audio_url VARCHAR(512),
    audio_cache_key VARCHAR(255) CONSTRAINT podcasts_audio_cache_key_key UNIQUE,
    play_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    source VARCHAR(32) DEFAULT 'user_generated',
    share_token VARCHAR(32) CONSTRAINT podcasts_share_token_key UNIQUE
);

COMMENT ON TABLE podcasts IS 'AI 播客主表';

CREATE INDEX idx_podcasts_share_token ON podcasts(share_token) WHERE share_token IS NOT NULL;
CREATE INDEX idx_podcasts_user_source ON podcasts(user_id, source);
CREATE INDEX idx_podcasts_user_status_created
    ON podcasts(user_id, generation_status, created_at DESC);

CREATE TRIGGER update_podcasts_updated_at BEFORE UPDATE ON podcasts
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TABLE podcast_articles (
    id SERIAL PRIMARY KEY,
    podcast_id INTEGER NOT NULL
        CONSTRAINT podcast_articles_podcast_id_fkey REFERENCES podcasts(id) ON DELETE CASCADE,
    article_id INTEGER NOT NULL
        CONSTRAINT podcast_articles_article_id_fkey REFERENCES articles(id) ON DELETE CASCADE,
    sequence_order INTEGER NOT NULL,
    importance_score DOUBLE PRECISION DEFAULT 0.5,
    start_time INTEGER,
    end_time INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    global_article_id INTEGER
        CONSTRAINT podcast_articles_global_article_id_fkey
        REFERENCES global_articles(id) ON DELETE CASCADE,
    CONSTRAINT podcast_articles_podcast_id_article_id_key UNIQUE(podcast_id, article_id)
);

COMMENT ON TABLE podcast_articles IS '播客-文章关联表';

CREATE INDEX idx_podcast_articles_global ON podcast_articles(global_article_id);
CREATE INDEX idx_podcast_articles_podcast ON podcast_articles(podcast_id);

CREATE TABLE podcast_scripts (
    id SERIAL PRIMARY KEY,
    podcast_id INTEGER NOT NULL
        CONSTRAINT podcast_scripts_podcast_id_fkey REFERENCES podcasts(id) ON DELETE CASCADE,
    full_script TEXT NOT NULL,
    script_version VARCHAR(20) DEFAULT 'v1',
    total_segments INTEGER,
    estimated_duration INTEGER,
    generated_by VARCHAR(50) DEFAULT 'gpt-4',
    generation_prompt TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    suggested_questions JSONB
);

COMMENT ON TABLE podcast_scripts IS '播客脚本表';

CREATE TABLE podcast_conversations (
    id SERIAL PRIMARY KEY,
    podcast_id INTEGER NOT NULL
        CONSTRAINT podcast_conversations_podcast_id_fkey REFERENCES podcasts(id) ON DELETE CASCADE,
    user_id VARCHAR(64) NOT NULL
        CONSTRAINT podcast_conversations_user_id_fkey REFERENCES users(id) ON DELETE CASCADE,
    user_message TEXT NOT NULL,
    assistant_message TEXT NOT NULL,
    context_article_ids INTEGER[],
    context_segments JSONB,
    conversation_index INTEGER DEFAULT 0,
    parent_conversation_id INTEGER
        CONSTRAINT podcast_conversations_parent_conversation_id_fkey
        REFERENCES podcast_conversations(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE podcast_conversations IS '播客对话历史表';

CREATE INDEX idx_conversations_podcast ON podcast_conversations(podcast_id);
CREATE INDEX idx_conversations_user ON podcast_conversations(user_id);

CREATE TABLE podcast_play_progress (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL
        CONSTRAINT podcast_play_progress_user_id_fkey REFERENCES users(id) ON DELETE CASCADE,
    podcast_id INTEGER NOT NULL
        CONSTRAINT podcast_play_progress_podcast_id_fkey REFERENCES podcasts(id) ON DELETE CASCADE,
    current_position INTEGER DEFAULT 0,
    total_time INTEGER,
    progress_percentage DOUBLE PRECISION DEFAULT 0,
    is_completed BOOLEAN DEFAULT false,
    last_played_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT podcast_play_progress_user_id_podcast_id_key UNIQUE(user_id, podcast_id)
);

COMMENT ON TABLE podcast_play_progress IS '播客播放进度表';

CREATE TRIGGER update_podcast_play_progress_updated_at BEFORE UPDATE ON podcast_play_progress
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ========== 音频历史、队列与播放状态 ==========

CREATE TABLE audio_play_history (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL
        CONSTRAINT audio_play_history_user_id_fkey REFERENCES users(id) ON DELETE CASCADE,
    item_type VARCHAR(20) NOT NULL,
    item_id INTEGER NOT NULL,
    title VARCHAR(500),
    source_name VARCHAR(255),
    duration_seconds INTEGER DEFAULT 0,
    played_seconds INTEGER DEFAULT 0,
    progress_percentage DOUBLE PRECISION DEFAULT 0,
    is_completed BOOLEAN DEFAULT false,
    played_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    global_article_id INTEGER
        CONSTRAINT audio_play_history_global_article_id_fkey
        REFERENCES global_articles(id) ON DELETE CASCADE,
    CONSTRAINT audio_play_history_item_type_check CHECK(item_type IN ('article', 'podcast')),
    CONSTRAINT audio_play_history_user_id_item_type_item_id_key
        UNIQUE(user_id, item_type, item_id)
);

CREATE INDEX idx_audio_history_global ON audio_play_history(global_article_id);
CREATE INDEX idx_audio_history_item ON audio_play_history(item_type, item_id);
CREATE INDEX idx_audio_history_user_played ON audio_play_history(user_id, played_at DESC);
CREATE INDEX idx_audio_history_user_type ON audio_play_history(user_id, item_type);

CREATE TABLE user_queues (
    user_id VARCHAR(64) PRIMARY KEY
        CONSTRAINT user_queues_user_id_fkey REFERENCES users(id) ON DELETE CASCADE,
    items JSONB NOT NULL DEFAULT '[]',
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_user_queues_updated_at ON user_queues(updated_at DESC);

CREATE TRIGGER update_user_queues_updated_at BEFORE UPDATE ON user_queues
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TABLE user_playback_state (
    user_id VARCHAR(64) PRIMARY KEY
        CONSTRAINT user_playback_state_user_id_fkey REFERENCES users(id) ON DELETE CASCADE,
    playlist JSONB NOT NULL DEFAULT '[]',
    current_index INTEGER NOT NULL DEFAULT 0,
    "current_time" DOUBLE PRECISION NOT NULL DEFAULT 0,
    total_time DOUBLE PRECISION NOT NULL DEFAULT 0,
    current_article JSONB,
    is_playing BOOLEAN NOT NULL DEFAULT false,
    playback_rate DOUBLE PRECISION NOT NULL DEFAULT 1.0,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_user_playback_state_updated_at ON user_playback_state(updated_at DESC);

CREATE TRIGGER update_user_playback_state_updated_at BEFORE UPDATE ON user_playback_state
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ========== TTS 缓存与用量统计 ==========

CREATE TABLE tts_cache (
    id SERIAL PRIMARY KEY,
    global_article_id INTEGER NOT NULL
        CONSTRAINT tts_cache_global_article_id_fkey
        REFERENCES global_articles(id) ON DELETE CASCADE,
    voice VARCHAR(50) NOT NULL,
    engine VARCHAR(50) NOT NULL,
    cache_key VARCHAR(255) NOT NULL CONSTRAINT tts_cache_cache_key_key UNIQUE,
    file_path VARCHAR(512) NOT NULL,
    file_size INTEGER,
    duration_seconds INTEGER,
    format VARCHAR(10) DEFAULT 'mp3',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    last_accessed_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    access_count INTEGER DEFAULT 0,
    CONSTRAINT tts_cache_global_article_id_voice_engine_key
        UNIQUE(global_article_id, voice, engine)
);

CREATE INDEX idx_tts_cache_article ON tts_cache(global_article_id);
CREATE INDEX idx_tts_cache_key ON tts_cache(cache_key);

CREATE TABLE user_usage_daily (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL
        CONSTRAINT user_usage_daily_user_id_fkey REFERENCES users(id) ON DELETE CASCADE,
    usage_date DATE NOT NULL DEFAULT CURRENT_DATE,
    tts_count INTEGER DEFAULT 0,
    tts_characters INTEGER DEFAULT 0,
    podcast_count INTEGER DEFAULT 0,
    ai_summary_count INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT user_usage_daily_user_id_usage_date_key UNIQUE(user_id, usage_date)
);

COMMENT ON COLUMN user_usage_daily.podcast_count IS '今日播客生成数';

CREATE INDEX idx_user_usage_date ON user_usage_daily(usage_date);

-- ========== 内容源提案（保留的生产表；verticals 外键已随模块移除） ==========

CREATE TABLE source_proposals (
    id BIGSERIAL PRIMARY KEY,
    vertical_id INTEGER NOT NULL,
    source_url TEXT NOT NULL,
    source_type VARCHAR(32) NOT NULL DEFAULT 'rss',
    evidence TEXT DEFAULT '',
    status VARCHAR(16) NOT NULL DEFAULT 'pending',
    proposed_by VARCHAR(16) NOT NULL DEFAULT 'scout',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    decided_at TIMESTAMP WITH TIME ZONE
);

CREATE UNIQUE INDEX idx_source_proposals_pending_unique
    ON source_proposals(vertical_id, source_url) WHERE status = 'pending';
CREATE INDEX idx_source_proposals_status ON source_proposals(status);

-- ========== 兼容视图 ==========

CREATE VIEW v_articles AS
SELECT
    a.id,
    a.title,
    a.url,
    a.author,
    a.published_at,
    a.summary,
    a.content,
    a.language,
    a.word_count,
    a.reading_time,
    a.sentiment_score,
    a.source,
    a.tags,
    a.created_at,
    a.updated_at,
    uf.feed_name,
    uf.feed_url,
    st.display_name AS source_type_display
FROM articles a
JOIN user_feeds uf ON a.feed_id = uf.id
JOIN source_types st ON a.source_type_id = st.id;

CREATE VIEW v_user_feeds AS
SELECT
    uf.id,
    uf.user_id,
    uf.feed_name,
    uf.feed_url,
    uf.is_active,
    uf.last_fetched_at,
    uf.fetch_interval_minutes,
    uf.created_at,
    uf.updated_at,
    st.name AS source_type,
    st.display_name AS source_type_display,
    (SELECT COUNT(*) FROM articles a WHERE a.feed_id = uf.id) AS article_count,
    (SELECT MAX(a.published_at) FROM articles a WHERE a.feed_id = uf.id) AS latest_article_date
FROM user_feeds uf
JOIN source_types st ON uf.source_type_id = st.id;

-- ========== Demo 精选内容注册表（公开演示内容，合成用户 demo-curator 名下） ==========
CREATE TABLE IF NOT EXISTS public.demo_content_registry (
    demo_id VARCHAR(64) PRIMARY KEY,
    kind VARCHAR(16) NOT NULL CHECK (kind IN ('podcast', 'article')),
    podcast_id INTEGER REFERENCES public.podcasts(id) ON DELETE CASCADE,
    global_article_id INTEGER REFERENCES public.global_articles(id) ON DELETE CASCADE,
    tts_audio_path VARCHAR(512),
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CHECK ((kind = 'podcast' AND podcast_id IS NOT NULL AND global_article_id IS NULL)
        OR (kind = 'article' AND global_article_id IS NOT NULL AND podcast_id IS NULL))
);
