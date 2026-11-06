from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.utils.feed_refresher import FeedRefresher

ZH_CONTENT = (
    "当地时间周二，美国财政部宣布将对中国商品加征关税，"
    "中方表示坚决反对并采取必要措施维护自身合法权益。"
    "多家机构分析认为，此举将对全球供应链产生深远影响，"
    "相关企业正在评估风险并调整生产布局，市场反应强烈。"
)

EN_CONTENT = (
    "The Treasury Department announced new tariffs on Tuesday, "
    "sparking broad concern among economists. Analysts say the move "
    "could disrupt global supply chains and raise costs for consumers. "
    "Several major companies are now reassessing their production plans."
)

EN_SUMMARY = (
    "The article analyzes the impact of tariff policies on global supply "
    "chains and explains how companies are adjusting their production "
    "plans in response to the latest economic developments this year."
)


def _make_refresher(cached_summary=None):
    rss_fetcher = MagicMock()
    rss_fetcher.fetch_multiple_feeds = AsyncMock(return_value=[{
        "title": "测试文章",
        "url": "http://example.com/post/1",
        "content": ZH_CONTENT,
    }])
    feed_url_manager = MagicMock()
    feed_url_manager.get_optimal_url.return_value = "http://example.com/feed"

    nlp_processor = MagicMock()
    nlp_processor.generate_summary.return_value = "中文摘要内容"
    nlp_processor.extract_entities.return_value = []

    db_manager = MagicMock()
    db_manager._get_user_id_by_feed_id.return_value = "user-1"
    db_manager.get_user_language.return_value = "en"  # 用户 UI 语言为英文
    db_manager.store_article.return_value = (100, 200, True)
    db_manager.get_article_summary.return_value = cached_summary
    db_manager.delete_article_summaries_except.return_value = 0
    db_manager.pg_conn = MagicMock()

    subscription_service = MagicMock()
    subscription_service.get_effective_plan.return_value = {"ai_summary_daily_limit": -1}

    refresher = FeedRefresher(rss_fetcher, feed_url_manager, nlp_processor, db_manager, subscription_service)
    return refresher, nlp_processor, db_manager


async def _refresh_one(refresher):
    return await refresher.refresh_feeds(
        [{"id": 1, "feed_name": "测试源", "feed_url": "http://example.com/feed"}],
        enable_logging=False,
        check_existence=False,
    )


@pytest.mark.unit
async def test_chinese_article_summary_uses_content_language_not_ui_language():
    """中文文章应使用内容语言 zh 生成摘要，即使用户 UI 语言是 en"""
    refresher, nlp_processor, db_manager = _make_refresher(cached_summary=None)

    await _refresh_one(refresher)

    nlp_processor.generate_summary.assert_called_once()
    _, kwargs = nlp_processor.generate_summary.call_args
    assert kwargs["language"] == "zh"
    db_manager.upsert_article_summary.assert_called_once_with(100, "zh", "中文摘要内容")
    # 旧逻辑按 UI 语言缓存的摘要行（如 'en' 键）会被清理，避免遮蔽内容语言摘要
    db_manager.delete_article_summaries_except.assert_called_once_with(100, "zh")


@pytest.mark.unit
async def test_english_article_summary_keeps_en():
    """英文文章内容语言检测为 en，缓存键仍为 en"""
    refresher, nlp_processor, db_manager = _make_refresher()
    refresher.rss_fetcher.fetch_multiple_feeds = AsyncMock(return_value=[{
        "title": "Test article",
        "url": "http://example.com/post/2",
        "content": EN_CONTENT,
    }])

    await _refresh_one(refresher)

    _, kwargs = nlp_processor.generate_summary.call_args
    assert kwargs["language"] == "en"
    db_manager.upsert_article_summary.assert_called_once_with(100, "en", "中文摘要内容")


@pytest.mark.unit
async def test_cached_summary_hit_skips_generation():
    """缓存命中时不再调用 LLM 生成"""
    refresher, nlp_processor, db_manager = _make_refresher(
        cached_summary="文章分析了关税政策对全球供应链的影响，市场反应强烈。"
    )

    await _refresh_one(refresher)

    nlp_processor.generate_summary.assert_not_called()
    db_manager.upsert_article_summary.assert_not_called()


@pytest.mark.unit
async def test_stale_cache_regenerated():
    """存量脏缓存（缓存键 zh 但实际是英文摘要）触发重新生成"""
    refresher, nlp_processor, db_manager = _make_refresher(cached_summary=EN_SUMMARY)

    await _refresh_one(refresher)

    nlp_processor.generate_summary.assert_called_once()
    _, kwargs = nlp_processor.generate_summary.call_args
    assert kwargs["language"] == "zh"
    db_manager.upsert_article_summary.assert_called_once_with(100, "zh", "中文摘要内容")


@pytest.mark.unit
async def test_legacy_shadow_rows_pruned():
    """修复前按 UI 语言缓存的其它语言摘要行（遮蔽问题）在刷新时被清理"""
    refresher, nlp_processor, db_manager = _make_refresher()
    db_manager.delete_article_summaries_except.return_value = 1  # 模拟存在旧的 'en' 行

    await _refresh_one(refresher)

    db_manager.delete_article_summaries_except.assert_called_once_with(100, "zh")
    # 清理后照常按内容语言生成并缓存
    db_manager.upsert_article_summary.assert_called_once_with(100, "zh", "中文摘要内容")
