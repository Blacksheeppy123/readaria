"""
API 回归 - 收藏与已读
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
def test_saved_flow(wait_for_server):
    base, s, user = _auth_session()

    # 获取一篇文章
    r = s.get(f"{base}/api/user/{user}/feeds/articles", params={"page": 1, "size": 5})
    r.raise_for_status()
    items = r.json().get('articles', [])
    if not items:
        pytest.skip('无文章用于收藏测试')
    url = items[0]['url']

    # 先查询状态
    r = s.get(f"{base}/api/saved/status", params={"url": url})
    r.raise_for_status()
    saved0 = r.json().get('saved')

    # 收藏
    r = s.post(f"{base}/api/saved", json={"url": url})
    assert r.status_code == 200

    # 状态应为 True
    r = s.get(f"{base}/api/saved/status", params={"url": url})
    r.raise_for_status()
    assert r.json().get('saved') is True

    # 列表中能看到
    r = s.get(f"{base}/api/saved")
    r.raise_for_status()
    lst = r.json().get('articles', r.json())
    assert any(a.get('url') == url for a in lst)

    # 取消收藏
    r = s.delete(f"{base}/api/saved", params={"url": url})
    assert r.status_code == 200

