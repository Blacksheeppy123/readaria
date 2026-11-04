-- 2026-05-06: Add ON DELETE CASCADE FK on user_id for user_reading_history & user_saved_articles
-- Background: these two tables were created (2025-11-02) without FK on user_id, so deleting
-- a user left orphan rows behind. Adding the constraint prevents future orphans.
-- Pre-condition: orphan rows already cleaned up on 2026-05-06 (no rows reference missing users).

BEGIN;

ALTER TABLE user_reading_history
    DROP CONSTRAINT IF EXISTS user_reading_history_user_id_fkey;
ALTER TABLE user_reading_history
    ADD CONSTRAINT user_reading_history_user_id_fkey
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;

ALTER TABLE user_saved_articles
    DROP CONSTRAINT IF EXISTS user_saved_articles_user_id_fkey;
ALTER TABLE user_saved_articles
    ADD CONSTRAINT user_saved_articles_user_id_fkey
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;

COMMIT;
