"""
Feed 质量验证服务
用于新用户 Starter Pack 的内容预筛选
"""
from datetime import datetime, timedelta
from typing import List, Dict, Any
import json
import logging
import time

import feedparser
from bs4 import BeautifulSoup
from psycopg2.extras import RealDictCursor

logger = logging.getLogger(__name__)

MIN_ARTICLE_COUNT = 3
MIN_AVG_CONTENT_LENGTH = 300
MAX_HTML_RATIO = 0.7
RECENCY_DAYS = 7


def validate_candidate_feeds(db_manager):
    """
    定时任务：验证候选 feed 池的内容质量。
    建议每 4 小时运行一次。
    """
    try:
        with db_manager.pg_conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT feed_url, feed_name, language FROM feed_validation")
            candidates = cur.fetchall()

        for candidate in candidates:
            try:
                result = evaluate_single_feed(candidate['feed_url'])
                with db_manager.pg_conn.cursor() as cur:
                    cur.execute(
                        """
                        UPDATE feed_validation
                        SET is_valid = %s,
                            article_count = %s,
                            avg_content_length = %s,
                            last_article_at = %s,
                            last_validated_at = CURRENT_TIMESTAMP,
                            validation_metadata = %s
                        WHERE feed_url = %s
                        """,
                        (
                            result['is_valid'],
                            result['article_count'],
                            result['avg_content_length'],
                            result['last_article_at'],
                            json.dumps(result['metadata'], ensure_ascii=False),
                            candidate['feed_url']
                        )
                    )
                    db_manager.pg_conn.commit()
            except Exception as e:
                db_manager.pg_conn.rollback()
                logger.error(f"验证 feed 失败: {candidate['feed_url']}, error={e}")
                continue

        logger.info(f"完成 feed 验证: 共 {len(candidates)} 个候选源")

    except Exception as e:
        db_manager.pg_conn.rollback()
        logger.error(f"批量验证 feed 失败: {e}")


def evaluate_single_feed(feed_url: str) -> Dict[str, Any]:
    """
    抓取并评估单个 feed 的内容质量。

    Args:
        feed_url: Feed URL

    Returns:
        包含 is_valid, article_count, avg_content_length, last_article_at, metadata 的字典
    """
    try:
        parsed = feedparser.parse(feed_url)
        entries = parsed.entries[:20]  # 最多评估前 20 条

        if len(entries) < MIN_ARTICLE_COUNT:
            return _invalid_result("文章数量不足")

        content_lengths = []
        recent_count = 0
        last_article_at = None
        html_heavy_count = 0

        for entry in entries:
            content = _extract_content(entry)
            plain_text = BeautifulSoup(content, "html.parser").get_text(separator=' ', strip=True)
            content_lengths.append(len(plain_text))

            # HTML 占比检查
            if len(content) > 0:
                text_ratio = len(plain_text) / len(content)
                if text_ratio < (1 - MAX_HTML_RATIO):
                    html_heavy_count += 1

            # 时间检查
            published = _parse_published_at(entry)
            if published:
                if not last_article_at or published > last_article_at:
                    last_article_at = published
                if published > datetime.now(published.tzinfo) - timedelta(days=RECENCY_DAYS):
                    recent_count += 1

        avg_length = sum(content_lengths) // max(len(content_lengths), 1)
        html_ratio = html_heavy_count / max(len(entries), 1)

        is_valid = (
            len(entries) >= MIN_ARTICLE_COUNT and
            avg_length >= MIN_AVG_CONTENT_LENGTH and
            recent_count >= 1 and
            html_ratio <= MAX_HTML_RATIO
        )

        return {
            'is_valid': is_valid,
            'article_count': len(entries),
            'avg_content_length': avg_length,
            'last_article_at': last_article_at,
            'metadata': {
                'recent_count': recent_count,
                'html_heavy_ratio': html_ratio,
                'reason': None if is_valid else _reason_text(avg_length, recent_count, html_ratio)
            }
        }

    except Exception as e:
        logger.error(f"评估 feed 异常: {feed_url}, error={e}")
        return _invalid_result(f"抓取异常: {str(e)}")


def _extract_content(entry: Any) -> str:
    """从 feed entry 中提取最完整的内容"""
    if hasattr(entry, 'content') and entry.content:
        return entry.content[0].value
    return getattr(entry, 'summary', '') or getattr(entry, 'description', '') or ''


def _parse_published_at(entry: Any) -> datetime:
    """解析 entry 的发布时间"""
    published_parsed = getattr(entry, 'published_parsed', None)
    if published_parsed:
        try:
            return datetime.fromtimestamp(time.mktime(published_parsed))
        except (ValueError, OverflowError):
            return None
    return None


def _invalid_result(reason: str) -> Dict[str, Any]:
    return {
        'is_valid': False,
        'article_count': 0,
        'avg_content_length': 0,
        'last_article_at': None,
        'metadata': {'reason': reason}
    }


def _reason_text(avg_length: int, recent_count: int, html_ratio: float) -> str:
    if avg_length < MIN_AVG_CONTENT_LENGTH:
        return "内容长度不足"
    if recent_count < 1:
        return "近期无更新"
    if html_ratio > MAX_HTML_RATIO:
        return "HTML/广告占比过高"
    return "未知"
