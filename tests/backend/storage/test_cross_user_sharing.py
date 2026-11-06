"""
Cross-User Content Sharing 数据库层单元测试
覆盖 dual-write、feed 订阅链接、文章列表查询、starter pack
"""
import pytest
from unittest.mock import MagicMock, patch, call
from datetime import datetime

from backend.storage.database import DatabaseManager
from backend.utils.url import normalize_url, generate_content_hash
from backend.config.onboarding_starter_pack import STARTER_PACK_FEEDS


@pytest.fixture
def mock_db_manager():
    db = MagicMock(spec=DatabaseManager)
    db.pg_conn = MagicMock()
    db.logger = MagicMock()
    db._user_feeds_cache = {}
    db._user_feeds_cache_ttl = 300
    return db


class TestStoreArticleDualWrite:
    """测试 store_article 双写逻辑"""

    @patch.object(DatabaseManager, '_ensure_source_type', return_value='rss')
    def test_store_article_inserts_global_and_legacy(self, mock_ensure_source, mock_db_manager):
        """验证同时写入 global_articles、articles 和 user_article_refs"""
        # 直接设置实例方法返回值（MagicMock 实例上 patch.object 无效）
        mock_db_manager._get_user_id_by_feed_id.return_value = 'user_123'

        # 模拟 cursor：四次 execute 分别返回旧 content_hash、global_id、legacy_id、None
        cursor = MagicMock()
        cursor.fetchone.side_effect = [
            ['old_hash'],  # 查询旧的 content_hash
            [100],         # global_articles RETURNING id
            [200, True]    # articles RETURNING id, is_new
        ]

        mock_db_manager.pg_conn.cursor.return_value.__enter__.return_value = cursor

        article = {
            'title': 'Test Article',
            'link': 'https://example.com/post/1?utm_source=test',
            'content': '<p>This is a test article.</p>',
            'author': 'Author',
            'published': datetime(2026, 4, 14, 10, 0, 0),
            'source': 'https://example.com/rss',
            'feed_id': 1,
            'language': 'zh',
        }

        DatabaseManager.store_article(mock_db_manager, article)

        # 验证 execute 调用顺序：旧 content_hash 查询 -> global_articles -> articles -> user_article_refs
        calls = cursor.execute.call_args_list
        assert 'SELECT content_hash FROM global_articles' in calls[0][0][0]

        assert 'global_articles' in calls[1][0][0]
        norm_url = normalize_url(article['link'])
        expected_hash = generate_content_hash(article['content'], norm_url)
        assert calls[1][0][1][0] == norm_url
        assert calls[1][0][1][1] == expected_hash

        # 验证 articles INSERT
        assert 'articles' in calls[2][0][0]

        # 验证 user_article_refs INSERT（content_hash 变化，应更新 fetched_at）
        assert 'user_article_refs' in calls[3][0][0]
        assert calls[3][0][1] == ('user_123', 100, 200, 1, article['published'])

        mock_db_manager.pg_conn.commit.assert_called_once()

    @patch.object(DatabaseManager, '_ensure_source_type', return_value='rss')
    def test_store_article_same_hash_preserves_fetched_at(self, mock_ensure_source, mock_db_manager):
        """相同 content_hash 时，user_article_refs ON CONFLICT 不更新 fetched_at"""
        mock_db_manager._get_user_id_by_feed_id.return_value = 'user_123'

        article = {
            'title': 'Test Article',
            'link': 'https://example.com/post/1',
            'content': '<p>This is a test article.</p>',
            'author': 'Author',
            'published': datetime(2026, 4, 14, 10, 0, 0),
            'source': 'https://example.com/rss',
            'feed_id': 1,
            'language': 'zh',
        }
        norm_url = normalize_url(article['link'])
        content_hash = generate_content_hash(article['content'], norm_url)

        # 旧 content_hash 与新内容相同 → 不应刷新 fetched_at
        cursor = MagicMock()
        cursor.fetchone.side_effect = [
            [content_hash],  # 查询旧的 content_hash（与新内容相同）
            [100],           # global_articles RETURNING id
            [200, False]     # articles RETURNING id, is_new
        ]
        mock_db_manager.pg_conn.cursor.return_value.__enter__.return_value = cursor

        DatabaseManager.store_article(mock_db_manager, article)

        calls = cursor.execute.call_args_list
        # 验证 user_article_refs INSERT（content_hash 未变化，不应更新 fetched_at）
        assert 'user_article_refs' in calls[3][0][0]
        # ON CONFLICT 子句中不应包含 fetched_at = CURRENT_TIMESTAMP
        assert 'fetched_at = CURRENT_TIMESTAMP' not in calls[3][0][0]
        # 但仍应更新 legacy_article_id
        assert 'legacy_article_id = EXCLUDED.legacy_article_id' in calls[3][0][0]

        mock_db_manager.pg_conn.commit.assert_called_once()

    @patch.object(DatabaseManager, '_ensure_source_type', return_value='rss')
    def test_store_article_new_user_existing_global_article(self, mock_ensure_source, mock_db_manager):
        """新用户首次关联已有全局文章时，fetched_at 应设为 published_at"""
        mock_db_manager._get_user_id_by_feed_id.return_value = 'user_new'

        article = {
            'title': 'Existing Article',
            'link': 'https://example.com/post/2',
            'content': '<p>Content.</p>',
            'author': 'Author',
            'published': datetime(2026, 4, 10, 8, 0, 0),
            'source': 'https://example.com/rss',
            'feed_id': 2,
            'language': 'zh',
        }
        norm_url = normalize_url(article['link'])
        content_hash = generate_content_hash(article['content'], norm_url)

        cursor = MagicMock()
        cursor.fetchone.side_effect = [
            [content_hash],  # 全局文章已存在，content_hash 相同
            [101],           # global_articles RETURNING id
            [201, True]      # articles RETURNING id, is_new
        ]
        mock_db_manager.pg_conn.cursor.return_value.__enter__.return_value = cursor

        DatabaseManager.store_article(mock_db_manager, article)

        calls = cursor.execute.call_args_list
        # 验证 user_article_refs INSERT 使用 published_at 作为 fetched_at
        assert 'user_article_refs' in calls[3][0][0]
        assert calls[3][0][1] == ('user_new', 101, 201, 2, article['published'])

        mock_db_manager.pg_conn.commit.assert_called_once()


