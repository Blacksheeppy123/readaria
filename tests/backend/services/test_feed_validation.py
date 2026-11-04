"""
Feed Validation Service 单元测试
"""
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta

from backend.services.feed_validation import (
    evaluate_single_feed,
    validate_candidate_feeds,
    MIN_ARTICLE_COUNT,
    MIN_AVG_CONTENT_LENGTH,
    MAX_HTML_RATIO,
    RECENCY_DAYS,
)


class MockContentItem:
    def __init__(self, value):
        self.value = value


class MockEntry:
    def __init__(self, title, link, content, summary=None, published_parsed=None):
        self.title = title
        self.link = link
        self.content = [MockContentItem(content)] if content else []
        self.summary = summary or ''
        self.published_parsed = published_parsed


def build_published_parsed(days_ago=0):
    dt = datetime.now() - timedelta(days=days_ago)
    return dt.timetuple()


class TestEvaluateSingleFeed:
    """测试 evaluate_single_feed"""

    @patch('backend.services.feed_validation.feedparser.parse')
    def test_valid_feed_passes(self, mock_parse):
        mock_parse.return_value = MagicMock(entries=[
            MockEntry(
                'Article 1', 'https://example.com/1',
                '<p>' + 'A' * 400 + '</p>',
                published_parsed=build_published_parsed(1)
            ),
            MockEntry(
                'Article 2', 'https://example.com/2',
                '<p>' + 'B' * 400 + '</p>',
                published_parsed=build_published_parsed(2)
            ),
            MockEntry(
                'Article 3', 'https://example.com/3',
                '<p>' + 'C' * 400 + '</p>',
                published_parsed=build_published_parsed(3)
            ),
        ])

        result = evaluate_single_feed('https://example.com/rss')

        assert result['is_valid'] is True
        assert result['article_count'] == 3
        assert result['avg_content_length'] >= MIN_AVG_CONTENT_LENGTH
        assert result['metadata']['recent_count'] >= 1

    @patch('backend.services.feed_validation.feedparser.parse')
    def test_invalid_feed_too_few_articles(self, mock_parse):
        mock_parse.return_value = MagicMock(entries=[
            MockEntry('A1', 'https://example.com/1', 'Short', published_parsed=build_published_parsed(1)),
        ])

        result = evaluate_single_feed('https://example.com/rss')

        assert result['is_valid'] is False
        assert result['metadata']['reason'] == '文章数量不足'

    @patch('backend.services.feed_validation.feedparser.parse')
    def test_invalid_feed_content_too_short(self, mock_parse):
        mock_parse.return_value = MagicMock(entries=[
            MockEntry('A1', 'https://example.com/1', 'Short', published_parsed=build_published_parsed(1)),
            MockEntry('A2', 'https://example.com/2', 'Tiny', published_parsed=build_published_parsed(2)),
            MockEntry('A3', 'https://example.com/3', 'Mini', published_parsed=build_published_parsed(3)),
        ])

        result = evaluate_single_feed('https://example.com/rss')

        assert result['is_valid'] is False
        assert result['metadata']['reason'] == '内容长度不足'

    @patch('backend.services.feed_validation.feedparser.parse')
    def test_invalid_feed_not_recent(self, mock_parse):
        mock_parse.return_value = MagicMock(entries=[
            MockEntry(
                'A1', 'https://example.com/1',
                '<p>' + 'A' * 400 + '</p>',
                published_parsed=build_published_parsed(RECENCY_DAYS + 1)
            ),
            MockEntry(
                'A2', 'https://example.com/2',
                '<p>' + 'B' * 400 + '</p>',
                published_parsed=build_published_parsed(RECENCY_DAYS + 2)
            ),
            MockEntry(
                'A3', 'https://example.com/3',
                '<p>' + 'C' * 400 + '</p>',
                published_parsed=build_published_parsed(RECENCY_DAYS + 3)
            ),
        ])

        result = evaluate_single_feed('https://example.com/rss')

        assert result['is_valid'] is False
        assert result['metadata']['reason'] == '近期无更新'

    @patch('backend.services.feed_validation.feedparser.parse')
    def test_invalid_feed_html_heavy(self, mock_parse):
        # HTML 占比高，但 plain text 仍超过最小长度阈值
        html = (
            '<div><script>ad</script><style>.css{}</style>'
            + '<span class="x">' * 500 + '</span>' * 500
            + '<p>' + 'A' * 350 + '</p></div>'
        )
        mock_parse.return_value = MagicMock(entries=[
            MockEntry('A1', 'https://example.com/1', html, published_parsed=build_published_parsed(1)),
            MockEntry('A2', 'https://example.com/2', html, published_parsed=build_published_parsed(1)),
            MockEntry('A3', 'https://example.com/3', html, published_parsed=build_published_parsed(1)),
        ])

        result = evaluate_single_feed('https://example.com/rss')

        assert result['is_valid'] is False
        assert result['metadata']['reason'] == 'HTML/广告占比过高'

    @patch('backend.services.feed_validation.feedparser.parse')
    def test_parse_exception_returns_invalid(self, mock_parse):
        mock_parse.side_effect = Exception('Network error')

        result = evaluate_single_feed('https://example.com/rss')

        assert result['is_valid'] is False
        assert '抓取异常' in result['metadata']['reason']


class TestValidateCandidateFeeds:
    """测试 validate_candidate_feeds 批量任务"""

    @patch('backend.services.feed_validation.feedparser.parse')
    def test_batch_validation_updates_all_candidates(self, mock_parse):
        mock_parse.return_value = MagicMock(entries=[
            MockEntry(
                'A1', 'https://example.com/1',
                '<p>' + 'A' * 400 + '</p>',
                published_parsed=build_published_parsed(1)
            ),
            MockEntry(
                'A2', 'https://example.com/2',
                '<p>' + 'B' * 400 + '</p>',
                published_parsed=build_published_parsed(2)
            ),
            MockEntry(
                'A3', 'https://example.com/3',
                '<p>' + 'C' * 400 + '</p>',
                published_parsed=build_published_parsed(3)
            ),
        ])

        db_manager = MagicMock()
        cursor = MagicMock()
        cursor.fetchall.return_value = [
            {'feed_url': 'https://a.com/rss', 'feed_name': 'A', 'language': 'zh'},
            {'feed_url': 'https://b.com/rss', 'feed_name': 'B', 'language': 'en'},
        ]
        db_manager.pg_conn.cursor.return_value.__enter__.return_value = cursor

        validate_candidate_feeds(db_manager)

        # 两次 SELECT 候选 + 两次 UPDATE
        assert cursor.execute.call_count == 3  # 1 select + 2 updates
        db_manager.pg_conn.commit.assert_called()

    def test_batch_validation_rollback_on_error(self):
        db_manager = MagicMock()
        cursor = MagicMock()
        cursor.fetchall.side_effect = Exception('DB error')
        db_manager.pg_conn.cursor.return_value.__enter__.return_value = cursor

        validate_candidate_feeds(db_manager)

        db_manager.pg_conn.rollback.assert_called_once()
