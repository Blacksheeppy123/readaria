--
-- Readaria Production Database Initialization Script
-- Generated from the working production database on 2026-11-04.
-- Source: PostgreSQL 14.20 pg_dump --schema-only.
-- Removed modules: newsroom story pipeline, invitations, and subscriptions.
-- The source_proposals -> verticals foreign key is omitted with verticals.
-- users.preferred_language uses the application/migration default of 'en'.
--

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', true); -- transaction-scoped: pooled connections must not inherit empty search_path
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: uuid-ossp; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS "uuid-ossp" WITH SCHEMA public;


--
-- Name: EXTENSION "uuid-ossp"; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON EXTENSION "uuid-ossp" IS 'generate universally unique identifiers (UUIDs)';


--
-- Name: update_feed_validation_updated_at_column(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.update_feed_validation_updated_at_column() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$;


--
-- Name: update_last_updated_at_column(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.update_last_updated_at_column() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    NEW.last_updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$;


--
-- Name: update_updated_at_column(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.update_updated_at_column() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$;


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: article_summaries; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE IF NOT EXISTS public.article_summaries (
    id integer NOT NULL,
    global_article_id integer NOT NULL,
    language character varying(10) DEFAULT 'zh'::character varying NOT NULL,
    summary text NOT NULL,
    generated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: article_summaries_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.article_summaries_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: article_summaries_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.article_summaries_id_seq OWNED BY public.article_summaries.id;


--
-- Name: articles; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE IF NOT EXISTS public.articles (
    id integer NOT NULL,
    feed_id integer NOT NULL,
    source_type_id character varying(64) NOT NULL,
    title text NOT NULL,
    url text NOT NULL,
    author character varying(255),
    published_at timestamp with time zone,
    summary text,
    content text,
    content_hash character varying(64),
    language character varying(10) DEFAULT 'zh'::character varying,
    word_count integer,
    reading_time integer,
    keywords jsonb DEFAULT '[]'::jsonb,
    entities jsonb DEFAULT '[]'::jsonb,
    sentiment_score double precision,
    source character varying(255),
    tags jsonb DEFAULT '[]'::jsonb,
    metadata jsonb DEFAULT '{}'::jsonb,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    cover_image text
);


--
-- Name: articles_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.articles_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: articles_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.articles_id_seq OWNED BY public.articles.id;


--
-- Name: audio_play_history; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE IF NOT EXISTS public.audio_play_history (
    id integer NOT NULL,
    user_id character varying(64) NOT NULL,
    item_type character varying(20) NOT NULL,
    item_id integer NOT NULL,
    title character varying(500),
    source_name character varying(255),
    duration_seconds integer DEFAULT 0,
    played_seconds integer DEFAULT 0,
    progress_percentage double precision DEFAULT 0,
    is_completed boolean DEFAULT false,
    played_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    global_article_id integer,
    CONSTRAINT audio_play_history_item_type_check CHECK (((item_type)::text = ANY ((ARRAY['article'::character varying, 'podcast'::character varying])::text[])))
);


--
-- Name: audio_play_history_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.audio_play_history_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: audio_play_history_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.audio_play_history_id_seq OWNED BY public.audio_play_history.id;


--
-- Name: feed_update_logs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE IF NOT EXISTS public.feed_update_logs (
    id integer NOT NULL,
    feed_id integer NOT NULL,
    started_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    completed_at timestamp without time zone,
    status character varying(20),
    articles_fetched integer DEFAULT 0,
    stored_count integer DEFAULT 0,
    failed_count integer DEFAULT 0,
    error_message text
);


--
-- Name: feed_update_logs_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.feed_update_logs_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: feed_update_logs_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.feed_update_logs_id_seq OWNED BY public.feed_update_logs.id;


--
-- Name: feed_validation; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE IF NOT EXISTS public.feed_validation (
    id integer NOT NULL,
    feed_url character varying(2048) NOT NULL,
    feed_name character varying(255),
    language character varying(10) DEFAULT 'zh'::character varying,
    is_valid boolean DEFAULT false,
    article_count integer DEFAULT 0,
    avg_content_length integer DEFAULT 0,
    last_article_at timestamp with time zone,
    last_validated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    validation_metadata jsonb DEFAULT '{}'::jsonb,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: feed_validation_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.feed_validation_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: feed_validation_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.feed_validation_id_seq OWNED BY public.feed_validation.id;


--
-- Name: global_articles; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE IF NOT EXISTS public.global_articles (
    id integer NOT NULL,
    url character varying(2048) NOT NULL,
    content_hash character varying(64) NOT NULL,
    title text NOT NULL,
    author character varying(255),
    published_at timestamp with time zone,
    content text,
    summary text,
    source_feed_url character varying(1024),
    source_type_id character varying(64),
    word_count integer,
    reading_time integer,
    cover_image text,
    language character varying(10) DEFAULT 'zh'::character varying,
    keywords jsonb DEFAULT '[]'::jsonb,
    entities jsonb DEFAULT '[]'::jsonb,
    sentiment_score double precision,
    first_seen_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    last_updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: global_articles_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.global_articles_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: global_articles_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.global_articles_id_seq OWNED BY public.global_articles.id;


--
-- Name: podcast_articles; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE IF NOT EXISTS public.podcast_articles (
    id integer NOT NULL,
    podcast_id integer NOT NULL,
    article_id integer NOT NULL,
    sequence_order integer NOT NULL,
    importance_score double precision DEFAULT 0.5,
    start_time integer,
    end_time integer,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    global_article_id integer
);


--
-- Name: TABLE podcast_articles; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.podcast_articles IS '播客-文章关联表';


--
-- Name: podcast_articles_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.podcast_articles_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: podcast_articles_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.podcast_articles_id_seq OWNED BY public.podcast_articles.id;


--
-- Name: podcast_conversations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE IF NOT EXISTS public.podcast_conversations (
    id integer NOT NULL,
    podcast_id integer NOT NULL,
    user_id character varying(64) NOT NULL,
    user_message text NOT NULL,
    assistant_message text NOT NULL,
    context_article_ids integer[],
    context_segments jsonb,
    conversation_index integer DEFAULT 0,
    parent_conversation_id integer,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: TABLE podcast_conversations; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.podcast_conversations IS '播客对话历史表';


--
-- Name: podcast_conversations_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.podcast_conversations_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: podcast_conversations_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.podcast_conversations_id_seq OWNED BY public.podcast_conversations.id;


--
-- Name: podcast_play_progress; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE IF NOT EXISTS public.podcast_play_progress (
    id integer NOT NULL,
    user_id character varying(64) NOT NULL,
    podcast_id integer NOT NULL,
    current_position integer DEFAULT 0,
    total_time integer,
    progress_percentage double precision DEFAULT 0,
    is_completed boolean DEFAULT false,
    last_played_at timestamp without time zone,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: TABLE podcast_play_progress; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.podcast_play_progress IS '播客播放进度表';


--
-- Name: podcast_play_progress_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.podcast_play_progress_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: podcast_play_progress_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.podcast_play_progress_id_seq OWNED BY public.podcast_play_progress.id;


--
-- Name: podcast_scripts; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE IF NOT EXISTS public.podcast_scripts (
    id integer NOT NULL,
    podcast_id integer NOT NULL,
    full_script text NOT NULL,
    script_version character varying(20) DEFAULT 'v1'::character varying,
    total_segments integer,
    estimated_duration integer,
    generated_by character varying(50) DEFAULT 'gpt-4'::character varying,
    generation_prompt text,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    suggested_questions jsonb
);


--
-- Name: TABLE podcast_scripts; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.podcast_scripts IS '播客脚本表';


--
-- Name: podcast_scripts_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.podcast_scripts_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: podcast_scripts_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.podcast_scripts_id_seq OWNED BY public.podcast_scripts.id;


--
-- Name: podcasts; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE IF NOT EXISTS public.podcasts (
    id integer NOT NULL,
    user_id character varying(64) NOT NULL,
    title character varying(255) NOT NULL,
    description text,
    style character varying(50) DEFAULT 'deep_dive'::character varying,
    duration integer,
    cover_image character varying(512),
    generation_status character varying(20) DEFAULT 'pending'::character varying,
    generation_started_at timestamp without time zone,
    generation_completed_at timestamp without time zone,
    generation_error text,
    audio_url character varying(512),
    audio_cache_key character varying(255),
    play_count integer DEFAULT 0,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    source character varying(32) DEFAULT 'user_generated'::character varying,
    share_token character varying(32)
);


--
-- Name: TABLE podcasts; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.podcasts IS 'AI 播客主表';


--
-- Name: podcasts_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.podcasts_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: podcasts_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.podcasts_id_seq OWNED BY public.podcasts.id;


--
-- Name: source_proposals; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE IF NOT EXISTS public.source_proposals (
    id bigint NOT NULL,
    vertical_id integer NOT NULL,
    source_url text NOT NULL,
    source_type character varying(32) DEFAULT 'rss'::character varying NOT NULL,
    evidence text DEFAULT ''::text,
    status character varying(16) DEFAULT 'pending'::character varying NOT NULL,
    proposed_by character varying(16) DEFAULT 'scout'::character varying NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    decided_at timestamp with time zone
);


--
-- Name: source_proposals_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.source_proposals_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: source_proposals_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.source_proposals_id_seq OWNED BY public.source_proposals.id;


--
-- Name: source_types; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE IF NOT EXISTS public.source_types (
    id character varying(64) NOT NULL,
    name character varying(50) NOT NULL,
    display_name character varying(100) NOT NULL,
    description text,
    is_active boolean DEFAULT true,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: tts_cache; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE IF NOT EXISTS public.tts_cache (
    id integer NOT NULL,
    global_article_id integer NOT NULL,
    voice character varying(50) NOT NULL,
    engine character varying(50) NOT NULL,
    cache_key character varying(255) NOT NULL,
    file_path character varying(512) NOT NULL,
    file_size integer,
    duration_seconds integer,
    format character varying(10) DEFAULT 'mp3'::character varying,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    last_accessed_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    access_count integer DEFAULT 0
);


--
-- Name: tts_cache_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.tts_cache_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: tts_cache_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.tts_cache_id_seq OWNED BY public.tts_cache.id;


--
-- Name: user_article_refs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE IF NOT EXISTS public.user_article_refs (
    id integer NOT NULL,
    user_id character varying(64) NOT NULL,
    global_article_id integer NOT NULL,
    legacy_article_id integer,
    feed_id integer NOT NULL,
    user_summary text,
    is_favorited boolean DEFAULT false,
    folder_name character varying(100),
    user_tags text[],
    notes text,
    fetched_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: user_article_refs_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.user_article_refs_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: user_article_refs_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.user_article_refs_id_seq OWNED BY public.user_article_refs.id;


--
-- Name: user_feedback; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE IF NOT EXISTS public.user_feedback (
    id integer NOT NULL,
    user_id character varying(64) NOT NULL,
    message text NOT NULL,
    attach_logs boolean DEFAULT false,
    status character varying(20) DEFAULT 'open'::character varying,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    frontend_logs jsonb DEFAULT '[]'::jsonb,
    CONSTRAINT user_feedback_status_check CHECK (((status)::text = ANY ((ARRAY['open'::character varying, 'resolved'::character varying, 'ignored'::character varying])::text[])))
);


--
-- Name: user_feedback_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.user_feedback_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: user_feedback_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.user_feedback_id_seq OWNED BY public.user_feedback.id;


--
-- Name: user_feeds; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE IF NOT EXISTS public.user_feeds (
    id integer NOT NULL,
    user_id character varying(64) NOT NULL,
    source_type_id character varying(64) NOT NULL,
    feed_name character varying(255) NOT NULL,
    feed_url text NOT NULL,
    feed_config jsonb DEFAULT '{}'::jsonb,
    is_active boolean DEFAULT true,
    last_fetched_at timestamp with time zone,
    fetch_interval_minutes integer DEFAULT 60,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    platform character varying(50) DEFAULT 'rss'::character varying NOT NULL
);


--
-- Name: COLUMN user_feeds.platform; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.user_feeds.platform IS 'Feed platform type: rss, wechat, bilibili, twitter, xiaohongshu, etc.';


--
-- Name: user_feeds_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.user_feeds_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: user_feeds_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.user_feeds_id_seq OWNED BY public.user_feeds.id;


--
-- Name: user_playback_state; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE IF NOT EXISTS public.user_playback_state (
    user_id character varying(64) NOT NULL,
    playlist jsonb DEFAULT '[]'::jsonb NOT NULL,
    current_index integer DEFAULT 0 NOT NULL,
    "current_time" double precision DEFAULT 0 NOT NULL,
    total_time double precision DEFAULT 0 NOT NULL,
    current_article jsonb,
    is_playing boolean DEFAULT false NOT NULL,
    playback_rate double precision DEFAULT 1.0 NOT NULL,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: user_queues; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE IF NOT EXISTS public.user_queues (
    user_id character varying(64) NOT NULL,
    items jsonb DEFAULT '[]'::jsonb NOT NULL,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: user_reading_history; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE IF NOT EXISTS public.user_reading_history (
    id integer NOT NULL,
    user_id character varying(64) NOT NULL,
    article_id integer,
    is_read boolean DEFAULT false,
    read_at timestamp without time zone,
    read_duration integer DEFAULT 0,
    scroll_position double precision DEFAULT 0,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    global_article_id integer
);


--
-- Name: user_reading_history_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.user_reading_history_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: user_reading_history_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.user_reading_history_id_seq OWNED BY public.user_reading_history.id;


--
-- Name: user_saved_articles; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE IF NOT EXISTS public.user_saved_articles (
    id integer NOT NULL,
    user_id character varying(64) NOT NULL,
    article_id integer,
    folder_name character varying(100),
    notes text,
    tags text[],
    saved_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    global_article_id integer
);


--
-- Name: user_saved_articles_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.user_saved_articles_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: user_saved_articles_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.user_saved_articles_id_seq OWNED BY public.user_saved_articles.id;


--
-- Name: user_sessions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE IF NOT EXISTS public.user_sessions (
    id integer NOT NULL,
    user_id character varying(64) NOT NULL,
    token_hash character varying(255) NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    last_accessed timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: user_sessions_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.user_sessions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: user_sessions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.user_sessions_id_seq OWNED BY public.user_sessions.id;


--
-- Name: user_usage_daily; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE IF NOT EXISTS public.user_usage_daily (
    id integer NOT NULL,
    user_id character varying(64) NOT NULL,
    usage_date date DEFAULT CURRENT_DATE NOT NULL,
    tts_count integer DEFAULT 0,
    tts_characters integer DEFAULT 0,
    podcast_count integer DEFAULT 0,
    ai_summary_count integer DEFAULT 0,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: COLUMN user_usage_daily.podcast_count; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.user_usage_daily.podcast_count IS '今日播客生成数';


--
-- Name: user_usage_daily_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.user_usage_daily_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: user_usage_daily_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.user_usage_daily_id_seq OWNED BY public.user_usage_daily.id;


--
-- Name: users; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE IF NOT EXISTS public.users (
    id character varying(64) NOT NULL,
    username character varying(50) NOT NULL,
    email character varying(100) NOT NULL,
    full_name character varying(100),
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    password_hash character varying(255),
    is_active boolean DEFAULT true,
    is_superuser boolean DEFAULT false,
    avatar_url text,
    auto_refresh_enabled boolean DEFAULT true NOT NULL,
    preferred_language character varying(10) DEFAULT 'en'::character varying,
    auto_podcast_enabled boolean DEFAULT false NOT NULL,
    auth_provider character varying(20) DEFAULT 'password'::character varying,
    first_podcast_grace_credit_used boolean DEFAULT false,
    invite_code_status character varying(20) DEFAULT NULL::character varying,
    tts_voice_zh character varying(100) DEFAULT NULL::character varying,
    tts_voice_en character varying(100) DEFAULT NULL::character varying
);


--
-- Name: COLUMN users.auto_refresh_enabled; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.users.auto_refresh_enabled IS 'Controls whether user feeds are included in scheduled automatic refreshes.';


--
-- Name: v_articles; Type: VIEW; Schema: public; Owner: -
--

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
   FROM ((public.articles a
     JOIN public.user_feeds uf ON ((a.feed_id = uf.id)))
     JOIN public.source_types st ON (((a.source_type_id)::text = (st.id)::text)));


--
-- Name: v_user_feeds; Type: VIEW; Schema: public; Owner: -
--

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
           FROM public.articles a
          WHERE (a.feed_id = uf.id)) AS article_count,
    ( SELECT max(a.published_at) AS max
           FROM public.articles a
          WHERE (a.feed_id = uf.id)) AS latest_article_date
   FROM (public.user_feeds uf
     JOIN public.source_types st ON (((uf.source_type_id)::text = (st.id)::text)));


--
-- Name: article_summaries id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.article_summaries ALTER COLUMN id SET DEFAULT nextval('public.article_summaries_id_seq'::regclass);


--
-- Name: articles id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.articles ALTER COLUMN id SET DEFAULT nextval('public.articles_id_seq'::regclass);


--
-- Name: audio_play_history id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.audio_play_history ALTER COLUMN id SET DEFAULT nextval('public.audio_play_history_id_seq'::regclass);


--
-- Name: feed_update_logs id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.feed_update_logs ALTER COLUMN id SET DEFAULT nextval('public.feed_update_logs_id_seq'::regclass);


--
-- Name: feed_validation id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.feed_validation ALTER COLUMN id SET DEFAULT nextval('public.feed_validation_id_seq'::regclass);


--
-- Name: global_articles id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.global_articles ALTER COLUMN id SET DEFAULT nextval('public.global_articles_id_seq'::regclass);


--
-- Name: podcast_articles id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.podcast_articles ALTER COLUMN id SET DEFAULT nextval('public.podcast_articles_id_seq'::regclass);


--
-- Name: podcast_conversations id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.podcast_conversations ALTER COLUMN id SET DEFAULT nextval('public.podcast_conversations_id_seq'::regclass);


--
-- Name: podcast_play_progress id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.podcast_play_progress ALTER COLUMN id SET DEFAULT nextval('public.podcast_play_progress_id_seq'::regclass);


--
-- Name: podcast_scripts id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.podcast_scripts ALTER COLUMN id SET DEFAULT nextval('public.podcast_scripts_id_seq'::regclass);


--
-- Name: podcasts id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.podcasts ALTER COLUMN id SET DEFAULT nextval('public.podcasts_id_seq'::regclass);


--
-- Name: source_proposals id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.source_proposals ALTER COLUMN id SET DEFAULT nextval('public.source_proposals_id_seq'::regclass);


--
-- Name: tts_cache id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tts_cache ALTER COLUMN id SET DEFAULT nextval('public.tts_cache_id_seq'::regclass);


--
-- Name: user_article_refs id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_article_refs ALTER COLUMN id SET DEFAULT nextval('public.user_article_refs_id_seq'::regclass);


--
-- Name: user_feedback id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_feedback ALTER COLUMN id SET DEFAULT nextval('public.user_feedback_id_seq'::regclass);


--
-- Name: user_feeds id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_feeds ALTER COLUMN id SET DEFAULT nextval('public.user_feeds_id_seq'::regclass);


--
-- Name: user_reading_history id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_reading_history ALTER COLUMN id SET DEFAULT nextval('public.user_reading_history_id_seq'::regclass);


--
-- Name: user_saved_articles id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_saved_articles ALTER COLUMN id SET DEFAULT nextval('public.user_saved_articles_id_seq'::regclass);


--
-- Name: user_sessions id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_sessions ALTER COLUMN id SET DEFAULT nextval('public.user_sessions_id_seq'::regclass);


--
-- Name: user_usage_daily id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_usage_daily ALTER COLUMN id SET DEFAULT nextval('public.user_usage_daily_id_seq'::regclass);


--
-- Name: article_summaries article_summaries_global_article_id_language_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.article_summaries
    ADD CONSTRAINT article_summaries_global_article_id_language_key UNIQUE (global_article_id, language);


--
-- Name: article_summaries article_summaries_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.article_summaries
    ADD CONSTRAINT article_summaries_pkey PRIMARY KEY (id);


--
-- Name: articles articles_feed_id_url_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.articles
    ADD CONSTRAINT articles_feed_id_url_key UNIQUE (feed_id, url);


--
-- Name: articles articles_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.articles
    ADD CONSTRAINT articles_pkey PRIMARY KEY (id);


--
-- Name: audio_play_history audio_play_history_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.audio_play_history
    ADD CONSTRAINT audio_play_history_pkey PRIMARY KEY (id);


--
-- Name: audio_play_history audio_play_history_user_id_item_type_item_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.audio_play_history
    ADD CONSTRAINT audio_play_history_user_id_item_type_item_id_key UNIQUE (user_id, item_type, item_id);


--
-- Name: feed_update_logs feed_update_logs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.feed_update_logs
    ADD CONSTRAINT feed_update_logs_pkey PRIMARY KEY (id);


--
-- Name: feed_validation feed_validation_feed_url_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.feed_validation
    ADD CONSTRAINT feed_validation_feed_url_key UNIQUE (feed_url);


--
-- Name: feed_validation feed_validation_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.feed_validation
    ADD CONSTRAINT feed_validation_pkey PRIMARY KEY (id);


--
-- Name: global_articles global_articles_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.global_articles
    ADD CONSTRAINT global_articles_pkey PRIMARY KEY (id);


--
-- Name: global_articles global_articles_url_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.global_articles
    ADD CONSTRAINT global_articles_url_key UNIQUE (url);


--
-- Name: podcast_articles podcast_articles_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.podcast_articles
    ADD CONSTRAINT podcast_articles_pkey PRIMARY KEY (id);


--
-- Name: podcast_articles podcast_articles_podcast_id_article_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.podcast_articles
    ADD CONSTRAINT podcast_articles_podcast_id_article_id_key UNIQUE (podcast_id, article_id);


--
-- Name: podcast_conversations podcast_conversations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.podcast_conversations
    ADD CONSTRAINT podcast_conversations_pkey PRIMARY KEY (id);


--
-- Name: podcast_play_progress podcast_play_progress_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.podcast_play_progress
    ADD CONSTRAINT podcast_play_progress_pkey PRIMARY KEY (id);


--
-- Name: podcast_play_progress podcast_play_progress_user_id_podcast_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.podcast_play_progress
    ADD CONSTRAINT podcast_play_progress_user_id_podcast_id_key UNIQUE (user_id, podcast_id);


--
-- Name: podcast_scripts podcast_scripts_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.podcast_scripts
    ADD CONSTRAINT podcast_scripts_pkey PRIMARY KEY (id);


--
-- Name: podcasts podcasts_audio_cache_key_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.podcasts
    ADD CONSTRAINT podcasts_audio_cache_key_key UNIQUE (audio_cache_key);


--
-- Name: podcasts podcasts_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.podcasts
    ADD CONSTRAINT podcasts_pkey PRIMARY KEY (id);


--
-- Name: podcasts podcasts_share_token_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.podcasts
    ADD CONSTRAINT podcasts_share_token_key UNIQUE (share_token);


--
-- Name: source_proposals source_proposals_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.source_proposals
    ADD CONSTRAINT source_proposals_pkey PRIMARY KEY (id);


--
-- Name: source_types source_types_name_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.source_types
    ADD CONSTRAINT source_types_name_key UNIQUE (name);


--
-- Name: source_types source_types_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.source_types
    ADD CONSTRAINT source_types_pkey PRIMARY KEY (id);


--
-- Name: tts_cache tts_cache_cache_key_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tts_cache
    ADD CONSTRAINT tts_cache_cache_key_key UNIQUE (cache_key);


--
-- Name: tts_cache tts_cache_global_article_id_voice_engine_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tts_cache
    ADD CONSTRAINT tts_cache_global_article_id_voice_engine_key UNIQUE (global_article_id, voice, engine);


--
-- Name: tts_cache tts_cache_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tts_cache
    ADD CONSTRAINT tts_cache_pkey PRIMARY KEY (id);


--
-- Name: user_reading_history unique_user_reading_global_article; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_reading_history
    ADD CONSTRAINT unique_user_reading_global_article UNIQUE (user_id, global_article_id);


--
-- Name: user_saved_articles unique_user_saved_global_article; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_saved_articles
    ADD CONSTRAINT unique_user_saved_global_article UNIQUE (user_id, global_article_id);


--
-- Name: user_article_refs user_article_refs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_article_refs
    ADD CONSTRAINT user_article_refs_pkey PRIMARY KEY (id);


--
-- Name: user_article_refs user_article_refs_user_id_global_article_id_feed_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_article_refs
    ADD CONSTRAINT user_article_refs_user_id_global_article_id_feed_id_key UNIQUE (user_id, global_article_id, feed_id);


--
-- Name: user_feedback user_feedback_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_feedback
    ADD CONSTRAINT user_feedback_pkey PRIMARY KEY (id);


--
-- Name: user_feeds user_feeds_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_feeds
    ADD CONSTRAINT user_feeds_pkey PRIMARY KEY (id);


--
-- Name: user_feeds user_feeds_user_id_feed_url_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_feeds
    ADD CONSTRAINT user_feeds_user_id_feed_url_key UNIQUE (user_id, feed_url);


--
-- Name: user_playback_state user_playback_state_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_playback_state
    ADD CONSTRAINT user_playback_state_pkey PRIMARY KEY (user_id);


--
-- Name: user_queues user_queues_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_queues
    ADD CONSTRAINT user_queues_pkey PRIMARY KEY (user_id);


--
-- Name: user_reading_history user_reading_history_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_reading_history
    ADD CONSTRAINT user_reading_history_pkey PRIMARY KEY (id);


--
-- Name: user_reading_history user_reading_history_user_id_article_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_reading_history
    ADD CONSTRAINT user_reading_history_user_id_article_id_key UNIQUE (user_id, article_id);


--
-- Name: user_saved_articles user_saved_articles_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_saved_articles
    ADD CONSTRAINT user_saved_articles_pkey PRIMARY KEY (id);


--
-- Name: user_saved_articles user_saved_articles_user_id_article_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_saved_articles
    ADD CONSTRAINT user_saved_articles_user_id_article_id_key UNIQUE (user_id, article_id);


--
-- Name: user_sessions user_sessions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_sessions
    ADD CONSTRAINT user_sessions_pkey PRIMARY KEY (id);


--
-- Name: user_usage_daily user_usage_daily_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_usage_daily
    ADD CONSTRAINT user_usage_daily_pkey PRIMARY KEY (id);


--
-- Name: user_usage_daily user_usage_daily_user_id_usage_date_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_usage_daily
    ADD CONSTRAINT user_usage_daily_user_id_usage_date_key UNIQUE (user_id, usage_date);


--
-- Name: users users_email_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_email_key UNIQUE (email);


--
-- Name: users users_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);


--
-- Name: users users_username_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_username_key UNIQUE (username);


--
-- Name: idx_article_summaries_article; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_article_summaries_article ON public.article_summaries USING btree (global_article_id);


--
-- Name: idx_article_summaries_lang; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_article_summaries_lang ON public.article_summaries USING btree (language);


--
-- Name: idx_articles_content_search; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_articles_content_search ON public.articles USING gin (to_tsvector('simple'::regconfig, COALESCE(content, summary)));


--
-- Name: idx_articles_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_articles_created_at ON public.articles USING btree (created_at);


--
-- Name: idx_articles_feed_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_articles_feed_id ON public.articles USING btree (feed_id);


--
-- Name: idx_articles_published_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_articles_published_at ON public.articles USING btree (published_at);


--
-- Name: idx_articles_source; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_articles_source ON public.articles USING btree (source);


--
-- Name: idx_articles_title_search; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_articles_title_search ON public.articles USING gin (to_tsvector('simple'::regconfig, title));


--
-- Name: idx_audio_history_global; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_audio_history_global ON public.audio_play_history USING btree (global_article_id);


--
-- Name: idx_audio_history_item; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_audio_history_item ON public.audio_play_history USING btree (item_type, item_id);


--
-- Name: idx_audio_history_user_played; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_audio_history_user_played ON public.audio_play_history USING btree (user_id, played_at DESC);


--
-- Name: idx_audio_history_user_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_audio_history_user_type ON public.audio_play_history USING btree (user_id, item_type);


--
-- Name: idx_conversations_podcast; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_conversations_podcast ON public.podcast_conversations USING btree (podcast_id);


--
-- Name: idx_conversations_user; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_conversations_user ON public.podcast_conversations USING btree (user_id);


--
-- Name: idx_feed_update_logs_feed_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_feed_update_logs_feed_id ON public.feed_update_logs USING btree (feed_id);


--
-- Name: idx_feed_update_logs_started; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_feed_update_logs_started ON public.feed_update_logs USING btree (started_at DESC);


--
-- Name: idx_feed_validation_valid; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_feed_validation_valid ON public.feed_validation USING btree (is_valid, language);


--
-- Name: idx_feed_validation_validated_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_feed_validation_validated_at ON public.feed_validation USING btree (last_validated_at);


--
-- Name: idx_global_articles_content_hash; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_global_articles_content_hash ON public.global_articles USING btree (content_hash);


--
-- Name: idx_global_articles_content_search; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_global_articles_content_search ON public.global_articles USING gin (to_tsvector('simple'::regconfig, COALESCE(content, summary)));


--
-- Name: idx_global_articles_first_seen; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_global_articles_first_seen ON public.global_articles USING btree (first_seen_at);


--
-- Name: idx_global_articles_published; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_global_articles_published ON public.global_articles USING btree (published_at DESC);


--
-- Name: idx_global_articles_source_feed_url; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_global_articles_source_feed_url ON public.global_articles USING btree (source_feed_url);


--
-- Name: idx_global_articles_title_search; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_global_articles_title_search ON public.global_articles USING gin (to_tsvector('simple'::regconfig, title));


--
-- Name: idx_global_articles_url; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_global_articles_url ON public.global_articles USING btree (url);


--
-- Name: idx_podcast_articles_global; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_podcast_articles_global ON public.podcast_articles USING btree (global_article_id);


--
-- Name: idx_podcast_articles_podcast; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_podcast_articles_podcast ON public.podcast_articles USING btree (podcast_id);


--
-- Name: idx_podcasts_share_token; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_podcasts_share_token ON public.podcasts USING btree (share_token) WHERE (share_token IS NOT NULL);


--
-- Name: idx_podcasts_user_source; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_podcasts_user_source ON public.podcasts USING btree (user_id, source);


--
-- Name: idx_podcasts_user_status_created; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_podcasts_user_status_created ON public.podcasts USING btree (user_id, generation_status, created_at DESC);


--
-- Name: idx_reading_global_article; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_reading_global_article ON public.user_reading_history USING btree (global_article_id);


--
-- Name: idx_reading_read_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_reading_read_at ON public.user_reading_history USING btree (read_at DESC);


--
-- Name: idx_reading_user_article; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_reading_user_article ON public.user_reading_history USING btree (user_id, article_id);


--
-- Name: idx_reading_user_is_read; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_reading_user_is_read ON public.user_reading_history USING btree (user_id, is_read);


--
-- Name: idx_source_proposals_pending_unique; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX idx_source_proposals_pending_unique ON public.source_proposals USING btree (vertical_id, source_url) WHERE ((status)::text = 'pending'::text);


--
-- Name: idx_source_proposals_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_source_proposals_status ON public.source_proposals USING btree (status);


--
-- Name: idx_tts_cache_article; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_tts_cache_article ON public.tts_cache USING btree (global_article_id);


--
-- Name: idx_tts_cache_key; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_tts_cache_key ON public.tts_cache USING btree (cache_key);


--
-- Name: idx_uar_global_article; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_uar_global_article ON public.user_article_refs USING btree (global_article_id);


--
-- Name: idx_uar_legacy_article; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_uar_legacy_article ON public.user_article_refs USING btree (legacy_article_id);


--
-- Name: idx_uar_user_article; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_uar_user_article ON public.user_article_refs USING btree (user_id, global_article_id);


--
-- Name: idx_uar_user_feed; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_uar_user_feed ON public.user_article_refs USING btree (user_id, feed_id);


--
-- Name: idx_user_feedback_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_user_feedback_created_at ON public.user_feedback USING btree (created_at DESC);


--
-- Name: idx_user_feedback_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_user_feedback_status ON public.user_feedback USING btree (status);


--
-- Name: idx_user_feedback_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_user_feedback_user_id ON public.user_feedback USING btree (user_id);


--
-- Name: idx_user_feeds_active; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_user_feeds_active ON public.user_feeds USING btree (is_active);


--
-- Name: idx_user_feeds_last_fetched; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_user_feeds_last_fetched ON public.user_feeds USING btree (last_fetched_at);


--
-- Name: idx_user_feeds_platform; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_user_feeds_platform ON public.user_feeds USING btree (platform);


--
-- Name: idx_user_feeds_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_user_feeds_user_id ON public.user_feeds USING btree (user_id);


--
-- Name: idx_user_playback_state_updated_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_user_playback_state_updated_at ON public.user_playback_state USING btree (updated_at DESC);


--
-- Name: idx_user_queues_updated_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_user_queues_updated_at ON public.user_queues USING btree (updated_at DESC);


--
-- Name: idx_user_saved_article; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_user_saved_article ON public.user_saved_articles USING btree (article_id);


--
-- Name: idx_user_saved_global_article; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_user_saved_global_article ON public.user_saved_articles USING btree (global_article_id);


--
-- Name: idx_user_saved_user; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_user_saved_user ON public.user_saved_articles USING btree (user_id);


--
-- Name: idx_user_sessions_expires; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_user_sessions_expires ON public.user_sessions USING btree (expires_at);


--
-- Name: idx_user_sessions_token; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_user_sessions_token ON public.user_sessions USING btree (token_hash);


--
-- Name: idx_user_sessions_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_user_sessions_user_id ON public.user_sessions USING btree (user_id);


--
-- Name: idx_user_usage_date; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_user_usage_date ON public.user_usage_daily USING btree (usage_date);


--
-- Name: idx_users_auto_podcast; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_users_auto_podcast ON public.users USING btree (auto_podcast_enabled) WHERE (auto_podcast_enabled = true);


--
-- Name: idx_users_auto_refresh; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_users_auto_refresh ON public.users USING btree (auto_refresh_enabled) WHERE (auto_refresh_enabled = true);


--
-- Name: article_summaries update_article_summaries_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER update_article_summaries_updated_at BEFORE UPDATE ON public.article_summaries FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();


--
-- Name: articles update_articles_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER update_articles_updated_at BEFORE UPDATE ON public.articles FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();


--
-- Name: feed_validation update_feed_validation_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER update_feed_validation_updated_at BEFORE UPDATE ON public.feed_validation FOR EACH ROW EXECUTE FUNCTION public.update_feed_validation_updated_at_column();


--
-- Name: global_articles update_global_articles_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER update_global_articles_updated_at BEFORE UPDATE ON public.global_articles FOR EACH ROW EXECUTE FUNCTION public.update_last_updated_at_column();


--
-- Name: podcast_play_progress update_podcast_play_progress_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER update_podcast_play_progress_updated_at BEFORE UPDATE ON public.podcast_play_progress FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();


--
-- Name: podcasts update_podcasts_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER update_podcasts_updated_at BEFORE UPDATE ON public.podcasts FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();


--
-- Name: user_feedback update_user_feedback_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER update_user_feedback_updated_at BEFORE UPDATE ON public.user_feedback FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();


--
-- Name: user_feeds update_user_feeds_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER update_user_feeds_updated_at BEFORE UPDATE ON public.user_feeds FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();


--
-- Name: user_playback_state update_user_playback_state_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER update_user_playback_state_updated_at BEFORE UPDATE ON public.user_playback_state FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();


--
-- Name: user_queues update_user_queues_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER update_user_queues_updated_at BEFORE UPDATE ON public.user_queues FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();


--
-- Name: users update_users_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER update_users_updated_at BEFORE UPDATE ON public.users FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();


--
-- Name: article_summaries article_summaries_global_article_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.article_summaries
    ADD CONSTRAINT article_summaries_global_article_id_fkey FOREIGN KEY (global_article_id) REFERENCES public.global_articles(id) ON DELETE CASCADE;


--
-- Name: articles articles_feed_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.articles
    ADD CONSTRAINT articles_feed_id_fkey FOREIGN KEY (feed_id) REFERENCES public.user_feeds(id) ON DELETE CASCADE;


--
-- Name: articles articles_source_type_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.articles
    ADD CONSTRAINT articles_source_type_id_fkey FOREIGN KEY (source_type_id) REFERENCES public.source_types(id);


--
-- Name: audio_play_history audio_play_history_global_article_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.audio_play_history
    ADD CONSTRAINT audio_play_history_global_article_id_fkey FOREIGN KEY (global_article_id) REFERENCES public.global_articles(id) ON DELETE CASCADE;


--
-- Name: audio_play_history audio_play_history_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.audio_play_history
    ADD CONSTRAINT audio_play_history_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: global_articles global_articles_source_type_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.global_articles
    ADD CONSTRAINT global_articles_source_type_id_fkey FOREIGN KEY (source_type_id) REFERENCES public.source_types(id);


--
-- Name: podcast_articles podcast_articles_article_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.podcast_articles
    ADD CONSTRAINT podcast_articles_article_id_fkey FOREIGN KEY (article_id) REFERENCES public.articles(id) ON DELETE CASCADE;


--
-- Name: podcast_articles podcast_articles_global_article_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.podcast_articles
    ADD CONSTRAINT podcast_articles_global_article_id_fkey FOREIGN KEY (global_article_id) REFERENCES public.global_articles(id) ON DELETE CASCADE;


--
-- Name: podcast_articles podcast_articles_podcast_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.podcast_articles
    ADD CONSTRAINT podcast_articles_podcast_id_fkey FOREIGN KEY (podcast_id) REFERENCES public.podcasts(id) ON DELETE CASCADE;


--
-- Name: podcast_conversations podcast_conversations_parent_conversation_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.podcast_conversations
    ADD CONSTRAINT podcast_conversations_parent_conversation_id_fkey FOREIGN KEY (parent_conversation_id) REFERENCES public.podcast_conversations(id);


--
-- Name: podcast_conversations podcast_conversations_podcast_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.podcast_conversations
    ADD CONSTRAINT podcast_conversations_podcast_id_fkey FOREIGN KEY (podcast_id) REFERENCES public.podcasts(id) ON DELETE CASCADE;


--
-- Name: podcast_conversations podcast_conversations_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.podcast_conversations
    ADD CONSTRAINT podcast_conversations_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: podcast_play_progress podcast_play_progress_podcast_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.podcast_play_progress
    ADD CONSTRAINT podcast_play_progress_podcast_id_fkey FOREIGN KEY (podcast_id) REFERENCES public.podcasts(id) ON DELETE CASCADE;


--
-- Name: podcast_play_progress podcast_play_progress_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.podcast_play_progress
    ADD CONSTRAINT podcast_play_progress_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: podcast_scripts podcast_scripts_podcast_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.podcast_scripts
    ADD CONSTRAINT podcast_scripts_podcast_id_fkey FOREIGN KEY (podcast_id) REFERENCES public.podcasts(id) ON DELETE CASCADE;


--
-- Name: podcasts podcasts_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.podcasts
    ADD CONSTRAINT podcasts_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: tts_cache tts_cache_global_article_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tts_cache
    ADD CONSTRAINT tts_cache_global_article_id_fkey FOREIGN KEY (global_article_id) REFERENCES public.global_articles(id) ON DELETE CASCADE;


--
-- Name: user_article_refs user_article_refs_feed_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_article_refs
    ADD CONSTRAINT user_article_refs_feed_id_fkey FOREIGN KEY (feed_id) REFERENCES public.user_feeds(id) ON DELETE CASCADE;


--
-- Name: user_article_refs user_article_refs_global_article_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_article_refs
    ADD CONSTRAINT user_article_refs_global_article_id_fkey FOREIGN KEY (global_article_id) REFERENCES public.global_articles(id) ON DELETE CASCADE;


--
-- Name: user_article_refs user_article_refs_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_article_refs
    ADD CONSTRAINT user_article_refs_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: user_feedback user_feedback_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_feedback
    ADD CONSTRAINT user_feedback_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: user_feeds user_feeds_source_type_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_feeds
    ADD CONSTRAINT user_feeds_source_type_id_fkey FOREIGN KEY (source_type_id) REFERENCES public.source_types(id);


--
-- Name: user_feeds user_feeds_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_feeds
    ADD CONSTRAINT user_feeds_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: user_playback_state user_playback_state_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_playback_state
    ADD CONSTRAINT user_playback_state_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: user_queues user_queues_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_queues
    ADD CONSTRAINT user_queues_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: user_reading_history user_reading_history_global_article_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_reading_history
    ADD CONSTRAINT user_reading_history_global_article_id_fkey FOREIGN KEY (global_article_id) REFERENCES public.global_articles(id) ON DELETE CASCADE;


--
-- Name: user_reading_history user_reading_history_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_reading_history
    ADD CONSTRAINT user_reading_history_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: user_saved_articles user_saved_articles_global_article_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_saved_articles
    ADD CONSTRAINT user_saved_articles_global_article_id_fkey FOREIGN KEY (global_article_id) REFERENCES public.global_articles(id) ON DELETE CASCADE;


--
-- Name: user_saved_articles user_saved_articles_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_saved_articles
    ADD CONSTRAINT user_saved_articles_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: user_sessions user_sessions_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_sessions
    ADD CONSTRAINT user_sessions_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: user_usage_daily user_usage_daily_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_usage_daily
    ADD CONSTRAINT user_usage_daily_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Readaria schema initialization complete
--
