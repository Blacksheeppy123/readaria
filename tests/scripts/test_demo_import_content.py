"""Unit tests for idempotent and demo-scoped demo content imports."""

from unittest.mock import MagicMock

import pytest

from scripts import demo_import_content as importer


pytestmark = pytest.mark.unit


def _article(**overrides):
    article = {
        "demo_id": "demo-article-01",
        "title": "Curated title",
        "url": "https://example.com/articles/1",
        "author": "Curated author",
        "language": "en",
        "published_at": "2026-11-04T08:00:00+00:00",
        "summary": "Curated summary.",
        "excerpt": "Curated excerpt.",
        "source_name": "Demo Source",
    }
    article.update(overrides)
    return article


@pytest.mark.parametrize("invalid_url", ["ftp://example.com/article", "file:///tmp/article"])
def test_validate_input_rejects_non_http_article_urls(invalid_url):
    with pytest.raises(ValueError, match="http/https"):
        importer._validate_input({"articles": [_article(url=invalid_url)], "podcasts": []})


def test_validate_input_rejects_non_http_podcast_story_urls():
    podcast = {
        "demo_id": "demo-podcast-en",
        "title": "Demo podcast",
        "audio_file": "podcast.mp3",
        "stories": [{"title": "Story", "url": "javascript:alert(1)"}],
    }

    with pytest.raises(ValueError, match="http/https"):
        importer._validate_input({"articles": [], "podcasts": [podcast]})


def test_article_summary_upsert_does_not_touch_timestamps_when_unchanged():
    cursor = MagicMock()
    cursor.fetchone.return_value = {"id": 1}

    importer._import_article(cursor, _article(), None)

    summary_call = next(
        call
        for call in cursor.execute.call_args_list
        if "INSERT INTO article_summaries" in call.args[0]
    )
    assert "article_summaries.summary IS DISTINCT FROM EXCLUDED.summary" in summary_call.args[0]


def test_podcast_upsert_returns_existing_id_without_touching_timestamps():
    cursor = MagicMock()
    cursor.fetchone.side_effect = [
        None,  # A no-op DO UPDATE returns no row.
        {"id": 9, "user_id": importer.DEMO_CURATOR_ID},
    ]
    podcast = {
        "demo_id": "demo-podcast-en",
        "title": "Demo podcast",
        "description": "Same description",
        "duration": 100,
        "audio_file": "podcast.mp3",
    }

    podcast_id = importer._ensure_podcast(cursor, podcast)

    assert podcast_id == 9
    upsert_query = cursor.execute.call_args_list[0].args[0]
    assert "IS DISTINCT FROM" in upsert_query
    select_query = cursor.execute.call_args_list[1].args[0]
    assert "SELECT id, user_id FROM podcasts" in select_query


def test_wipe_only_deletes_demo_owned_registry_rows_and_preserves_global_articles():
    cursor = MagicMock()
    cursor.rowcount = 0

    importer._wipe(cursor)

    registry_query = cursor.execute.call_args_list[0].args[0]
    assert "DELETE FROM demo_content_registry" in registry_query
    assert "p.user_id = %s" in registry_query
    assert "ga.source_feed_url LIKE %s" in registry_query
    assert cursor.execute.call_args_list[0].args[1] == (
        importer.DEMO_CURATOR_ID,
        "demo://%",
    )
    assert all(
        "DELETE FROM global_articles" not in call.args[0]
        for call in cursor.execute.call_args_list
    )
