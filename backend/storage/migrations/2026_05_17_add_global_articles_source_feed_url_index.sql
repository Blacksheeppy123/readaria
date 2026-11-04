-- =============================================
-- Migration: Add source feed URL index for starter pack activation
-- Date: 2026-05-17
-- Description: Speed up global_articles lookups by feed URL during onboarding starter pack linking
-- =============================================

CREATE INDEX IF NOT EXISTS idx_global_articles_source_feed_url
    ON global_articles(source_feed_url);