class TestCreateUserFeedLinksGlobalArticles:
    """测试 create_user_feed_minimal + link_global_articles_to_feed 拆分后的行为

    Fix 1 (2026-05-11): create_user_feed 已拆为两个函数:
      * create_user_feed_minimal 只 INSERT user_feeds 并 commit,用于 onboarding 快速路径
      * link_global_articles_to_feed 把 global_articles → articles/user_article_refs 物化,
        可单独通过 BackgroundTasks 调度。
    保留的 create_user_feed 仅作为 OPML 等同步路径的便捷封装,这里改测拆分后的两个函数。
    """

    def test_create_user_feed_minimal_inserts_user_feed_only(self, mock_db_manager):
        mock_db_manager._ensure_source_type.return_value = 'rss'
        cursor = MagicMock()
        cursor.fetchone.return_value = [42]
        mock_db_manager.pg_conn.cursor.return_value.__enter__.return_value = cursor

        result = DatabaseManager.create_user_feed_minimal(
            mock_db_manager, 'user_123', 'Test Feed', 'https://example.com/rss'
        )

        assert result == (42, False)

        calls = cursor.execute.call_args_list
        # minimal 只发一条 INSERT INTO user_feeds
        assert len(calls) == 1
        assert 'user_feeds' in calls[0][0][0]
        mock_db_manager.pg_conn.commit.assert_called_once()

    def test_link_global_articles_to_feed_links_existing_global_articles(self, mock_db_manager):
        mock_db_manager._ensure_source_type.return_value = 'rss'
        cursor = MagicMock()
        cursor.rowcount = 1
        mock_db_manager.pg_conn.cursor.return_value.__enter__.return_value = cursor

        result = DatabaseManager.link_global_articles_to_feed(
            mock_db_manager, 'user_123', 42, 'https://example.com/rss'
        )

        assert result == 1

        calls = cursor.execute.call_args_list
        # calls[0]: INSERT INTO articles (兼容层 materialize)
        assert 'articles' in calls[0][0][0]
        assert 'global_articles' in calls[0][0][0]
        assert calls[0][0][1] == (42, 'rss', 'https://example.com/rss')

        # calls[1]: INSERT INTO user_article_refs (含 legacy_article_id)
        assert 'user_article_refs' in calls[1][0][0]
        assert calls[1][0][1] == ('user_123', 42, 42, 'https://example.com/rss')

        mock_db_manager.pg_conn.commit.assert_called_once()

    def test_link_global_articles_to_feed_no_global_articles(self, mock_db_manager):
        mock_db_manager._ensure_source_type.return_value = 'rss'
        cursor = MagicMock()
        cursor.rowcount = 0
        mock_db_manager.pg_conn.cursor.return_value.__enter__.return_value = cursor

        result = DatabaseManager.link_global_articles_to_feed(
            mock_db_manager, 'user_123', 42, 'https://example.com/rss'
        )

        assert result == 0
        # 仍然执行 materialize 和 refs 的 set-based INSERT,只是没有匹配行
        calls = cursor.execute.call_args_list
        assert 'articles' in calls[0][0][0]
        assert 'user_article_refs' in calls[1][0][0]
        mock_db_manager.pg_conn.commit.assert_called_once()

    def test_link_global_articles_to_feed_can_limit_to_recent_articles(self, mock_db_manager):
        mock_db_manager._ensure_source_type.return_value = 'rss'
        cursor = MagicMock()
        cursor.rowcount = 20
        mock_db_manager.pg_conn.cursor.return_value.__enter__.return_value = cursor

        result = DatabaseManager.link_global_articles_to_feed(
            mock_db_manager, 'user_123', 42, 'https://example.com/rss', limit=20
        )

        assert result == 20
        calls = cursor.execute.call_args_list
        assert 'ORDER BY COALESCE(ga.published_at, ga.first_seen_at)' in calls[0][0][0]
        assert 'LIMIT %s' in calls[0][0][0]
        assert calls[0][0][1] == (42, 'rss', 'https://example.com/rss', 20)
        assert calls[1][0][1] == ('user_123', 42, 42, 'https://example.com/rss', 20)

    def test_activate_starter_pack_feeds_links_recent_articles_before_returning(self, mock_db_manager):
        feeds = [
            {'feed_name': 'Feed A', 'feed_url': 'https://example.com/a.xml'},
            {'feed_name': 'Feed B', 'feed_url': 'https://example.com/b.xml'},
        ]
        mock_db_manager.create_user_feed_minimal.side_effect = [(11, False), (12, True)]
        mock_db_manager.link_global_articles_to_feed.side_effect = [3, 2]

        result = DatabaseManager.activate_starter_pack_feeds(
            mock_db_manager,
            'user_123',
            feeds,
        )

        assert result == {
            'feeds': [
                {
                    'feed_id': 11,
                    'feed_name': 'Feed A',
                    'feed_url': 'https://example.com/a.xml',
                    'is_existing': False,
                    'linked_count': 3,
                },
                {
                    'feed_id': 12,
                    'feed_name': 'Feed B',
                    'feed_url': 'https://example.com/b.xml',
                    'is_existing': True,
                    'linked_count': 2,
                },
            ],
            'created_count': 1,
            'existing_count': 1,
            'linked_count': 5,
            'initial_link_limit': 20,
            'needs_background_backfill': True,
        }
        assert result['needs_background_backfill'] is True
        mock_db_manager.create_user_feed_minimal.assert_has_calls([
            call('user_123', 'Feed A', 'https://example.com/a.xml'),
            call('user_123', 'Feed B', 'https://example.com/b.xml'),
        ])
        mock_db_manager.link_global_articles_to_feed.assert_has_calls([
            call('user_123', 11, 'https://example.com/a.xml', limit=20),
            call('user_123', 12, 'https://example.com/b.xml', limit=20),
        ])


