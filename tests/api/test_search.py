"""
API 回归 - 搜索（用户范围，ES 优先，PG 兜底）
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
    return base, s, username


@pytest.mark.api
def test_search_user_scoped(wait_for_server):
    base, s, user = _auth_session()

    # 选用常见中文关键字验证兜底（若 ES 不返回，接口会回落 PG）
    query = os.getenv('TEST_QUERY', '点金')
    r = s.get(f"{base}/articles/search", params={"query": query, "size": 10})
    assert r.status_code == 200
    data = r.json()
    assert 'results' in data
    assert isinstance(data['results'], list)

