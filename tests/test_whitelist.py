import sys
from pathlib import Path

import pytest

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from backend.utils.whitelist import (
    filter_tts_pregenerate_users,
    filter_feature_whitelist_users,
    filter_whitelist_users,
    is_frontend_log_whitelist_user,
    is_feature_whitelist_user,
    is_whitelist_user,
)
from core.config.settings import settings


@pytest.mark.unit
def test_is_feature_whitelist_user(monkeypatch):
    monkeypatch.setattr(settings, "feature_whitelist", ["test-user"])

    assert is_feature_whitelist_user("test-user") is True
    assert is_feature_whitelist_user("Test-User") is True
    assert is_feature_whitelist_user("alex") is False
    assert is_feature_whitelist_user(None) is False


@pytest.mark.unit
def test_is_whitelist_user_alias_uses_feature_whitelist(monkeypatch):
    monkeypatch.setattr(settings, "feature_whitelist", ["test-user"])

    assert is_whitelist_user("test-user") is True
    assert is_whitelist_user("alex") is False


@pytest.mark.unit
def test_filter_feature_whitelist_users_preserves_order_and_uniqueness(monkeypatch):
    monkeypatch.setattr(settings, "feature_whitelist", ["test-user", "prod-test-1128"])

    filtered = filter_feature_whitelist_users(
        ["alex", "Test-User", "prod-test-1128", "test-user", "", None]
    )

    assert filtered == ["Test-User", "prod-test-1128"]


@pytest.mark.unit
def test_filter_whitelist_users_alias_uses_feature_whitelist(monkeypatch):
    monkeypatch.setattr(settings, "feature_whitelist", ["test-user", "prod-test-1128"])

    filtered = filter_whitelist_users(
        ["alex", "test-user", "prod-test-1128", "test-user", "", None]
    )

    assert filtered == ["test-user", "prod-test-1128"]


@pytest.mark.unit
def test_filter_tts_pregenerate_users_uses_whitelist_by_default(monkeypatch):
    monkeypatch.setattr(settings, "feature_whitelist", ["test-user"])
    monkeypatch.setattr(settings, "tts_pregenerate_all_users", False)

    filtered = filter_tts_pregenerate_users(["test-user", "alex", "test-user"])

    assert filtered == ["test-user"]


@pytest.mark.unit
def test_filter_tts_pregenerate_users_can_allow_all_users(monkeypatch):
    monkeypatch.setattr(settings, "feature_whitelist", ["test-user"])
    monkeypatch.setattr(settings, "tts_pregenerate_all_users", True)

    filtered = filter_tts_pregenerate_users(["test-user", "alex", "test-user"])

    assert filtered == ["test-user", "alex"]


@pytest.mark.unit
def test_frontend_log_whitelist_is_independent_from_feature_whitelist(monkeypatch):
    monkeypatch.setattr(settings, "feature_whitelist", ["test-user"])
    monkeypatch.setattr(settings, "frontend_log_whitelist", ["test-user", "testuser2"])

    assert is_feature_whitelist_user("testuser2") is False
    assert "testuser2" in settings.frontend_log_whitelist


@pytest.mark.unit
def test_frontend_log_whitelist_is_case_insensitive(monkeypatch):
    monkeypatch.setattr(settings, "frontend_log_whitelist", ["test-user", "testuser2"])

    assert is_frontend_log_whitelist_user("Testuser2") is True
    assert is_frontend_log_whitelist_user("TEST-USER") is True
    assert is_frontend_log_whitelist_user("alex") is False
