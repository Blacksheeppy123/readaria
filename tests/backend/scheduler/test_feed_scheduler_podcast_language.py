"""
测试调度器自动播客生成时是否正确传递用户语言偏好
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from backend.scheduler.feed_scheduler import FeedScheduler


class TestPodcastLanguagePassing:
    """验证调度器根据用户 preferred_language 传递正确的 language 参数"""

    @pytest.fixture
    def scheduler(self):
        """创建带有 mock 依赖的 FeedScheduler"""
        mock_db = MagicMock()
        mock_db.connection_scope.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_db.connection_scope.return_value.__exit__ = MagicMock(return_value=False)

        return FeedScheduler(
            rss_fetcher=MagicMock(),
            feed_url_manager=MagicMock(),
            nlp_processor=MagicMock(),
            db_manager=mock_db,
            subscription_service=MagicMock()
        )

    @pytest.fixture
    def mock_podcast_generator(self):
        """Mock PodcastGenerator 实例（patch 源模块，因调度器内使用局部 import）"""
        with patch("backend.services.podcast_generator.PodcastGenerator") as MockGen:
            instance = MagicMock()
            instance.generate_daily_podcast = AsyncMock(return_value=42)
            MockGen.return_value = instance
            yield instance

    @pytest.fixture
    def mock_settings(self):
        """Mock settings 避免外部配置依赖"""
        with patch("backend.scheduler.feed_scheduler.settings") as s:
            s.podcast_enabled = True
            s.podcast_style_default = "deep_dive"
            s.podcast_max_articles = 10
            yield s

    @pytest.mark.parametrize("preferred_language,expected_lang", [
        ("en", "en"),
        ("EN", "en"),
        ("En", "en"),
        ("zh", "zh"),
        ("", "zh"),
        (None, "zh"),
        ("fr", "zh"),
        ("ja", "zh"),
    ])
    @pytest.mark.asyncio
    async def test_language_normalization(
        self, scheduler, mock_podcast_generator, mock_settings,
        preferred_language, expected_lang
    ):
        """
        参数化测试：不同 preferred_language 输入 → 正确 language 输出

        - 'en' / 'EN' / 'En' → language='en'
        - 空串 / None / 其他语言 → language='zh'
        """
        # 设置模拟用户
        scheduler.db_manager.get_podcast_enabled_users.return_value = [
            ("test-user", preferred_language)
        ]

        # 模拟配额检查通过
        scheduler.subscription_service.check_podcast_quota.return_value = {
            "allowed": True, "limit": 10, "used": 0
        }

        # 执行
        await scheduler._generate_daily_podcasts_impl()

        # 断言：generate_daily_podcast 被调用且 language 参数正确
        mock_podcast_generator.generate_daily_podcast.assert_awaited_once()
        call_kwargs = mock_podcast_generator.generate_daily_podcast.await_args.kwargs
        assert call_kwargs["language"] == expected_lang
        assert call_kwargs["user_id"] == "test-user"

    @pytest.mark.asyncio
    async def test_multiple_users_different_languages(
        self, scheduler, mock_podcast_generator, mock_settings
    ):
        """
        多个用户、不同语言偏好的场景
        """
        scheduler.db_manager.get_podcast_enabled_users.return_value = [
            ("user-en", "en"),
            ("user-zh", "zh"),
            ("user-null", None),
        ]

        scheduler.subscription_service.check_podcast_quota.return_value = {
            "allowed": True, "limit": 10, "used": 0
        }

        await scheduler._generate_daily_podcasts_impl()

        assert mock_podcast_generator.generate_daily_podcast.await_count == 3
        calls = mock_podcast_generator.generate_daily_podcast.await_args_list

        lang_by_user = {c.kwargs["user_id"]: c.kwargs["language"] for c in calls}
        assert lang_by_user == {
            "user-en": "en",
            "user-zh": "zh",
            "user-null": "zh",
        }

    @pytest.mark.asyncio
    async def test_podcast_disabled_skips_generation(
        self, scheduler, mock_podcast_generator
    ):
        """
        podcast_enabled = False 时直接返回，不调用生成器
        """
        with patch("backend.scheduler.feed_scheduler.settings") as s:
            s.podcast_enabled = False

            await scheduler._generate_daily_podcasts_impl()

        mock_podcast_generator.generate_daily_podcast.assert_not_awaited()
