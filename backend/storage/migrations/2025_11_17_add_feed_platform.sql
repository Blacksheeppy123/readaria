-- Week 5: Add platform field to user_feeds for multi-platform support
-- Migration: 2025_11_17_add_feed_platform.sql
-- Purpose: Support platform-specific handling (wechat, bilibili, rss, etc.)

BEGIN;

-- Add platform field to user_feeds (default 'rss' for existing feeds)
ALTER TABLE user_feeds
ADD COLUMN IF NOT EXISTS platform VARCHAR(50) DEFAULT 'rss' NOT NULL;

-- Add index for platform filtering
CREATE INDEX IF NOT EXISTS idx_user_feeds_platform ON user_feeds(platform);

-- Add comment for documentation
COMMENT ON COLUMN user_feeds.platform IS 'Feed platform type: rss, wechat, bilibili, twitter, xiaohongshu, etc. Used for platform-specific processing.';

-- Backfill existing feeds to 'rss' platform (already default, but ensure consistency)
UPDATE user_feeds SET platform = 'rss' WHERE platform IS NULL OR platform = '';

COMMIT;
