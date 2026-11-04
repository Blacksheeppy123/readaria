-- Jasmine DB alignment migration (draft)
-- Goal: align legacy tables to current UUID-based schema and fix indexes
-- NOTE: Review on a staging DB before applying to production.

BEGIN;

-- 1) Articles: ensure published_at and index naming
DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name='articles' AND column_name='published'
  ) AND NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name='articles' AND column_name='published_at'
  ) THEN
    ALTER TABLE articles RENAME COLUMN published TO published_at;
  END IF;
END $$;

-- Drop legacy index if it referenced a removed/renamed column
DROP INDEX IF EXISTS idx_articles_source;

-- Ensure a descending index on published_at exists
DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name='articles' AND column_name='published_at'
  ) THEN
    CREATE INDEX IF NOT EXISTS idx_articles_published_at
      ON articles(published_at DESC);
  END IF;
END $$;

-- 2) Ensure user_id columns are UUID and FK to users(id)
-- This section is conservative: adds a new column, attempts a safe cast, then swaps.
-- If your existing user_id values are not UUIDs, fill mapping in temp table before running the swap.

-- user_feeds.user_id -> UUID
DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name='user_feeds' AND column_name='user_id'
          AND data_type <> 'uuid'
  ) THEN
    ALTER TABLE user_feeds ADD COLUMN IF NOT EXISTS user_id_uuid UUID;
    -- Attempt direct cast when possible
    UPDATE user_feeds SET user_id_uuid = NULLIF(user_id, '')::uuid
    WHERE user_id_uuid IS NULL
      AND user_id ~* '^[0-9a-f-]{36}$';

    -- If some rows remain NULL, populate user_id_uuid via a mapping before proceeding.
    -- RAISE NOTICE for operator action
    IF EXISTS (SELECT 1 FROM user_feeds WHERE user_id_uuid IS NULL) THEN
      RAISE NOTICE 'user_feeds.user_id_uuid contains NULLs; please backfill before column swap';
    ELSE
      ALTER TABLE user_feeds DROP COLUMN user_id;
      ALTER TABLE user_feeds RENAME COLUMN user_id_uuid TO user_id;
    END IF;

    -- Add FK if not present
    BEGIN
      ALTER TABLE user_feeds
        ADD CONSTRAINT fk_user_feeds_user
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;
    EXCEPTION WHEN duplicate_object THEN
      -- constraint already exists
      NULL;
    END;
  END IF;
END $$;

-- user_reading_history.user_id -> UUID (if table exists)
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name='user_reading_history') THEN
    IF EXISTS (
      SELECT 1 FROM information_schema.columns
      WHERE table_name='user_reading_history' AND column_name='user_id' AND data_type <> 'uuid'
    ) THEN
      ALTER TABLE user_reading_history ADD COLUMN IF NOT EXISTS user_id_uuid UUID;
      UPDATE user_reading_history SET user_id_uuid = NULLIF(user_id, '')::uuid
      WHERE user_id_uuid IS NULL AND user_id ~* '^[0-9a-f-]{36}$';

      IF EXISTS (SELECT 1 FROM user_reading_history WHERE user_id_uuid IS NULL) THEN
        RAISE NOTICE 'user_reading_history.user_id_uuid contains NULLs; please backfill before column swap';
      ELSE
        ALTER TABLE user_reading_history DROP COLUMN user_id;
        ALTER TABLE user_reading_history RENAME COLUMN user_id_uuid TO user_id;
      END IF;

      BEGIN
        ALTER TABLE user_reading_history
          ADD CONSTRAINT fk_reading_user
          FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;
      EXCEPTION WHEN duplicate_object THEN NULL;
      END;
    END IF;
  END IF;
END $$;

-- user_saved_articles -> if legacy table exists (new schema uses user_bookmarks)
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name='user_saved_articles') THEN
    IF EXISTS (
      SELECT 1 FROM information_schema.columns
      WHERE table_name='user_saved_articles' AND column_name='user_id' AND data_type <> 'uuid'
    ) THEN
      ALTER TABLE user_saved_articles ADD COLUMN IF NOT EXISTS user_id_uuid UUID;
      UPDATE user_saved_articles SET user_id_uuid = NULLIF(user_id, '')::uuid
      WHERE user_id_uuid IS NULL AND user_id ~* '^[0-9a-f-]{36}$';

      IF EXISTS (SELECT 1 FROM user_saved_articles WHERE user_id_uuid IS NULL) THEN
        RAISE NOTICE 'user_saved_articles.user_id_uuid contains NULLs; please backfill before column swap';
      ELSE
        ALTER TABLE user_saved_articles DROP COLUMN user_id;
        ALTER TABLE user_saved_articles RENAME COLUMN user_id_uuid TO user_id;
      END IF;

      BEGIN
        ALTER TABLE user_saved_articles
          ADD CONSTRAINT fk_saved_user
          FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;
      EXCEPTION WHEN duplicate_object THEN NULL;
      END;
    END IF;
  END IF;
END $$;

COMMIT;

-- Post-steps (manual, recommended before production run):
-- 1) Verify no NULL remains in temporary UUID columns during migration.
-- 2) Validate indexes and query plans for articles list/search after changes.
-- 3) Backup before running on production data.

