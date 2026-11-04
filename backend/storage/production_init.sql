--
-- Jasmine Production Database Initialization Script
-- Generated from local development database (final state)
-- Date: 2025-11-28
--
-- This script represents the complete, tested schema from local development.
-- It should be used INSTEAD OF (schemas.sql + migrations) for fresh production deploys.
--

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

-- ================================
-- Extensions
-- ================================
CREATE EXTENSION IF NOT EXISTS "uuid-ossp" WITH SCHEMA public;
COMMENT ON EXTENSION "uuid-ossp" IS 'generate universally unique identifiers (UUIDs)';

-- ================================
-- Functions
-- ================================
CREATE FUNCTION public.update_updated_at_column() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$;

-- ================================
-- Tables
-- ================================

-- Users table
CREATE TABLE public.users (
    id VARCHAR(64) PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL,
    full_name VARCHAR(100),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    password_hash VARCHAR(255),
    is_active BOOLEAN DEFAULT true,
    is_superuser BOOLEAN DEFAULT false,
    avatar_url TEXT,
    auto_refresh_enabled BOOLEAN DEFAULT true NOT NULL,
    tts_voice_zh VARCHAR(100) DEFAULT NULL,
    tts_voice_en VARCHAR(100) DEFAULT NULL
);
COMMENT ON COLUMN public.users.auto_refresh_enabled IS 'Controls whether user feeds are included in scheduled automatic refreshes.';

-- User sessions table
CREATE TABLE public.user_sessions (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash VARCHAR(255) NOT NULL,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    last_accessed TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Source types table
CREATE TABLE public.source_types (
    id VARCHAR(64) PRIMARY KEY,
    name VARCHAR(50) UNIQUE NOT NULL,
    display_name VARCHAR(100) NOT NULL,
    description TEXT,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- User feeds table
CREATE TABLE public.user_feeds (
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
    platform VARCHAR(50) DEFAULT 'rss' NOT NULL,
    UNIQUE(user_id, feed_url)
);
COMMENT ON COLUMN public.user_feeds.platform IS 'Feed platform type: rss, wechat, bilibili, twitter, xiaohongshu, etc.';

-- Articles table
CREATE TABLE public.articles (
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
    UNIQUE(feed_id, url)
);

-- Feed update logs table
CREATE TABLE public.feed_update_logs (
    id SERIAL PRIMARY KEY,
    feed_id INTEGER NOT NULL,
    started_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
    completed_at TIMESTAMP WITHOUT TIME ZONE,
    status VARCHAR(20),
    articles_fetched INTEGER DEFAULT 0,
    stored_count INTEGER DEFAULT 0,
    failed_count INTEGER DEFAULT 0,
    error_message TEXT
);

-- User saved articles table
CREATE TABLE public.user_saved_articles (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL,
    article_id INTEGER NOT NULL,
    folder_name VARCHAR(100),
    notes TEXT,
    tags TEXT[],
    saved_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, article_id)
);

-- User reading history table
CREATE TABLE public.user_reading_history (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL,
    article_id INTEGER NOT NULL,
    is_read BOOLEAN DEFAULT false,
    read_at TIMESTAMP WITHOUT TIME ZONE,
    read_duration INTEGER DEFAULT 0,
    scroll_position DOUBLE PRECISION DEFAULT 0,
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, article_id)
);

-- ================================
-- Views
-- ================================

CREATE VIEW public.v_articles AS
 SELECT a.id,
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
     JOIN source_types st ON a.source_type_id::text = st.id::text;

CREATE VIEW public.v_user_feeds AS
 SELECT uf.id,
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
    ( SELECT count(*) AS count
           FROM articles a
          WHERE a.feed_id = uf.id) AS article_count,
    ( SELECT max(a.published_at) AS max
           FROM articles a
          WHERE a.feed_id = uf.id) AS latest_article_date
   FROM user_feeds uf
     JOIN source_types st ON uf.source_type_id::text = st.id::text;

-- ================================
-- Indexes
-- ================================

