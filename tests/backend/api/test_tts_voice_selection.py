"""TTS 音色选择端点测试

覆盖：
- GET /api/v1/tts/voices 目录 shape
- PATCH /api/auth/me/tts-voices 校验（合法 / 非法 id / 语言不匹配 / null 重置 / 空 body / DB 失败）
- GET /api/auth/me 响应携带 tts_voice_zh/en 字段
"""

import sys
import types
from unittest.mock import MagicMock, patch


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

from backend.api.main import app, get_current_user  # noqa: E402

pytestmark = [pytest.mark.unit, pytest.mark.api, pytest.mark.tts]


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


def _client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_get_tts_voices(override_user):
    async with _client() as client:
        resp = await client.get("/api/v1/tts/voices")
    assert resp.status_code == 200
    data = resp.json()
    assert set(data.keys()) == {"zh", "en"}
    zh_ids = [v["id"] for v in data["zh"]]
    assert "zh-CN-Xiaoxiao:DragonHDFlashLatestNeural" in zh_ids
    assert "zh-CN-YunyangNeural" in zh_ids
    en_ids = [v["id"] for v in data["en"]]
    assert "en-US-Tiana:DragonHDFlashLatestNeural" in en_ids
    for lang in ("zh", "en"):
        defaults = [v for v in data[lang] if v.get("is_default")]
        assert len(defaults) == 1
        for v in data[lang]:
            assert v["sample_text"] and v["name"] and v["description"]


async def test_patch_tts_voice_success(override_user):
    with patch('backend.api.main.db_manager') as mock_db:
        mock_db.update_user.return_value = True
        async with _client() as client:
            resp = await client.patch(
                "/api/auth/me/tts-voices",
                json={"tts_voice_zh": "zh-CN-YunyangNeural"},
            )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "success"
    mock_db.update_user.assert_called_once_with(
        "test_user", tts_voice_zh="zh-CN-YunyangNeural"
    )


async def test_patch_tts_voice_invalid_id(override_user):
    async with _client() as client:
        resp = await client.patch(
            "/api/auth/me/tts-voices", json={"tts_voice_zh": "not-a-voice"}
        )
    assert resp.status_code == 400


async def test_patch_tts_voice_lang_mismatch(override_user):
    """英文音色 id 不能写入中文字段"""
    async with _client() as client:
        resp = await client.patch(
            "/api/auth/me/tts-voices",
            json={"tts_voice_zh": "en-US-Ava:DragonLatestNeural"},
        )
    assert resp.status_code == 400


async def test_patch_tts_voice_reset_to_default(override_user):
    """显式 null = 恢复系统默认"""
    with patch('backend.api.main.db_manager') as mock_db:
        mock_db.update_user.return_value = True
        async with _client() as client:
            resp = await client.patch(
                "/api/auth/me/tts-voices", json={"tts_voice_zh": None}
            )
    assert resp.status_code == 200, resp.text
    mock_db.update_user.assert_called_once_with("test_user", tts_voice_zh=None)


async def test_patch_tts_voice_empty_body(override_user):
    async with _client() as client:
        resp = await client.patch("/api/auth/me/tts-voices", json={})
    assert resp.status_code == 400


async def test_patch_tts_voice_db_failure(override_user):
    with patch('backend.api.main.db_manager') as mock_db:
        mock_db.update_user.return_value = False
        async with _client() as client:
            resp = await client.patch(
                "/api/auth/me/tts-voices",
                json={"tts_voice_en": "en-US-Ava:DragonLatestNeural"},
            )
    assert resp.status_code == 500


async def test_me_returns_tts_voice_fields():
    app.dependency_overrides[get_current_user] = lambda: {
        "id": "u1",
        "username": "u",
        "email": "u@x.com",
        "is_active": True,
        "is_superuser": False,
        "preferred_language": "en",
        "auto_podcast_enabled": False,
        "tts_voice_zh": "zh-CN-YunyangNeural",
        "tts_voice_en": None,
    }
    try:
        with patch('backend.api.main.subscription_service') as mock_sub:
            mock_sub.get_subscription_summary.return_value = None
            async with _client() as client:
                resp = await client.get("/api/auth/me")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["tts_voice_zh"] == "zh-CN-YunyangNeural"
        assert "tts_voice_en" in data
    finally:
        app.dependency_overrides.clear()


async def test_voice_preview_success(override_user):
    """试听：目录内音色 → 200 + MP3；不调用 record_tts_usage（不占配额）"""
    mock_svc = MagicMock()

    async def fake_synthesize(**kwargs):
        assert kwargs["voice"] == "zh-CN-YunyangNeural"
        assert kwargs["text"]  # 使用目录固定示例文本
        return b"\xff\xfb\x90" + b"\x00" * 100

    mock_svc.synthesize = fake_synthesize
    with patch('backend.api.main.get_speech_service', return_value=mock_svc), \
         patch('backend.api.main.subscription_service') as mock_sub:
        async with _client() as client:
            resp = await client.post(
                "/api/v1/tts/voice-preview",
                json={"voice": "zh-CN-YunyangNeural", "lang": "zh"},
            )
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"].startswith("audio/mpeg")
    assert resp.content.startswith(b"\xff\xfb")
    mock_sub.record_tts_usage.assert_not_called()


async def test_voice_preview_default_voice(override_user):
    """试听：voice='default' → 该语言默认音色，voice=None 传给 service"""
    mock_svc = MagicMock()
    seen = {}

    async def fake_synthesize(**kwargs):
        seen.update(kwargs)
        return b"\xff\xfb\x90" + b"\x00" * 100

    mock_svc.synthesize = fake_synthesize
    with patch('backend.api.main.get_speech_service', return_value=mock_svc):
        async with _client() as client:
            resp = await client.post(
                "/api/v1/tts/voice-preview",
                json={"voice": "default", "lang": "en"},
            )
    assert resp.status_code == 200, resp.text
    assert seen["voice"] is None
    assert seen["lang"] == "en"


async def test_voice_preview_invalid_voice(override_user):
    async with _client() as client:
        resp = await client.post(
            "/api/v1/tts/voice-preview",
            json={"voice": "not-a-voice", "lang": "zh"},
        )
    assert resp.status_code == 400


async def test_voice_preview_invalid_lang(override_user):
    async with _client() as client:
        resp = await client.post(
            "/api/v1/tts/voice-preview",
            json={"voice": "default", "lang": "fr"},
        )
    assert resp.status_code == 400
