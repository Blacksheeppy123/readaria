-- User Queue and Playback State Sync
-- Migration: 2026_07_15_user_queue_and_playback_state.sql

BEGIN;

-- Listen queue: user-managed list of articles to listen to later.
CREATE TABLE IF NOT EXISTS user_queues (
    user_id VARCHAR(64) PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    items JSONB NOT NULL DEFAULT '[]',
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_user_queues_updated_at ON user_queues(updated_at DESC);

-- Active playback state: snapshot of the player on a device.
CREATE TABLE IF NOT EXISTS user_playback_state (
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

CREATE INDEX IF NOT EXISTS idx_user_playback_state_updated_at ON user_playback_state(updated_at DESC);

-- Reuse the generic updated_at trigger function if it exists.
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_user_queues_updated_at
    BEFORE UPDATE ON user_queues
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_user_playback_state_updated_at
    BEFORE UPDATE ON user_playback_state
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

COMMIT;
