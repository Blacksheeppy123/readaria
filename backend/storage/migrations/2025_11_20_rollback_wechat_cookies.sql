-- Week 5 Cleanup: Remove WeChat cookie management
-- Migration: 2025_11_20_rollback_wechat_cookies.sql
-- Purpose: Remove wechat_cookie_profiles table as CookieCloud solution is adopted
-- Reason: CookieCloud provides direct browser→RSSHub sync, making Jasmine's cookie management redundant

BEGIN;

-- Drop indexes first
DROP INDEX IF EXISTS idx_wechat_cookies_user;
DROP INDEX IF EXISTS idx_wechat_cookies_scope;
DROP INDEX IF EXISTS idx_wechat_cookies_status;

-- Drop table
DROP TABLE IF EXISTS wechat_cookie_profiles;

-- Log cleanup
COMMENT ON SCHEMA public IS 'WeChat cookie management removed (2025-11-20). Migrated to RSSHub-CookieCloud solution.';

COMMIT;
