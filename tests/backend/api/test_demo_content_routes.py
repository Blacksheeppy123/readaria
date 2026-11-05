"""Unit tests for database-backed public demo content routes."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from backend.api.routes import demo


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
