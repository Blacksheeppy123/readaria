-- Week 3: Saved articles and reading history tables
-- Migration: 2025_11_02_user_saved_and_reading.sql

BEGIN;

-- user_saved_articles: per-user saved/starred articles
CREATE TABLE IF NOT EXISTS user_saved_articles (
  id SERIAL PRIMARY KEY,
  user_id VARCHAR(64) NOT NULL,
  article_id INTEGER NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
  folder_name VARCHAR(100),
  notes TEXT,
  tags TEXT[],
  saved_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(user_id, article_id)
);

CREATE INDEX IF NOT EXISTS idx_user_saved_user ON user_saved_articles(user_id);
CREATE INDEX IF NOT EXISTS idx_user_saved_article ON user_saved_articles(article_id);

-- user_reading_history: per-user read/unread + progress
CREATE TABLE IF NOT EXISTS user_reading_history (
  id SERIAL PRIMARY KEY,
  user_id VARCHAR(64) NOT NULL,
  article_id INTEGER NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
  is_read BOOLEAN DEFAULT false,
  read_at TIMESTAMP,
  read_duration INTEGER DEFAULT 0,
  scroll_position FLOAT DEFAULT 0,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(user_id, article_id)
);

CREATE INDEX IF NOT EXISTS idx_reading_user_article ON user_reading_history(user_id, article_id);
CREATE INDEX IF NOT EXISTS idx_reading_user_is_read ON user_reading_history(user_id, is_read);
CREATE INDEX IF NOT EXISTS idx_reading_read_at ON user_reading_history(read_at DESC);

COMMIT;

