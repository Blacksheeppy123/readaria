-- Week 3: Add authentication fields to users table
-- Migration: 2025_10_31_add_user_auth_fields.sql

BEGIN;

-- Add password_hash column for authentication
ALTER TABLE users
ADD COLUMN IF NOT EXISTS password_hash VARCHAR(255);

-- Add is_active flag (default true)
ALTER TABLE users
ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT true;

-- Add is_superuser flag (default false)
ALTER TABLE users
ADD COLUMN IF NOT EXISTS is_superuser BOOLEAN DEFAULT false;

-- Add avatar_url for profile pictures
ALTER TABLE users
ADD COLUMN IF NOT EXISTS avatar_url TEXT;

-- Make email NOT NULL if it isn't already
DO $$
BEGIN
  ALTER TABLE users ALTER COLUMN email SET NOT NULL;
EXCEPTION
  WHEN others THEN
    RAISE NOTICE 'email column already NOT NULL or other constraint exists';
END $$;

-- Update existing test-user with a default password hash
-- Password: "test123" hashed with bcrypt
-- This allows immediate testing after migration
UPDATE users
SET
  password_hash = '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY5eDWpbdJu.K3e',
  is_active = true,
  is_superuser = true
WHERE id::text = 'test-user' AND password_hash IS NULL;

-- Create user_sessions table if it doesn't exist (for JWT token management)
CREATE TABLE IF NOT EXISTS user_sessions (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash VARCHAR(255) NOT NULL,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    last_accessed TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Add index for token lookup
CREATE INDEX IF NOT EXISTS idx_user_sessions_token ON user_sessions(token_hash);
CREATE INDEX IF NOT EXISTS idx_user_sessions_expires ON user_sessions(expires_at);
CREATE INDEX IF NOT EXISTS idx_user_sessions_user_id ON user_sessions(user_id);

COMMIT;

-- Migration completed
-- Default test user credentials:
--   username: test-user
--   password: test123
