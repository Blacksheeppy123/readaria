"""Tests for POST /api/v1/podcasts/generate dedup behavior.

Covers the three branches of the ``ORDER BY CASE WHEN source = 'onboarding_cache'``
dedup clause that was added to defeat the experience-podcast race:

* Today has only an ``onboarding_cache completed`` row → return the cache id so
  the client picks up the prebuilt podcast directly.
* Today has both ``user_generated pending`` and ``onboarding_cache completed``
  → ``ORDER BY CASE`` pushes the cache to position 2; the user_generated row
  wins, preventing duplicate creation.
* Today's only podcast is ``user_generated failed`` → fall through to quota
  check, podcast record creation, and usage recording (retry path).
"""

import sys
import types
from unittest.mock import MagicMock, PropertyMock, patch


def _stub_module(name, **attrs):
    """Insert a fake module into sys.modules with the given attributes."""
    mod = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(mod, key, value)
    sys.modules[name] = mod
    return mod


# Stub heavy/optional ML modules pulled in transitively by backend.api.main.
# These are not installed in the local test environment because they pull in
# large model weights and ship in the production image only.
sys.modules.setdefault('spacy', MagicMock())
_stub_module(
    'backend.nlp.processor',
    NLPProcessor=type('NLPProcessor', (), {'__init__': lambda self, *a, **kw: None}),
)

# Patch the pg pool BEFORE importing backend.api.main. DatabaseManager.__init__
# eagerly creates a ThreadedConnectionPool, which would require a reachable
# Postgres at import time otherwise.
_pool_patcher = patch('psycopg2.pool.ThreadedConnectionPool')
_pool_patcher.start()

import pytest  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

from backend.api.main import (  # noqa: E402
    app,
    subscription_service,
    get_current_user,
)
from backend.storage.database import DatabaseManager  # noqa: E402


# starlette 0.35 + httpx 0.28 are incompatible (starlette's TestClient passes
# ``app=`` to ``httpx.Client`` which httpx 0.28 dropped). Drive the ASGI app
# via ``httpx.AsyncClient`` + ``ASGITransport`` instead — pytest-asyncio's
# auto-mode runs the coroutine tests transparently.
@pytest.fixture
def override_user():
    app.dependency_overrides[get_current_user] = lambda: {
        "id": "test_user",
        "preferred_language": "en",
    }
    try:
        yield
    finally:
        app.dependency_overrides.clear()


async def _post_generate(payload=None):
    """POST /api/v1/podcasts/generate against the in-process ASGI app."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        return await ac.post(
            "/api/v1/podcasts/generate",
            json=payload or {"style": "deep_dive"},
            headers={"Authorization": "Bearer test"},
        )


def _patch_pg_conn_returning(row):
    """Patch ``DatabaseManager.pg_conn`` so the cursor() context manager yields
    a cursor whose ``fetchone()`` returns ``row``."""
    cursor = MagicMock()
    cursor.fetchone.return_value = row

    mock_conn = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = cursor
    mock_conn.cursor.return_value.__exit__.return_value = False

    return patch.object(
        DatabaseManager, 'pg_conn',
        new_callable=PropertyMock,
        return_value=mock_conn,
    )


async def test_generate_returns_already_generated_when_only_onboarding_cache_today(override_user):
    """Branch 1: today has only onboarding_cache completed → return cache id."""
    with _patch_pg_conn_returning((123, 'completed', 'onboarding_cache')):
        response = await _post_generate()

    assert response.status_code == 200, response.text
    body = response.json()
    assert body['success'] is True
    assert body['already_generated'] is True
    assert body['podcast_id'] == 123
    assert body['source'] == 'onboarding_cache'
    assert body['status'] == 'completed'


async def test_generate_user_generated_wins_over_cache_in_dedup(override_user):
    """Branch 2: when both rows exist today, the dedup query returns the
    user_generated row (ORDER BY CASE pushes onboarding_cache to position 2)."""
    with _patch_pg_conn_returning((456, 'pending', 'user_generated')):
        response = await _post_generate()

    assert response.status_code == 200, response.text
    body = response.json()
    assert body['already_generated'] is True
    assert body['podcast_id'] == 456
    assert body['status'] == 'pending'
    assert body['source'] == 'user_generated'


async def test_generate_allows_retry_when_today_podcast_failed(override_user):
    """Branch 3: today's only podcast is user_generated failed → fall through
    to quota check + new record creation."""
    new_podcast_id = 999
    quota_result = {
        'allowed': True,
        'used': 0,
        'limit': -1,
        'plan': 'selfhost',
    }

    with _patch_pg_conn_returning((789, 'failed', 'user_generated')), \
         patch.object(subscription_service, 'check_podcast_quota',
                      return_value=quota_result) as mock_quota, \
         patch.object(subscription_service, 'record_podcast_usage') as mock_record, \
         patch('backend.api.main.get_podcast_generator') as mock_factory:
        mock_generator = MagicMock()
        mock_generator._create_podcast_record.return_value = new_podcast_id
        mock_factory.return_value = mock_generator

        response = await _post_generate()

    assert response.status_code == 200, response.text
    body = response.json()
    assert body['already_generated'] is False
    assert body['podcast_id'] == new_podcast_id
    assert body['status'] == 'pending'

    mock_quota.assert_called_once_with('test_user')
    mock_generator._create_podcast_record.assert_called_once_with(
        'test_user', 'deep_dive', 'en'
    )
    mock_record.assert_called_once_with('test_user')
