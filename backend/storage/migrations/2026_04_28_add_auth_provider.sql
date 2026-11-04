-- 2026-04-28: Add auth_provider to users table for OAuth vs password registration tracking

BEGIN;

-- Add auth_provider column
ALTER TABLE users
ADD COLUMN IF NOT EXISTS auth_provider VARCHAR(20) DEFAULT 'password';

-- Backfill: users with random-looking password_hash (64+ chars, no bcrypt prefix) created via OAuth
-- OAuth users get random secrets.token_urlsafe(32) hashed, which produces long hashes
-- Password users typically have bcrypt hashes starting with $2b$
UPDATE users
SET auth_provider = 'google'
WHERE auth_provider = 'password'
  AND password_hash IS NOT NULL
  AND LENGTH(password_hash) > 60
  AND password_hash NOT LIKE '$2b$%';

COMMIT;
