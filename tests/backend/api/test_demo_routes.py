"""Unit tests for the opt-in public demo routes."""

import logging
import sys
import types
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient


DEMO_KEY = "sk-demo-visitor-secret-must-never-leak"


def _stub_module(name, **attrs):
    module = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(module, key, value)
    sys.modules[name] = module
    return module


# Keep the main-app import lightweight, matching the existing API test pattern.
sys.modules.setdefault("spacy", MagicMock())
_stub_module(
    "backend.nlp.processor",
    NLPProcessor=type("NLPProcessor", (), {"__init__": lambda self: None}),
)
_pool_patcher = patch("psycopg2.pool.ThreadedConnectionPool")
_pool_patcher.start()

from backend.api.main import app as default_app  # noqa: E402
from core.config.settings import Settings  # noqa: E402

pytestmark = [pytest.mark.unit, pytest.mark.api]


def _settings(**overrides):
    values = {
        "demo_mode": True,
        "demo_turnstile_secret_key": "",
        "demo_daily_interaction_limit": 3,
        "openai_model": "gpt-test",
        "openai_base_url": "https://api.openai.com/v1",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _demo_app(redis_client=None, **setting_overrides):
    from backend.api.routes.demo import create_demo_router

    redis_client = redis_client or MagicMock()
    redis_client.incr.return_value = 1
    app = FastAPI()
    app.include_router(
        create_demo_router(settings=_settings(**setting_overrides), redis_client=redis_client)
    )
    return app, redis_client


async def _get(app, path):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        return await client.get(path)


async def _post_summary(app, **kwargs):
    payload = kwargs.pop("json", {"content": "A short public article used for the demo."})
    headers = kwargs.pop("headers", {"x-demo-api-key": DEMO_KEY})
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        return await client.post("/api/demo/summary", json=payload, headers=headers, **kwargs)


def _completion(text="A concise demo summary."):
    completion = MagicMock()
    completion.choices[0].message.content = text
    return completion


async def test_demo_routes_are_not_mounted_by_default():
    response = await _get(default_app, "/api/demo/content")

    assert response.status_code == 404


def test_demo_settings_default_to_disabled():
    settings = Settings(
        openai_api_key="test-openai-key-12345",
        postgres_password="test-postgres-password",
        secret_key="x" * 32,
        jwt_secret_key="y" * 32,
    )

    assert settings.demo_mode is False
    assert settings.demo_turnstile_secret_key == ""
    assert settings.demo_daily_interaction_limit == 3


async def test_demo_content_returns_pre_generated_public_articles():
    app, _ = _demo_app()

    response = await _get(app, "/api/demo/content")

    assert response.status_code == 200
    articles = response.json()["articles"]
    assert 5 <= len(articles) <= 8
    assert len({article["source"]["name"] for article in articles}) == len(articles)
    for article in articles:
        assert article["id"]
        assert article["title"]
        assert article["url"].startswith("https://")
        assert article["source"]["name"]
        assert article["source"]["feed_url"].startswith("https://")
        assert article["summary"]
        assert article["podcast_audio_url"].startswith("/static/demo/")
        assert article["content"]
        assert "wechat" not in article["source"]["feed_url"].lower()


async def test_demo_summary_requires_byok_key():
    app, _ = _demo_app()

    response = await _post_summary(app, headers={})

    assert response.status_code == 400


async def test_demo_summary_uses_visitor_key_without_persisting_it():
    app, redis_client = _demo_app()

    with patch("backend.api.routes.demo.OpenAI") as openai_class:
        openai_class.return_value.chat.completions.create.return_value = _completion()
        response = await _post_summary(app)

    assert response.status_code == 200
    assert response.json()["summary"] == "A concise demo summary."
    openai_class.assert_called_once_with(
        api_key=DEMO_KEY,
        base_url="https://api.openai.com/v1",
        timeout=30.0,
        max_retries=0,
    )
    assert redis_client.incr.call_count == 1
    assert DEMO_KEY not in repr(redis_client.method_calls)


async def test_demo_summary_returns_429_when_daily_limit_is_exceeded():
    app, redis_client = _demo_app()
    redis_client.incr.return_value = 4

    with patch("backend.api.routes.demo.OpenAI") as openai_class:
        response = await _post_summary(app)

    assert response.status_code == 429
    openai_class.assert_not_called()


async def test_demo_summary_never_logs_or_returns_visitor_key(caplog):
    app, _ = _demo_app()
    caplog.set_level(logging.INFO)

    with patch("backend.api.routes.demo.OpenAI") as openai_class:
        openai_class.return_value.chat.completions.create.side_effect = RuntimeError(
            f"Provider echoed credential: {DEMO_KEY}"
        )
        response = await _post_summary(app)

    assert response.status_code == 502
    assert DEMO_KEY not in response.text
    assert DEMO_KEY not in caplog.text


async def test_demo_summary_rejects_failed_turnstile_verification():
    app, _ = _demo_app(demo_turnstile_secret_key="turnstile-test-secret")
    verification = MagicMock()
    verification.json.return_value = {"success": False}
    verification.raise_for_status.return_value = None

    with patch("backend.api.routes.demo.httpx.post", return_value=verification), patch(
        "backend.api.routes.demo.OpenAI"
    ) as openai_class:
        response = await _post_summary(
            app, json={"content": "Article", "turnstile_token": "invalid-token"}
        )

    assert response.status_code == 403
    openai_class.assert_not_called()


async def test_demo_summary_supports_custom_openai_compatible_base_url():
    app, _ = _demo_app()
    base_url = "https://llm.example.com/v1"

    with patch(
        "backend.api.routes.demo.socket.getaddrinfo",
        return_value=[(2, 1, 6, "", ("8.8.8.8", 443))],
    ), patch("backend.api.routes.demo.OpenAI") as openai_class:
        openai_class.return_value.chat.completions.create.return_value = _completion()
        response = await _post_summary(
            app, headers={"x-demo-api-key": DEMO_KEY, "x-demo-base-url": base_url}
        )

    assert response.status_code == 200
    assert openai_class.call_args.kwargs["base_url"] == base_url


async def test_demo_summary_rejects_private_provider_base_url():
    app, _ = _demo_app()

    with patch("backend.api.routes.demo.OpenAI") as openai_class:
        response = await _post_summary(
            app,
            headers={
                "x-demo-api-key": DEMO_KEY,
                "x-demo-base-url": "http://127.0.0.1:8080/v1",
            },
        )

    assert response.status_code == 400
    openai_class.assert_not_called()


async def test_demo_summary_can_fetch_an_article_url():
    app, _ = _demo_app()

    with patch(
        "backend.api.routes.demo._fetch_article_content", return_value="Fetched public article text"
    ) as fetch_article, patch("backend.api.routes.demo.OpenAI") as openai_class:
        openai_class.return_value.chat.completions.create.return_value = _completion()
        response = await _post_summary(
            app, json={"url": "https://example.com/public-article"}
        )

    assert response.status_code == 200
    fetch_article.assert_called_once_with("https://example.com/public-article")
    messages = openai_class.return_value.chat.completions.create.call_args.kwargs["messages"]
    assert messages[-1]["content"] == "Fetched public article text"


def test_sentry_event_scrubs_demo_api_key_header():
    from backend.api.main import _scrub_sensitive_headers

    event = {
        "request": {
            "headers": {
                "Content-Type": "application/json",
                "X-Demo-Api-Key": DEMO_KEY,
            }
        }
    }

    scrubbed = _scrub_sensitive_headers(event)

    assert scrubbed["request"]["headers"]["X-Demo-Api-Key"] == "[Filtered]"
    assert DEMO_KEY not in repr(scrubbed)


def test_outbound_network_backend_connects_to_validated_ip_not_hostname():
    from backend.api.routes.demo import _PinnedNetworkBackend

    backend = _PinnedNetworkBackend("llm.example.com", ("8.8.8.8",))
    with patch("backend.api.routes.demo.SyncBackend.connect_tcp") as connect_tcp:
        backend.connect_tcp("llm.example.com", 443, 30.0, None, None)

    connect_tcp.assert_called_once_with("8.8.8.8", 443, 30.0, None, None)
