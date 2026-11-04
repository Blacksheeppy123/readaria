-- Example backfill script for migrating legacy user_id values to UUIDs.
-- Fill legacy_user_id_map with correct mappings before running updates.
-- Run this BEFORE rerunning 2025_10_27_alignment.sql to allow column swap.

BEGIN;

-- 0) Mapping table: old string IDs -> users.id (UUID)
CREATE TABLE IF NOT EXISTS legacy_user_id_map (
  old_user_id VARCHAR(128) PRIMARY KEY,
  new_user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE
);

-- INSERT INTO legacy_user_id_map(old_user_id, new_user_id) VALUES
--   ('test_user_001', '00000000-0000-0000-0000-000000000001');
-- Add your rows above, then run the updates below.

-- 1) user_feeds backfill
DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name='user_feeds' AND column_name='user_id_uuid'
  ) THEN
    UPDATE user_feeds uf
    SET user_id_uuid = m.new_user_id
    FROM legacy_user_id_map m
    WHERE uf.user_id_uuid IS NULL
      AND uf.user_id = m.old_user_id;
  END IF;
END $$;

-- 2) user_reading_history backfill (if table exists)
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name='user_reading_history')
     AND EXISTS (
       SELECT 1 FROM information_schema.columns
       WHERE table_name='user_reading_history' AND column_name='user_id_uuid'
     ) THEN
    UPDATE user_reading_history urh
    SET user_id_uuid = m.new_user_id
    FROM legacy_user_id_map m
    WHERE urh.user_id_uuid IS NULL
      AND urh.user_id = m.old_user_id;
  END IF;
END $$;

-- 3) user_saved_articles backfill (if legacy table exists)
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name='user_saved_articles')
     AND EXISTS (
       SELECT 1 FROM information_schema.columns
       WHERE table_name='user_saved_articles' AND column_name='user_id_uuid'
     ) THEN
    UPDATE user_saved_articles usa
    SET user_id_uuid = m.new_user_id
    FROM legacy_user_id_map m
    WHERE usa.user_id_uuid IS NULL
      AND usa.user_id = m.old_user_id;
  END IF;
END $$;

COMMIT;

-- After running this backfill, rerun 2025_10_27_alignment.sql so it can
-- safely swap columns and enforce foreign keys.

