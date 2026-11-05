"""Unit tests for database-backed public demo content routes."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from backend.api.routes import demo
from scripts import demo_import_content as importer


pytestmark = [pytest.mark.unit, pytest.mark.api]


def _demo_app():
    settings = SimpleNamespace(
        demo_mode=True,
        demo_turnstile_secret_key="",
        demo_daily_interaction_limit=3,
        openai_model="gpt-test",
        openai_base_url="https://api.openai.com/v1",
    )
    app = FastAPI()
    app.include_router(demo.create_demo_router(settings=settings, redis_client=MagicMock()))
    return app


def _registry_content():
    return {
        "podcasts": [
            {
                "share_token": "demo-demo-podcast-zh",
                "title": "Demo podcast",
                "duration": 491,
                "created_at": "2026-11-05T08:00:00+00:00",
            }
        ],
        "articles": [
            {
                "demo_id": "demo-article-01",
                "title": "A real article",
                "author": "Demo Author",
                "source_name": "Demo Source",
                "published_at": "2026-11-04T08:00:00+00:00",
                "language": "zh",
                "summary": "A concise summary.",
                "excerpt": "The article excerpt.",
                "original_url": "https://example.com/articles/1",
                "audio_url": "/static/demo/audio/article_01.mp3",
            }
        ],
    }


async def _get(app, path):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        return await client.get(path)


async def test_demo_content_returns_real_sections(monkeypatch):
    monkeypatch.setattr(demo, "_load_registry", lambda settings: _registry_content(), raising=False)
    app = _demo_app()

    response = await _get(app, "/api/demo/content")

    assert response.status_code == 200
    body = response.json()
    assert body["podcasts"] == _registry_content()["podcasts"]
    assert body["articles"] == [
        {
            "demo_id": "demo-article-01",
            "title": "A real article",
            "source_name": "Demo Source",
            "summary": "A concise summary.",
            "excerpt": "The article excerpt.",
        }
    ]


async def test_demo_article_not_found(monkeypatch):
    monkeypatch.setattr(demo, "_load_registry", lambda settings: {"podcasts": [], "articles": []}, raising=False)
    app = _demo_app()

    response = await _get(app, "/api/demo/articles/no-such-id")

    assert response.status_code == 404


async def test_demo_article_detail_shape(monkeypatch):
    monkeypatch.setattr(demo, "_load_registry", lambda settings: {"podcasts": [], "articles": []}, raising=False)
    app = _demo_app()

    response = await _get(app, "/api/demo/articles")

    assert response.status_code == 200
    assert response.json() == {"articles": []}


async def test_demo_article_detail_returns_public_fields(monkeypatch):
    monkeypatch.setattr(demo, "_load_registry", lambda settings: _registry_content(), raising=False)
    app = _demo_app()

    response = await _get(app, "/api/demo/articles/demo-article-01")

    assert response.status_code == 200
    assert response.json() == _registry_content()["articles"][0]
    assert "feed_url" not in response.json()
    assert "user_id" not in response.json()


async def test_existing_url_import_replaces_private_content_exposed_by_public_api(monkeypatch):
    curated = {
        "demo_id": "demo-article-01",
        "title": "Curated public title",
        "url": "https://example.com/articles/1",
        "author": "Curated author",
        "language": "en",
        "published_at": "2026-11-04T08:00:00+00:00",
        "summary": "Curated public summary.",
        "excerpt": "Curated public excerpt.",
        "source_name": "Demo Source",
    }
    existing = {
        "id": 41,
        "url": curated["url"],
        "title": "Old private title",
        "author": "Old private author",
        "published_at": "2025-01-01T00:00:00+00:00",
        "content": "Old private content",
        "summary": "Old private summary",
        "source_feed_url": "https://private.example.com/feed",
        "source_type_id": "blog",
        "language": "zh",
        "word_count": 3,
        "reading_time": 1,
    }
    import_cursor = MagicMock()
    import_cursor.fetchone.return_value = existing

    global_id = importer._ensure_global_article(
        import_cursor, curated, "demo://source/demo-source"
    )

    assert global_id == 41
    update_call = next(
        call
        for call in import_cursor.execute.call_args_list
        if call.args[0].lstrip().startswith("UPDATE global_articles")
    )
    public_state = {**existing, **update_call.args[1]}
    assert public_state["source_feed_url"] == "demo://source/demo-source"

    article_row = {
        "demo_id": curated["demo_id"],
        "title": public_state["title"],
        "author": public_state["author"],
        "published_at": public_state["published_at"],
        "language": public_state["language"],
        "original_url": public_state["url"],
        "excerpt": public_state["content"],
        "tts_audio_path": None,
        "source_name": curated["source_name"],
        "summary": public_state["summary"],
    }

    class FakeCursor:
        def __init__(self):
            self.queries = []
            self.query_params = []
            self.rows = []

        def execute(self, query, params=None):
            self.queries.append(query)
            self.query_params.append(params)
            self.rows = [article_row] if "JOIN global_articles" in query else []

        def fetchall(self):
            return self.rows

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

    class FakeConnection:
        def __init__(self):
            self.demo_cursor = FakeCursor()

        def cursor(self, cursor_factory=None):
            return self.demo_cursor

        def close(self):
            return None

    connection = FakeConnection()
    monkeypatch.setattr(demo, "_create_demo_connection", lambda settings: connection)
    app = _demo_app()

    response = await _get(app, "/api/demo/articles/demo-article-01")

    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "Curated public title"
    assert body["author"] == "Curated author"
    assert body["summary"] == "Curated public summary."
    assert body["excerpt"] == "Curated public excerpt."
    assert "Old private" not in response.text
    article_query_index = next(
        index
        for index, query in enumerate(connection.demo_cursor.queries)
        if "JOIN global_articles" in query
    )
    article_query = connection.demo_cursor.queries[article_query_index]
    article_params = connection.demo_cursor.query_params[article_query_index]
    assert "ga.source_feed_url LIKE %s" in article_query
    assert article_params[-1] == "demo://%"
    assert "uf.feed_url = ga.source_feed_url" in article_query
    assert "demo_feed.feed_url = ga.source_feed_url" in article_query
    assert "demo_ref.user_summary" in article_query
    assert "ga.summary" not in article_query
    assert "article_summaries" not in article_query
