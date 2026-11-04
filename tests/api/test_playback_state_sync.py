"""
API 回归 - 用户播放状态同步
"""
import os
import pytest
import requests


def _auth_session():
    base = os.getenv('TEST_BASE_URL', 'http://localhost:8000')
    username = os.getenv('TEST_USERNAME', 'test-user')
    password = os.getenv('TEST_PASSWORD', 'test123')
    s = requests.Session()
    s.headers.update({'Content-Type': 'application/json'})
    r = s.post(f"{base}/api/auth/login", json={"username": username, "password": password})
    r.raise_for_status()
    s.headers['Authorization'] = f"Bearer {r.json()['access_token']}"
    return base, s


@pytest.mark.api
def test_playback_state_sync_flow(wait_for_server):
    base, s = _auth_session()

    state = {
        "playlist": [
            {"id": 1, "url": "https://example.com/1", "title": "A"}
        ],
        "current_index": 0,
        "current_time": 12.5,
        "total_time": 120.0,
        "current_article": {"id": 1, "url": "https://example.com/1", "title": "A"},
        "is_playing": True,
        "playback_rate": 1.25
    }

    r = s.put(f"{base}/api/v1/playback-state", json=state)
    assert r.status_code == 200
    assert r.json()["status"] == "success"

    r = s.get(f"{base}/api/v1/playback-state")
    r.raise_for_status()
    data = r.json()["data"]
    assert data["playlist"] == state["playlist"]
    assert data["current_index"] == 0
    assert data["current_time"] == 12.5
    assert data["total_time"] == 120.0
    assert data["current_article"]["title"] == "A"
    assert data["is_playing"] is True
    assert data["playback_rate"] == 1.25
    assert data["updated_at"] is not None


@pytest.mark.api
def test_playback_state_unauthorized(wait_for_server):
    base = os.getenv('TEST_BASE_URL', 'http://localhost:8000')
    s = requests.Session()
    r = s.get(f"{base}/api/v1/playback-state")
    assert r.status_code == 403
