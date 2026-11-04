"""
API 回归 - 文章列表/详情/筛选
"""
import os
import time
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
def test_articles_list_and_detail(wait_for_server):
    base, s, user = _auth_session()

    # 列表第一页
    r = s.get(f"{base}/api/user/{user}/feeds/articles", params={"page": 1, "size": 20})
    assert r.status_code == 200
    data = r.json()
    items = data.get('articles', [])
    assert isinstance(items, list)
    pagination = data.get('pagination', {})
    assert 'total' in pagination
    assert 'playable_total' in pagination
    overview = data.get('overview', {})
    assert 'today_ready_count' in overview

    # 若有数据，取第一条做详情
    if items:
        url = items[0].get('url')
        if url:
            r = s.get(f"{base}/api/articles/by-url", params={"url": url})
            assert r.status_code in (200, 404)


@pytest.mark.api
def test_read_mark_and_filter(wait_for_server):
    base, s, user = _auth_session()

    # 取一条文章
    r = s.get(f"{base}/api/user/{user}/feeds/articles", params={"page": 1, "size": 10})
    r.raise_for_status()
    items = r.json().get('articles', [])
    if not items:
        pytest.skip('无文章可用于已读测试')

    url = items[0]['url']

    # 标记已读
    r = s.post(f"{base}/api/articles/read", json={"url": url})
    assert r.status_code == 200

    # 过滤 read=read 应包含该条
    r = s.get(f"{base}/api/user/{user}/feeds/articles", params={"page": 1, "size": 10, "read": "read"})
    r.raise_for_status()
    items = r.json().get('articles', [])
    assert any(a.get('url') == url for a in items)

    # 取消已读
    r = s.delete(f"{base}/api/articles/read", params={"url": url})
    assert r.status_code == 200