class TestGetUserArticlesQuery:
    """测试 get_user_articles 查询逻辑"""

    def test_query_uses_user_article_refs_with_fetched_at(self, mock_db_manager):
        """使用 user_article_refs + global_articles JOIN 查询，按 uar.fetched_at 排序"""
        cursor = MagicMock()
        cursor.fetchall.side_effect = [
            [(1,)],
            [(
                200, 'Article 1', 'Summary 1', 'https://example.com/1',
                datetime(2026, 4, 14, 10, 0, 0), 'A1', 's1',
                datetime(2026, 4, 14, 10, 0, 0), 'Content 1', None, False
            )]
        ]
        cursor.description = [
            ('id',), ('title',), ('summary',), ('url',), ('published_at',),
            ('author',), ('source',), ('updated_at',), ('content',),
            ('read_at',), ('is_read',)
        ]
        mock_db_manager.pg_conn.cursor.return_value.__enter__.return_value = cursor

        result = DatabaseManager.get_user_articles(mock_db_manager, 'user_123')

        assert len(result) == 1
        assert result[0]['id'] == 200
        assert result[0]['title'] == 'Article 1'

        calls = cursor.execute.call_args_list
        # 第一次查询 user_feeds
        assert 'user_feeds' in calls[0][0][0]
        # 第二次查询应使用 user_article_refs JOIN global_articles
        assert 'global_articles' in calls[1][0][0]
        assert 'user_article_refs' in calls[1][0][0]
        # 应使用 uar.fetched_at 作为 updated_at 和排序字段
        assert 'uar.fetched_at AS updated_at' in calls[1][0][0]
        assert 'ORDER BY uar.fetched_at DESC' in calls[1][0][0]
        assert len(calls) == 2

    def test_get_user_article_by_url_prefers_language_summary_cache(self, mock_db_manager):
        """用户文章详情应优先返回语言化 article_summaries"""
        cursor = MagicMock()
        cursor.fetchone.return_value = {
            'id': 200,
            'feed_id': 1,
            'title': 'Article 1',
            'url': 'https://example.com/1',
            'content': 'Content 1',
            'summary': '中文摘要',
            'author': 'A1',
            'published_at': datetime(2026, 4, 14, 10, 0, 0),
            'entities': [],
            'source': 'https://example.com/rss',
            'updated_at': datetime(2026, 4, 14, 10, 0, 0),
        }
        mock_db_manager.pg_conn.cursor.return_value.__enter__.return_value = cursor

        result = DatabaseManager.get_user_article_by_url(
            mock_db_manager,
            'user_123',
            'https://example.com/1',
            language='zh',
        )

        assert result['summary'] == '中文摘要'
        query = cursor.execute.call_args_list[0][0][0]
        params = cursor.execute.call_args_list[0][0][1]
        # 优先精确语言匹配，未命中时回退到最近生成的内容语言摘要
        assert 'LEFT JOIN LATERAL' in query
        assert 'ORDER BY (s.language = %s) DESC, s.updated_at DESC' in query
        assert 'COALESCE(as_lang.summary, ga.summary) AS summary' in query
        assert params[0] == 'zh'

    def test_get_user_articles_stats_returns_total_and_playable(self, mock_db_manager):
        """统计查询应返回稳定总数和可播放总数，而不是当前页长度"""
        cursor = MagicMock()
        cursor.fetchall.side_effect = [
            [(1,)],
        ]
        cursor.fetchone.return_value = (40, 32)
        mock_db_manager.pg_conn.cursor.return_value.__enter__.return_value = cursor

        result = DatabaseManager.get_user_articles_stats(mock_db_manager, 'user_123')

        assert result == {'total': 40, 'playable_total': 32}

        calls = cursor.execute.call_args_list
        assert 'user_feeds' in calls[0][0][0]
        assert 'COUNT(DISTINCT ga.id) AS total' in calls[1][0][0]
        assert 'playable_total' in calls[1][0][0]
        assert 'user_article_refs' in calls[1][0][0]


