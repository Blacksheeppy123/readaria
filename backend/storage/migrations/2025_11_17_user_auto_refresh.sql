-- Week 5: Add auto_refresh_enabled to users for scheduler control
-- Migration: 2025_11_17_user_auto_refresh.sql
-- Purpose: Allow users to opt-in/out of automatic scheduled feed refreshing

BEGIN;

-- Add auto_refresh_enabled field to users (default TRUE for opt-in)
ALTER TABLE users
ADD COLUMN IF NOT EXISTS auto_refresh_enabled BOOLEAN DEFAULT TRUE NOT NULL;

-- Add index for scheduler queries (filter by enabled users)
CREATE INDEX IF NOT EXISTS idx_users_auto_refresh ON users(auto_refresh_enabled) WHERE auto_refresh_enabled = TRUE;

-- Add comment for documentation
COMMENT ON COLUMN users.auto_refresh_enabled IS 'Controls whether user feeds are included in scheduled automatic refreshes. TRUE = user feeds refreshed hourly, FALSE = manual only.';

-- Backfill existing users to TRUE (opt-in by default)
UPDATE users SET auto_refresh_enabled = TRUE WHERE auto_refresh_enabled IS NULL;

COMMIT;
