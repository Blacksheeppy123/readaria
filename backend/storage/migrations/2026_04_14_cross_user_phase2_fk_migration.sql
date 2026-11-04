-- =============================================
-- Migration: Cross-User Content Sharing (Phase 2)
-- Date: 2026-04-14
-- Description: Migrate FK references from articles.id to global_articles.id
-- =============================================

-- Make legacy article_id nullable so new rows can use only global_article_id
ALTER TABLE user_saved_articles ALTER COLUMN article_id DROP NOT NULL;
ALTER TABLE user_reading_history ALTER COLUMN article_id DROP NOT NULL;

-- 1. user_saved_articles: add global_article_id
ALTER TABLE user_saved_articles
    ADD COLUMN IF NOT EXISTS global_article_id INTEGER REFERENCES global_articles(id) ON DELETE CASCADE;

-- Backfill from user_article_refs
UPDATE user_saved_articles usa
SET global_article_id = uar.global_article_id
FROM user_article_refs uar
WHERE usa.user_id = uar.user_id
  AND usa.article_id = uar.legacy_article_id
  AND usa.global_article_id IS NULL;

CREATE INDEX IF NOT EXISTS idx_user_saved_global_article ON user_saved_articles(global_article_id);

-- Deduplicate per (user_id, global_article_id) before adding unique constraint
DELETE FROM user_saved_articles
WHERE id IN (
    SELECT id FROM (
        SELECT id,
               ROW_NUMBER() OVER (
                   PARTITION BY user_id, global_article_id
                   ORDER BY saved_at DESC, id DESC
               ) as rn
        FROM user_saved_articles
        WHERE global_article_id IS NOT NULL
    ) sub
    WHERE sub.rn > 1
);

-- Add unique constraint for ON CONFLICT (user_id, global_article_id)
ALTER TABLE user_saved_articles
    ADD CONSTRAINT unique_user_saved_global_article UNIQUE (user_id, global_article_id);

-- 2. user_reading_history: add global_article_id
ALTER TABLE user_reading_history
    ADD COLUMN IF NOT EXISTS global_article_id INTEGER REFERENCES global_articles(id) ON DELETE CASCADE;

-- Backfill from user_article_refs
UPDATE user_reading_history urh
SET global_article_id = uar.global_article_id
FROM user_article_refs uar
WHERE urh.user_id = uar.user_id
  AND urh.article_id = uar.legacy_article_id
  AND urh.global_article_id IS NULL;

CREATE INDEX IF NOT EXISTS idx_reading_global_article ON user_reading_history(global_article_id);

-- Deduplicate per (user_id, global_article_id) before adding unique constraint
DELETE FROM user_reading_history
WHERE id IN (
    SELECT id FROM (
        SELECT id,
               ROW_NUMBER() OVER (
                   PARTITION BY user_id, global_article_id
                   ORDER BY is_read DESC, read_at DESC NULLS LAST, updated_at DESC, id DESC
               ) as rn
        FROM user_reading_history
        WHERE global_article_id IS NOT NULL
    ) sub
    WHERE sub.rn > 1
);

-- Add unique constraint for ON CONFLICT (user_id, global_article_id)
ALTER TABLE user_reading_history
    ADD CONSTRAINT unique_user_reading_global_article UNIQUE (user_id, global_article_id);

-- 3. podcast_articles: add global_article_id
ALTER TABLE podcast_articles
    ADD COLUMN IF NOT EXISTS global_article_id INTEGER REFERENCES global_articles(id) ON DELETE CASCADE;

-- Backfill from user_article_refs (podcast belongs to user, pick any uar with matching legacy_article_id)
UPDATE podcast_articles pa
SET global_article_id = uar.global_article_id
FROM podcasts p
JOIN user_article_refs uar ON uar.user_id = p.user_id
WHERE pa.podcast_id = p.id
  AND pa.article_id = uar.legacy_article_id
  AND pa.global_article_id IS NULL;

CREATE INDEX IF NOT EXISTS idx_podcast_articles_global ON podcast_articles(global_article_id);

-- 4. audio_play_history: add global_article_id (only for item_type='article')
ALTER TABLE audio_play_history
    ADD COLUMN IF NOT EXISTS global_article_id INTEGER REFERENCES global_articles(id) ON DELETE CASCADE;

-- Backfill from user_article_refs for articles
UPDATE audio_play_history aph
SET global_article_id = uar.global_article_id
FROM user_article_refs uar
WHERE aph.user_id = uar.user_id
  AND aph.item_type = 'article'
  AND aph.item_id = uar.legacy_article_id
  AND aph.global_article_id IS NULL;

-- Deduplicate audio_play_history per (user_id, global_article_id) before rewriting item_id
DELETE FROM audio_play_history
WHERE id IN (
    SELECT id FROM (
        SELECT id,
               ROW_NUMBER() OVER (
                   PARTITION BY user_id, global_article_id
                   ORDER BY played_at DESC, played_seconds DESC, id DESC
               ) as rn
        FROM audio_play_history
        WHERE item_type = 'article'
          AND global_article_id IS NOT NULL
    ) sub
    WHERE sub.rn > 1
);

-- Migrate old article item_id to global_article_id
UPDATE audio_play_history
SET item_id = global_article_id
WHERE item_type = 'article'
  AND global_article_id IS NOT NULL
  AND item_id != global_article_id;

CREATE INDEX IF NOT EXISTS idx_audio_history_global ON audio_play_history(global_article_id);
