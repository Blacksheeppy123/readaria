import os

import pytest

from core.config.settings import Settings


def _base_env() -> dict:
    return {
        "openai_api_key": "test-openai-key-12345",
        "postgres_password": "test-postgres-password",
        "secret_key": "x" * 32,
        "jwt_secret_key": "y" * 32,
    }


def test_settings_accept_google_application_credentials_env():
    env = {
        **_base_env(),
        "google_application_credentials": "/tmp/google-creds.json",
    }

    settings = Settings(**env)

    assert settings.google_application_credentials == "/tmp/google-creds.json"
    assert settings.resolved_google_credentials_path == "/tmp/google-creds.json"


def test_explicit_google_cloud_credentials_path_takes_precedence():
    env = {
        **_base_env(),
        "google_cloud_credentials_path": "/tmp/explicit-google-creds.json",
        "google_application_credentials": "/tmp/fallback-google-creds.json",
    }

    settings = Settings(**env)

    assert settings.google_cloud_credentials_path == "/tmp/explicit-google-creds.json"
    assert settings.google_application_credentials == "/tmp/fallback-google-creds.json"
    assert settings.resolved_google_credentials_path == "/tmp/explicit-google-creds.json"


@pytest.mark.unit
def test_tts_voice_catalog_shape():
    """音色目录：zh/en 分组、条目字段完整、每组恰好一个默认音色。"""
    from core.config.settings import TTS_VOICE_CATALOG

    assert set(TTS_VOICE_CATALOG.keys()) == {"zh", "en"}
    assert len(TTS_VOICE_CATALOG["zh"]) >= 5
    assert len(TTS_VOICE_CATALOG["en"]) >= 3

    for lang, voices in TTS_VOICE_CATALOG.items():
        defaults = [v for v in voices if v["is_default"]]
        assert len(defaults) == 1, f"{lang} 组必须恰好一个默认音色"
        for v in voices:
            assert v["id"] and "Neural" in v["id"]
            assert v["lang"] == lang
            assert v["name"] and v["description"] and v["sample_text"]
            assert v["gender"] in ("female", "male")
