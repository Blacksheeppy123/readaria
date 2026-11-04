-- ================================
-- Jasmine 数据库 Schema（生产环境真实映射）
-- 最后同步: 2026-02-13
-- 数据源: 线上 PostgreSQL (docker-postgres-1)
-- ================================
-- ⚠️ ID 类型说明:
--   users.id, source_types.id → VARCHAR(64)
--   其他表 id → INTEGER (SERIAL)
--   创建外键时必须匹配父表 ID 类型
-- ================================

-- 触发器函数
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ================================
-- 用户管理
-- ================================

CREATE TABLE users (
    id VARCHAR(64) PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL,
    password_hash VARCHAR(255),
    full_name VARCHAR(100),
    avatar_url TEXT,
    is_active BOOLEAN DEFAULT true,
    is_superuser BOOLEAN DEFAULT false,
    auto_refresh_enabled BOOLEAN NOT NULL DEFAULT true,
    auto_podcast_enabled BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    auth_provider VARCHAR(20) DEFAULT 'password',
    tts_voice_zh VARCHAR(100) DEFAULT NULL,  -- 中文朗读音色偏好（NULL=系统默认，2026-09-07 音色选择功能）
    tts_voice_en VARCHAR(100) DEFAULT NULL   -- 英文朗读音色偏好（NULL=系统默认）
);
CREATE INDEX idx_users_auto_refresh ON users(auto_refresh_enabled) WHERE auto_refresh_enabled = true;
CREATE INDEX idx_users_auto_podcast ON users(auto_podcast_enabled) WHERE auto_podcast_enabled = true;
CREATE TRIGGER update_users_updated_at BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TABLE user_sessions (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash VARCHAR(255) NOT NULL,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    last_accessed TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_user_sessions_token ON user_sessions(token_hash);
CREATE INDEX idx_user_sessions_expires ON user_sessions(expires_at);
CREATE INDEX idx_user_sessions_user_id ON user_sessions(user_id);

-- ================================
-- 内容源管理
-- ================================

CREATE TABLE source_types (
    id VARCHAR(64) PRIMARY KEY,
    name VARCHAR(50) UNIQUE NOT NULL,
    display_name VARCHAR(100) NOT NULL,
    description TEXT,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE user_feeds (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    source_type_id VARCHAR(64) NOT NULL REFERENCES source_types(id),
    feed_name VARCHAR(255) NOT NULL,
    feed_url TEXT NOT NULL,
    feed_config JSONB DEFAULT '{}',
    is_active BOOLEAN DEFAULT true,
    last_fetched_at TIMESTAMP WITH TIME ZONE,
    fetch_interval_minutes INTEGER DEFAULT 60,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    platform VARCHAR(50) NOT NULL DEFAULT 'rss',
    UNIQUE(user_id, feed_url)
);
CREATE INDEX idx_user_feeds_user_id ON user_feeds(user_id);
CREATE INDEX idx_user_feeds_active ON user_feeds(is_active);
CREATE INDEX idx_user_feeds_last_fetched ON user_feeds(last_fetched_at);
CREATE INDEX idx_user_feeds_platform ON user_feeds(platform);
CREATE TRIGGER update_user_feeds_updated_at BEFORE UPDATE ON user_feeds
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ================================
-- 文章内容
-- ================================

CREATE TABLE articles (
    id SERIAL PRIMARY KEY,
    feed_id INTEGER NOT NULL REFERENCES user_feeds(id) ON DELETE CASCADE,
    source_type_id VARCHAR(64) NOT NULL REFERENCES source_types(id),
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
    UNIQUE(feed_id, url)
);
CREATE INDEX idx_articles_feed_id ON articles(feed_id);
CREATE INDEX idx_articles_published_at ON articles(published_at);
CREATE INDEX idx_articles_source ON articles(source);
CREATE INDEX idx_articles_created_at ON articles(created_at);
CREATE INDEX idx_articles_title_search ON articles USING GIN(to_tsvector('simple', title));
CREATE INDEX idx_articles_content_search ON articles USING GIN(to_tsvector('simple', COALESCE(content, summary)));
CREATE TRIGGER update_articles_updated_at BEFORE UPDATE ON articles
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ================================
-- Cross-User Content Sharing (Added 2026-04-14)
-- ================================

CREATE TABLE global_articles (
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

CREATE INDEX idx_global_articles_url ON global_articles(url);
CREATE INDEX idx_global_articles_content_hash ON global_articles(content_hash);
CREATE INDEX idx_global_articles_published ON global_articles(published_at DESC);
CREATE INDEX idx_global_articles_first_seen ON global_articles(first_seen_at);
CREATE INDEX idx_global_articles_source_feed_url ON global_articles(source_feed_url);
CREATE INDEX idx_global_articles_title_search ON global_articles USING GIN(to_tsvector('simple', title));
CREATE INDEX idx_global_articles_content_search ON global_articles USING GIN(to_tsvector('simple', COALESCE(content, summary)));

-- ================================
-- 用户交互
-- ================================

CREATE TABLE user_saved_articles (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    article_id INTEGER REFERENCES articles(id) ON DELETE CASCADE,
    global_article_id INTEGER REFERENCES global_articles(id) ON DELETE CASCADE,
    folder_name VARCHAR(100),
    notes TEXT,
    tags TEXT[],
    saved_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, article_id),
    UNIQUE(user_id, global_article_id)
);
CREATE INDEX idx_user_saved_user ON user_saved_articles(user_id);
CREATE INDEX idx_user_saved_article ON user_saved_articles(article_id);

CREATE TABLE user_reading_history (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    article_id INTEGER REFERENCES articles(id) ON DELETE CASCADE,
    global_article_id INTEGER REFERENCES global_articles(id) ON DELETE CASCADE,
    is_read BOOLEAN DEFAULT false,
    read_at TIMESTAMP,
    read_duration INTEGER DEFAULT 0,
    scroll_position DOUBLE PRECISION DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, article_id),
    UNIQUE(user_id, global_article_id)
);
CREATE INDEX idx_reading_user_article ON user_reading_history(user_id, article_id);
CREATE INDEX idx_reading_user_is_read ON user_reading_history(user_id, is_read);
CREATE INDEX idx_reading_read_at ON user_reading_history(read_at DESC);

CREATE TABLE user_feedback (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    message TEXT NOT NULL,
    attach_logs BOOLEAN DEFAULT false,
    frontend_logs JSONB DEFAULT '[]',
    status VARCHAR(20) DEFAULT 'open' CHECK (status IN ('open', 'resolved', 'ignored')),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_user_feedback_user_id ON user_feedback(user_id);
CREATE INDEX idx_user_feedback_status ON user_feedback(status);
CREATE INDEX idx_user_feedback_created_at ON user_feedback(created_at DESC);
CREATE TRIGGER update_user_feedback_updated_at BEFORE UPDATE ON user_feedback
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ================================
-- 抓取日志
-- ================================

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

-- ================================
-- Podcast 系统
-- ================================

CREATE TABLE podcasts (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
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
    audio_cache_key VARCHAR(255) UNIQUE,
    play_count INTEGER DEFAULT 0,
    source VARCHAR(32) DEFAULT 'user_generated',
    share_token VARCHAR(32) UNIQUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_podcasts_user_status_created ON podcasts(user_id, generation_status, created_at DESC);
CREATE INDEX idx_podcasts_share_token ON podcasts(share_token) WHERE share_token IS NOT NULL;
CREATE TRIGGER update_podcasts_updated_at BEFORE UPDATE ON podcasts
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TABLE podcast_articles (
    id SERIAL PRIMARY KEY,
    podcast_id INTEGER NOT NULL REFERENCES podcasts(id) ON DELETE CASCADE,
    article_id INTEGER REFERENCES articles(id) ON DELETE CASCADE,
    global_article_id INTEGER REFERENCES global_articles(id) ON DELETE CASCADE,
    sequence_order INTEGER NOT NULL,
    importance_score DOUBLE PRECISION DEFAULT 0.5,
    start_time INTEGER,
    end_time INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(podcast_id, article_id)
);
CREATE INDEX idx_podcast_articles_podcast ON podcast_articles(podcast_id);
CREATE INDEX idx_podcast_articles_global ON podcast_articles(global_article_id);

CREATE TABLE podcast_scripts (
    id SERIAL PRIMARY KEY,
    podcast_id INTEGER NOT NULL REFERENCES podcasts(id) ON DELETE CASCADE,
    full_script TEXT NOT NULL,
    script_version VARCHAR(20) DEFAULT 'v1',
    total_segments INTEGER,
    estimated_duration INTEGER,
    generated_by VARCHAR(50) DEFAULT 'gpt-4',
    generation_prompt TEXT,
    suggested_questions JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE podcast_conversations (
    id SERIAL PRIMARY KEY,
    podcast_id INTEGER NOT NULL REFERENCES podcasts(id) ON DELETE CASCADE,
    user_id VARCHAR(64) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    user_message TEXT NOT NULL,
    assistant_message TEXT NOT NULL,
    context_article_ids INTEGER[],
    context_segments JSONB,
    conversation_index INTEGER DEFAULT 0,
    parent_conversation_id INTEGER REFERENCES podcast_conversations(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_conversations_podcast ON podcast_conversations(podcast_id);
CREATE INDEX idx_conversations_user ON podcast_conversations(user_id);

CREATE TABLE podcast_play_progress (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    podcast_id INTEGER NOT NULL REFERENCES podcasts(id) ON DELETE CASCADE,
    current_position INTEGER DEFAULT 0,
    total_time INTEGER,
    progress_percentage DOUBLE PRECISION DEFAULT 0,
    is_completed BOOLEAN DEFAULT false,
    last_played_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, podcast_id)
);
CREATE TRIGGER update_podcast_play_progress_updated_at BEFORE UPDATE ON podcast_play_progress
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ================================
-- 自托管版用量统计（不参与功能门控）
-- ================================

-- 每日用量追踪
CREATE TABLE user_usage_daily (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    usage_date DATE NOT NULL DEFAULT CURRENT_DATE,
    tts_count INTEGER DEFAULT 0,            -- 今日 TTS 文章数
    tts_characters INTEGER DEFAULT 0,       -- 今日 TTS 总字符数
    podcast_count INTEGER DEFAULT 0,        -- 今日播客生成数
    ai_summary_count INTEGER DEFAULT 0,     -- 今日 AI 摘要数
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, usage_date)
);
CREATE INDEX idx_user_usage_date ON user_usage_daily(usage_date);
CREATE TRIGGER update_user_usage_daily_updated_at BEFORE UPDATE ON user_usage_daily
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ================================
-- Audio Play History (Added 2026-03-06)
-- ================================

CREATE TABLE audio_play_history (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    item_type VARCHAR(20) NOT NULL CHECK (item_type IN ('article', 'podcast')),
    item_id INTEGER NOT NULL,
    global_article_id INTEGER REFERENCES global_articles(id) ON DELETE CASCADE,
    title VARCHAR(500),
    source_name VARCHAR(255),
    duration_seconds INTEGER DEFAULT 0,
    played_seconds INTEGER DEFAULT 0,
    progress_percentage DOUBLE PRECISION DEFAULT 0,
    is_completed BOOLEAN DEFAULT false,
    played_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, item_type, item_id)
);
CREATE INDEX idx_audio_history_user_played ON audio_play_history(user_id, played_at DESC);
CREATE INDEX idx_audio_history_user_type ON audio_play_history(user_id, item_type);
CREATE INDEX idx_audio_history_item ON audio_play_history(item_type, item_id);
CREATE INDEX idx_audio_history_global ON audio_play_history(global_article_id);

-- ================================
-- User Queue and Playback State (Added 2026-07-15)
-- ================================

CREATE TABLE user_queues (
    user_id VARCHAR(64) PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    items JSONB NOT NULL DEFAULT '[]',
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_user_queues_updated_at ON user_queues(updated_at DESC);

CREATE TRIGGER update_user_queues_updated_at BEFORE UPDATE ON user_queues
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TABLE user_playback_state (
    user_id VARCHAR(64) PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
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

-- ================================
-- Cross-User Content Sharing (Added 2026-04-14)
-- ================================

CREATE TABLE user_article_refs (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    global_article_id INTEGER NOT NULL REFERENCES global_articles(id) ON DELETE CASCADE,
    legacy_article_id INTEGER,
    feed_id INTEGER NOT NULL REFERENCES user_feeds(id) ON DELETE CASCADE,
    user_summary TEXT,
    is_favorited BOOLEAN DEFAULT FALSE,
    folder_name VARCHAR(100),
    user_tags TEXT[],
    notes TEXT,
    fetched_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, global_article_id, feed_id)
);

CREATE INDEX idx_uar_user_feed ON user_article_refs(user_id, feed_id);
CREATE INDEX idx_uar_global_article ON user_article_refs(global_article_id);
CREATE INDEX idx_uar_user_article ON user_article_refs(user_id, global_article_id);
CREATE INDEX idx_uar_legacy_article ON user_article_refs(legacy_article_id);

CREATE TABLE tts_cache (
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

CREATE INDEX idx_tts_cache_article ON tts_cache(global_article_id);
CREATE INDEX idx_tts_cache_key ON tts_cache(cache_key);

CREATE TABLE feed_validation (
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
