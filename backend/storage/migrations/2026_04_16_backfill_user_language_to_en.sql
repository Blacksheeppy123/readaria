-- =============================================
-- Migration: Backfill user preferred_language to English
-- Date: 2026-04-16
-- Description: Update existing users whose preferred_language is 'zh' to 'en'
--              to align with the new product default.
-- =============================================

UPDATE users SET preferred_language = 'en' WHERE preferred_language = 'zh';
