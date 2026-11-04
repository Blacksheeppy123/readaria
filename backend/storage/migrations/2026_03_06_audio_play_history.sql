-- Audio Play History: Track TTS and Podcast playback history
-- Migration: 2026_03_06_audio_play_history.sql

BEGIN;

-- audio_play_history: per-user audio playback history (TTS articles + Podcasts)
CREATE TABLE IF NOT EXISTS audio_play_history (
  id SERIAL PRIMARY KEY,
  user_id VARCHAR(64) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  item_type VARCHAR(20) NOT NULL CHECK (item_type IN ('article', 'podcast')),
  item_id INTEGER NOT NULL, -- article_id or podcast_id depending on item_type
  title VARCHAR(500),
  source_name VARCHAR(255),
  duration_seconds INTEGER DEFAULT 0, -- Total audio duration
  played_seconds INTEGER DEFAULT 0,   -- How much was actually played
  progress_percentage DOUBLE PRECISION DEFAULT 0,
  is_completed BOOLEAN DEFAULT false,
  played_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(user_id, item_type, item_id)
);

-- Indexes for efficient querying
CREATE INDEX IF NOT EXISTS idx_audio_history_user_played ON audio_play_history(user_id, played_at DESC);
CREATE INDEX IF NOT EXISTS idx_audio_history_user_type ON audio_play_history(user_id, item_type);
CREATE INDEX IF NOT EXISTS idx_audio_history_item ON audio_play_history(item_type, item_id);

COMMIT;
