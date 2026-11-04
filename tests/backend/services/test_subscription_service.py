import pytest
from unittest.mock import MagicMock
from backend.services.subscription_service import SubscriptionService


@pytest.fixture
def mock_db():
    db = MagicMock()
    db.pg_conn = MagicMock()
    return db


@pytest.fixture
def service(mock_db):
    return SubscriptionService(mock_db)


def test_effective_plan_is_unlimited_selfhost(service):
    plan = service.get_effective_plan("user1")

    assert plan["plan_id"] == "selfhost"
    assert plan["plan_name"] == "Self-hosted"
    assert plan["status"] == "active"
    assert plan["tts_daily_limit"] == -1
    assert plan["podcast_daily_limit"] == -1
    assert plan["ai_summary_daily_limit"] == -1


@pytest.mark.parametrize("check_name", [
    "check_tts_quota",
    "check_ai_summary_quota",
    "check_podcast_quota",
])
def test_all_quota_checks_allow_unlimited_usage(service, mock_db, check_name):
    result = getattr(service, check_name)("user1")

    assert result == {
        "allowed": True,
        "used": 0,
        "limit": -1,
        "plan": "selfhost",
    }
    mock_db.pg_conn.cursor.assert_not_called()


def test_subscription_summary_keeps_usage_shape(service, mock_db):
    mock_db.pg_conn.cursor.return_value.__enter__.return_value.fetchone.return_value = [2, 120, 1, 4]

    summary = service.get_subscription_summary("user1")

    assert summary["plan"] == "selfhost"
    assert summary["plan_name"] == "Self-hosted"
    assert summary["tts_daily_limit"] == -1
    assert summary["podcast_daily_limit"] == -1
    assert summary["ai_summary_daily_limit"] == -1
    assert summary["tts_used_today"] == 2
    assert summary["podcast_used_today"] == 1
    assert summary["ai_summary_used_today"] == 4


def test_record_ai_summary_usage_inserts_and_updates(service, mock_db):
    cur = mock_db.pg_conn.cursor.return_value.__enter__.return_value
    cur.execute.return_value = None
    assert service.record_ai_summary_usage("user1") is True
    call_args = cur.execute.call_args[0]
    assert "INSERT INTO user_usage_daily" in call_args[0]
    assert "ai_summary_count = user_usage_daily.ai_summary_count + 1" in call_args[0]
