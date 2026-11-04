-- Migration: Add share_token to podcasts table
-- Date: 2026-06-01
-- Purpose: Support opt-in podcast sharing with opaque tokens

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'podcasts' AND column_name = 'share_token'
    ) THEN
        ALTER TABLE podcasts ADD COLUMN share_token VARCHAR(32) UNIQUE;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_indexes
        WHERE indexname = 'idx_podcasts_share_token'
    ) THEN
        CREATE INDEX idx_podcasts_share_token ON podcasts(share_token) WHERE share_token IS NOT NULL;
    END IF;
END $$;
