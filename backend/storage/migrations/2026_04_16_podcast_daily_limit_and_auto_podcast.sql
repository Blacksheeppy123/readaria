-- 2026-04-16: 添加自动播客生成开关；用量按日统计

-- 1. 为 users 表添加 auto_podcast_enabled 字段，默认启用
ALTER TABLE users
ADD COLUMN IF NOT EXISTS auto_podcast_enabled BOOLEAN NOT NULL DEFAULT true;

CREATE INDEX IF NOT EXISTS idx_users_auto_podcast ON users(auto_podcast_enabled) WHERE auto_podcast_enabled = true;

-- 2. 更新 user_usage_daily 表注释（podcast_count 按日计算）
COMMENT ON COLUMN user_usage_daily.podcast_count IS '今日播客生成数';
