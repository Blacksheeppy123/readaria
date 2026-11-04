-- Create feed_update_logs table for refresh status tracking
BEGIN;

CREATE TABLE IF NOT EXISTS feed_update_logs (
  id SERIAL PRIMARY KEY,
  feed_id INTEGER NOT NULL,
  started_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  completed_at TIMESTAMP,
  status VARCHAR(20), -- running, success, error
  articles_fetched INTEGER DEFAULT 0,
  stored_count INTEGER DEFAULT 0,
  failed_count INTEGER DEFAULT 0,
  error_message TEXT
);

CREATE INDEX IF NOT EXISTS idx_feed_update_logs_feed_id ON feed_update_logs(feed_id);
CREATE INDEX IF NOT EXISTS idx_feed_update_logs_started ON feed_update_logs(started_at DESC);

COMMIT;

