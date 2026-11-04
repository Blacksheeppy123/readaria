"""
Onboarding API 回归测试
覆盖 starter-pack 接口
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
    if r.status_code == 401:
        r2 = s.post(f"{base}/api/auth/register", json={"username": username, "email": f"{username}@example.com", "password": password})
        r2.raise_for_status()
        token = r2.json()['access_token']
    else:
        r.raise_for_status()
        token = r.json()['access_token']
    s.headers['Authorization'] = f"Bearer {token}"
    return base, s, username


@pytest.mark.api
def test_starter_pack_returns_valid_feeds(wait_for_server):
    base, s, _ = _auth_session()

    r = s.get(f"{base}/api/v1/onboarding/starter-pack?language=zh")
    assert r.status_code == 200
    data = r.json()

    assert data.get('status') == 'success'
    assert 'feeds' in data
    feeds = data['feeds']

    # 若测试环境已预置验证数据，则返回的 feed 都应包含关键字段
    for feed in feeds:
        assert 'feed_url' in feed
        assert 'feed_name' in feed
        assert 'article_count' in feed
        assert 'avg_content_length' in feed


@pytest.mark.api
def test_starter_pack_default_language(wait_for_server):
    base, s, _ = _auth_session()

    r = s.get(f"{base}/api/v1/onboarding/starter-pack")
    assert r.status_code == 200
    data = r.json()
    assert data.get('status') == 'success'
    assert 'feeds' in data
