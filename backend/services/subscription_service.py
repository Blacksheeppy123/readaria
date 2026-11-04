"""
Self-hosted usage accounting and unlimited feature access.

The name is kept for compatibility with existing callers. It refers to feature
usage only; RSS feed subscriptions are managed elsewhere.
"""
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)


class SubscriptionService:
    """Provide unlimited self-hosted quotas and optional usage statistics."""

    def __init__(self, db_manager):
        self.db = db_manager

    def get_effective_plan(self, user_id: str) -> Dict[str, Any]:
        """Return the single self-hosted plan; -1 means unlimited."""
        return {
            'plan_id': 'selfhost',
            'plan_name': 'Self-hosted',
            'status': 'active',
            'tts_daily_limit': -1,
            'podcast_daily_limit': -1,
            'ai_summary_daily_limit': -1,
            'trial_end': None,
            'current_period_end': None,
        }

    # ================== 用量统计（不参与功能门控） ==================

    def get_usage_today(self, user_id: str) -> Dict[str, int]:
        """获取用户今日用量。"""
        try:
            conn = self.db.pg_conn
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT tts_count, tts_characters, podcast_count, ai_summary_count
                    FROM user_usage_daily
                    WHERE user_id = %s AND usage_date = CURRENT_DATE
                    """,
                    (user_id,)
                )
                row = cur.fetchone()
                if row:
                    return {
                        'tts_count': row[0],
                        'tts_characters': row[1],
                        'podcast_count': row[2],
                        'ai_summary_count': row[3],
                    }
                return {'tts_count': 0, 'tts_characters': 0, 'podcast_count': 0, 'ai_summary_count': 0}
        except Exception as e:
            logger.error(f"获取今日用量失败: user_id={user_id}, error={e}")
            return {'tts_count': 0, 'tts_characters': 0, 'podcast_count': 0, 'ai_summary_count': 0}

    def get_usage_week(self, user_id: str) -> Dict[str, int]:
        """获取用户本周播客生成次数。"""
        try:
            conn = self.db.pg_conn
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT COALESCE(SUM(podcast_count), 0)
                    FROM user_usage_daily
                    WHERE user_id = %s AND usage_date >= date_trunc('week', CURRENT_DATE)
                    """,
                    (user_id,)
                )
                row = cur.fetchone()
                return {'podcast_count_week': row[0] if row else 0}
        except Exception as e:
            logger.error(f"获取本周用量失败: user_id={user_id}, error={e}")
            return {'podcast_count_week': 0}

    def record_tts_usage(self, user_id: str, characters: int = 0) -> bool:
        """记录一次 TTS 使用。"""
        try:
            conn = self.db.pg_conn
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO user_usage_daily (user_id, usage_date, tts_count, tts_characters)
                    VALUES (%s, CURRENT_DATE, 1, %s)
                    ON CONFLICT (user_id, usage_date) DO UPDATE SET
                        tts_count = user_usage_daily.tts_count + 1,
                        tts_characters = user_usage_daily.tts_characters + EXCLUDED.tts_characters,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (user_id, characters)
                )
                conn.commit()
                return True
        except Exception as e:
            conn.rollback()
            logger.error(f"记录 TTS 用量失败: user_id={user_id}, error={e}")
            return False

    def record_podcast_usage(self, user_id: str) -> bool:
        """记录一次播客生成。"""
        try:
            conn = self.db.pg_conn
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO user_usage_daily (user_id, usage_date, podcast_count)
                    VALUES (%s, CURRENT_DATE, 1)
                    ON CONFLICT (user_id, usage_date) DO UPDATE SET
                        podcast_count = user_usage_daily.podcast_count + 1,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (user_id,)
                )
                conn.commit()
                return True
        except Exception as e:
            conn.rollback()
            logger.error(f"记录播客用量失败: user_id={user_id}, error={e}")
            return False

    def record_ai_summary_usage(self, user_id: str) -> bool:
        """记录一次 AI 摘要使用。"""
        try:
            conn = self.db.pg_conn
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO user_usage_daily (user_id, usage_date, ai_summary_count)
                    VALUES (%s, CURRENT_DATE, 1)
                    ON CONFLICT (user_id, usage_date) DO UPDATE SET
                        ai_summary_count = user_usage_daily.ai_summary_count + 1,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (user_id,)
                )
                conn.commit()
                return True
        except Exception as e:
            conn.rollback()
            logger.error(f"记录 AI 摘要用量失败: user_id={user_id}, error={e}")
            return False

    # ================== 无限配额（保持既有调用协议） ==================

    @staticmethod
    def _unlimited_quota() -> Dict[str, Any]:
        return {'allowed': True, 'used': 0, 'limit': -1, 'plan': 'selfhost'}

    def check_tts_quota(self, user_id: str) -> Dict[str, Any]:
        """自托管版不限制云端 TTS 次数。"""
        return self._unlimited_quota()

    def check_ai_summary_quota(self, user_id: str) -> Dict[str, Any]:
        """自托管版不限制 AI 摘要次数。"""
        return self._unlimited_quota()

    def check_podcast_quota(self, user_id: str) -> Dict[str, Any]:
        """自托管版不限制播客生成次数。"""
        return self._unlimited_quota()

    def get_subscription_summary(self, user_id: str) -> Dict[str, Any]:
        """Return the backwards-compatible self-hosted plan and usage summary."""
        plan = self.get_effective_plan(user_id)
        usage_today = self.get_usage_today(user_id)
        return {
            'plan': plan['plan_id'],
            'plan_name': plan['plan_name'],
            'status': plan['status'],
            'trial_end': None,
            'trial_days_left': None,
            'current_period_end': None,
            'tts_daily_limit': -1,
            'tts_used_today': usage_today['tts_count'],
            'podcast_daily_limit': -1,
            'podcast_used_today': usage_today['podcast_count'],
            'ai_summary_daily_limit': -1,
            'ai_summary_used_today': usage_today['ai_summary_count'],
        }
