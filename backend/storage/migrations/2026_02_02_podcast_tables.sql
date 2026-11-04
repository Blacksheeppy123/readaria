-- AI 播客功能数据库迁移
-- 创建日期: 2026-02-02
-- 版本: 1.0

-- 1. 播客主表
CREATE TABLE IF NOT EXISTS podcasts (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title VARCHAR(255) NOT NULL,
    description TEXT,
    style VARCHAR(50) DEFAULT 'deep_dive',
    duration INTEGER,  -- 播客时长（秒）
    cover_image VARCHAR(512),
    generation_status VARCHAR(20) DEFAULT 'pending',  -- pending/generating/completed/failed
    generation_started_at TIMESTAMP,
    generation_completed_at TIMESTAMP,
    generation_error TEXT,
    audio_url VARCHAR(512),
    audio_cache_key VARCHAR(255) UNIQUE,
    play_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_podcasts_user_status_created
ON podcasts(user_id, generation_status, created_at DESC);

-- 2. 播客-文章关联表
CREATE TABLE IF NOT EXISTS podcast_articles (
    id SERIAL PRIMARY KEY,
    podcast_id INTEGER NOT NULL REFERENCES podcasts(id) ON DELETE CASCADE,
    article_id INTEGER NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
    sequence_order INTEGER NOT NULL,  -- 文章在播客中的顺序
    importance_score FLOAT DEFAULT 0.5,  -- 文章重要性评分
    start_time INTEGER,  -- 章节开始时间（秒）
    end_time INTEGER,    -- 章节结束时间（秒）
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(podcast_id, article_id)
);

CREATE INDEX IF NOT EXISTS idx_podcast_articles_podcast
ON podcast_articles(podcast_id);

-- 3. 播客脚本表
CREATE TABLE IF NOT EXISTS podcast_scripts (
    id SERIAL PRIMARY KEY,
    podcast_id INTEGER NOT NULL REFERENCES podcasts(id) ON DELETE CASCADE,
    full_script TEXT NOT NULL,  -- JSON 格式的完整脚本
    script_version VARCHAR(20) DEFAULT 'v1',
    total_segments INTEGER,  -- 脚本段落总数
    estimated_duration INTEGER,  -- 预估时长（秒）
    generated_by VARCHAR(50) DEFAULT 'gpt-4',
    generation_prompt TEXT,  -- 生成脚本使用的 prompt
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 4. 播客对话历史表
CREATE TABLE IF NOT EXISTS podcast_conversations (
    id SERIAL PRIMARY KEY,
    podcast_id INTEGER NOT NULL REFERENCES podcasts(id) ON DELETE CASCADE,
    user_id VARCHAR(64) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    user_message TEXT NOT NULL,
    assistant_message TEXT NOT NULL,
    context_article_ids INTEGER[],  -- 相关文章 ID 列表
    context_segments JSONB,  -- 相关脚本片段
    conversation_index INTEGER DEFAULT 0,  -- 对话序号
    parent_conversation_id INTEGER REFERENCES podcast_conversations(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_conversations_podcast
ON podcast_conversations(podcast_id);

CREATE INDEX IF NOT EXISTS idx_conversations_user
ON podcast_conversations(user_id);

-- 5. 播客播放进度表
CREATE TABLE IF NOT EXISTS podcast_play_progress (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    podcast_id INTEGER NOT NULL REFERENCES podcasts(id) ON DELETE CASCADE,
    current_time INTEGER DEFAULT 0,  -- 当前播放位置（秒）- 与 API 字段名一致
    total_time INTEGER,  -- 总时长（秒）
    progress_percentage FLOAT DEFAULT 0,  -- 播放进度百分比
    is_completed BOOLEAN DEFAULT false,  -- 是否播放完成
    last_played_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, podcast_id)
);

-- 迁移现有表：将 current_position 重命名为 current_time（如果列存在）
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'podcast_play_progress'
        AND column_name = 'current_position'
    ) THEN
        ALTER TABLE podcast_play_progress
        RENAME COLUMN current_position TO current_time;
    END IF;
END $$;

-- 添加更新时间触发器
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_podcasts_updated_at BEFORE UPDATE ON podcasts
FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_podcast_play_progress_updated_at BEFORE UPDATE ON podcast_play_progress
FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- 添加注释
COMMENT ON TABLE podcasts IS 'AI 播客主表';
COMMENT ON TABLE podcast_articles IS '播客-文章关联表';
COMMENT ON TABLE podcast_scripts IS '播客脚本表';
COMMENT ON TABLE podcast_conversations IS '播客对话历史表';
COMMENT ON TABLE podcast_play_progress IS '播客播放进度表';