class TestUpdateArticleSummary:
    """测试摘要更新不会污染共享摘要字段"""

    def test_only_updates_legacy_article_summary(self, mock_db_manager):
        cursor = MagicMock()
        mock_db_manager.pg_conn.cursor.return_value.__enter__.return_value = cursor

        DatabaseManager.update_article_summary(mock_db_manager, 100, 200, 'Localized summary')

        calls = cursor.execute.call_args_list
        assert len(calls) == 1
        assert 'UPDATE articles SET summary = %s' in calls[0][0][0]
        assert 'UPDATE global_articles SET summary = %s' not in calls[0][0][0]
        mock_db_manager.pg_conn.commit.assert_called_once()

    def test_get_user_feed_overview_stats_counts_today_new_articles(self, mock_db_manager):
        """首页概览统计今日新更新文章数"""
        cursor = MagicMock()
        cursor.fetchall.side_effect = [
            [(1,)],
        ]
        cursor.fetchone.return_value = (12,)
        mock_db_manager.pg_conn.cursor.return_value.__enter__.return_value = cursor

        result = DatabaseManager.get_user_feed_overview_stats(mock_db_manager, 'user_123')

        assert result == {'today_ready_count': 12}

        calls = cursor.execute.call_args_list
        assert 'user_feeds' in calls[0][0][0]
        assert 'COUNT(DISTINCT ga.id) AS today_ready_count' in calls[1][0][0]
        assert 'uar.fetched_at AT TIME ZONE' in calls[1][0][0]
        assert "Asia/Shanghai" in calls[1][0][0]
        assert 'article_summaries' not in calls[1][0][0]