-- Articles indexes
CREATE INDEX idx_articles_content_search ON public.articles USING gin (to_tsvector('simple'::regconfig, COALESCE(content, summary)));
CREATE INDEX idx_articles_created_at ON public.articles USING btree (created_at);
CREATE INDEX idx_articles_feed_id ON public.articles USING btree (feed_id);
CREATE INDEX idx_articles_published_at ON public.articles USING btree (published_at);
CREATE INDEX idx_articles_source ON public.articles USING btree (source);
CREATE INDEX idx_articles_title_search ON public.articles USING gin (to_tsvector('simple'::regconfig, title));

-- Feed update logs indexes
CREATE INDEX idx_feed_update_logs_feed_id ON public.feed_update_logs USING btree (feed_id);
CREATE INDEX idx_feed_update_logs_started ON public.feed_update_logs USING btree (started_at DESC);

-- Reading history indexes
CREATE INDEX idx_reading_read_at ON public.user_reading_history USING btree (read_at DESC);
CREATE INDEX idx_reading_user_article ON public.user_reading_history USING btree (user_id, article_id);
CREATE INDEX idx_reading_user_is_read ON public.user_reading_history USING btree (user_id, is_read);

-- User feeds indexes
CREATE INDEX idx_user_feeds_active ON public.user_feeds USING btree (is_active);
CREATE INDEX idx_user_feeds_last_fetched ON public.user_feeds USING btree (last_fetched_at);
CREATE INDEX idx_user_feeds_platform ON public.user_feeds USING btree (platform);
CREATE INDEX idx_user_feeds_user_id ON public.user_feeds USING btree (user_id);

-- User saved articles indexes
CREATE INDEX idx_user_saved_article ON public.user_saved_articles USING btree (article_id);
CREATE INDEX idx_user_saved_user ON public.user_saved_articles USING btree (user_id);

-- User sessions indexes
CREATE INDEX idx_user_sessions_expires ON public.user_sessions USING btree (expires_at);
CREATE INDEX idx_user_sessions_token ON public.user_sessions USING btree (token_hash);
CREATE INDEX idx_user_sessions_user_id ON public.user_sessions USING btree (user_id);

-- Users indexes
CREATE INDEX idx_users_auto_refresh ON public.users USING btree (auto_refresh_enabled) WHERE (auto_refresh_enabled = true);

-- ================================
-- Triggers
-- ================================

CREATE TRIGGER update_articles_updated_at
    BEFORE UPDATE ON public.articles
    FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();

CREATE TRIGGER update_user_feeds_updated_at
    BEFORE UPDATE ON public.user_feeds
    FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();

CREATE TRIGGER update_users_updated_at
    BEFORE UPDATE ON public.users
    FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();

-- ================================
-- User Queue and Playback State (Added 2026-07-15)
-- ================================

CREATE TABLE public.user_queues (
    user_id VARCHAR(64) PRIMARY KEY REFERENCES public.users(id) ON DELETE CASCADE,
    items JSONB NOT NULL DEFAULT '[]',
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_user_queues_updated_at ON public.user_queues(updated_at DESC);

CREATE TRIGGER update_user_queues_updated_at
    BEFORE UPDATE ON public.user_queues
    FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();

CREATE TABLE public.user_playback_state (
    user_id VARCHAR(64) PRIMARY KEY REFERENCES public.users(id) ON DELETE CASCADE,
    playlist JSONB NOT NULL DEFAULT '[]',
    current_index INTEGER NOT NULL DEFAULT 0,
    "current_time" DOUBLE PRECISION NOT NULL DEFAULT 0,
    total_time DOUBLE PRECISION NOT NULL DEFAULT 0,
    current_article JSONB,
    is_playing BOOLEAN NOT NULL DEFAULT false,
    playback_rate DOUBLE PRECISION NOT NULL DEFAULT 1.0,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_user_playback_state_updated_at ON public.user_playback_state(updated_at DESC);

CREATE TRIGGER update_user_playback_state_updated_at
    BEFORE UPDATE ON public.user_playback_state
    FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();

-- ================================
-- Completion Message
-- ================================
-- Schema initialization complete
-- Note: Foreign key constraints are already defined inline in CREATE TABLE statements
