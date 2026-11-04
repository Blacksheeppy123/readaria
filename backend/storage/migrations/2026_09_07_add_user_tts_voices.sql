-- 用户 TTS 音色偏好（语音选择功能，2026-09-07）
-- NULL = 系统默认音色（中文 Xiaoxiao / 英文 Tiana），存量用户零感知
ALTER TABLE users ADD COLUMN IF NOT EXISTS tts_voice_zh VARCHAR(100) DEFAULT NULL;
ALTER TABLE users ADD COLUMN IF NOT EXISTS tts_voice_en VARCHAR(100) DEFAULT NULL;