class TestGetStarterPackFeeds:
    """测试 get_starter_pack_feeds 方法"""

    def test_returns_fixed_language_pack(self, mock_db_manager):
        result = DatabaseManager.get_starter_pack_feeds(mock_db_manager, language='zh')

        assert len(result) == len(STARTER_PACK_FEEDS['zh'])
        assert result[0]['language'] == 'zh'
        assert result[0]['feed_url'] == STARTER_PACK_FEEDS['zh'][0]['feed_url']

    def test_returns_copy_of_fixed_pack(self, mock_db_manager):
        result = DatabaseManager.get_starter_pack_feeds(mock_db_manager, language='zh')
        result.pop()

        fresh_result = DatabaseManager.get_starter_pack_feeds(mock_db_manager, language='zh')
        assert len(fresh_result) == len(STARTER_PACK_FEEDS['zh'])

    def test_english_pack_stays_compact(self, mock_db_manager):
        result = DatabaseManager.get_starter_pack_feeds(mock_db_manager, language='en')
        names = {feed['feed_name'] for feed in result}

        assert len(result) == 5
        assert names == {'The Atlantic', 'Popular Science', 'Vox', 'Axios', 'Ars Technica'}


class TestURLNormalizationAndHash:
    """测试 URL 规范化与内容哈希工具"""

    def test_normalize_url_removes_tracking_params(self):
        url = 'https://example.com/article?utm_source=email&utm_medium=social&sort=desc'
        assert normalize_url(url) == 'https://example.com/article?sort=desc'

    def test_normalize_url_sorts_query_params(self):
        url = 'https://example.com/search?z=last&a=first&m=middle'
        assert normalize_url(url) == 'https://example.com/search?a=first&m=middle&z=last'

    def test_normalize_url_removes_fragment_and_default_ports(self):
        assert normalize_url('https://example.com:443/path/') == 'https://example.com/path'
        assert normalize_url('http://example.com:80/path') == 'http://example.com/path'
        assert normalize_url('https://example.com/path#section') == 'https://example.com/path'

    def test_generate_content_hash_includes_url(self):
        h1 = generate_content_hash('same content', 'https://a.com')
        h2 = generate_content_hash('same content', 'https://b.com')
        assert h1 != h2
        assert len(h1) == 64
