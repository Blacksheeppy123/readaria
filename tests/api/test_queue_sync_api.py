"""
API 回归 - 用户听读队列同步
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
def test_queue_sync_flow(wait_for_server):
    base, s = _auth_session()

    sample_items = [
        {
            "id": 1,
            "url": "https://example.com/queue-1",
            "title": "Queue Article 1",
            "summary": "Summary 1",
            "source": "Test",
            "author": "Author",
            "published_at": "2026-07-15T00:00:00Z",
            "updated_at": "2026-07-15T00:00:00Z"
        },
        {
            "id": 2,
            "url": "https://example.com/queue-2",
            "title": "Queue Article 2",
            "summary": "Summary 2",
            "source": "Test",
            "author": "Author",
            "published_at": "2026-07-15T00:00:00Z",
            "updated_at": "2026-07-15T00:00:00Z"
        }
    ]

    # 更新队列
    r = s.put(f"{base}/api/v1/queue", json={"items": sample_items})
    assert r.status_code == 200
    assert r.json()["status"] == "success"

    # 读取队列
    r = s.get(f"{base}/api/v1/queue")
    r.raise_for_status()
    data = r.json()["data"]
    assert data["items"] == sample_items
    assert data["updated_at"] is not None

    # 清空队列
    r = s.delete(f"{base}/api/v1/queue")
    assert r.status_code == 200

    # 确认已清空
    r = s.get(f"{base}/api/v1/queue")
    r.raise_for_status()
    assert r.json()["data"]["items"] == []


@pytest.mark.api
def test_queue_unauthorized(wait_for_server):
    base = os.getenv('TEST_BASE_URL', 'http://localhost:8000')
    s = requests.Session()
    r = s.get(f"{base}/api/v1/queue")
    assert r.status_code == 403
