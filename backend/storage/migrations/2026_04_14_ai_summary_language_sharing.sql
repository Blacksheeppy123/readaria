-- =============================================
-- Migration: AI Summary Cross-User Sharing by Language
-- Date: 2026-04-14
-- Description: Add user language preference and article_summaries cache table
-- =============================================

-- 1. Add user preferred language column
ALTER TABLE users ADD COLUMN IF NOT EXISTS preferred_language VARCHAR(10) DEFAULT 'en';

-- 2. Create article summaries cache table (cross-user sharing by language)
CREATE TABLE IF NOT EXISTS article_summaries (
    id SERIAL PRIMARY KEY,
    global_article_id INTEGER NOT NULL REFERENCES global_articles(id) ON DELETE CASCADE,
    language VARCHAR(10) NOT NULL DEFAULT 'en',
    summary TEXT NOT NULL,
    generated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(global_article_id, language)
);

CREATE INDEX IF NOT EXISTS idx_article_summaries_article ON article_summaries(global_article_id);
CREATE INDEX IF NOT EXISTS idx_article_summaries_lang ON article_summaries(language);

-- 3. Update timestamp trigger for article_summaries
DROP TRIGGER IF EXISTS update_article_summaries_updated_at ON article_summaries;
CREATE TRIGGER update_article_summaries_updated_at
    BEFORE UPDATE ON article_summaries
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
