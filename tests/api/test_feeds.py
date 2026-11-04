"""
API 回归 - 订阅 CRUD 与 URL 验证、统计
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
        # 尝试注册
        r2 = s.post(f"{base}/api/auth/register", json={"username": username, "email": f"{username}@example.com", "password": password})
        r2.raise_for_status()
        token = r2.json()['access_token']
    else:
        r.raise_for_status()
        token = r.json()['access_token']
    s.headers['Authorization'] = f"Bearer {token}"
    return base, s, username


@pytest.mark.api
def test_feed_crud_and_validation(wait_for_server):
    base, s, user = _auth_session()

    # URL 验证（有效）
    valid_url = os.getenv('TEST_FEED_URL', 'https://rsshub.app/v2ex/topics/hot')
    r = s.post(f"{base}/api/feeds/test", json={"feed_url": valid_url})
    assert r.status_code == 200
    assert r.json().get('status') in ('success', 'warning')

    # 添加
    body = {"feed_name": "测试源-回归", "feed_url": valid_url}
    r = s.post(f"{base}/user/{user}/feeds", json=body)
    assert r.status_code == 200
    feed_id = r.json().get('feed_id')
    assert feed_id

    # 列表
    r = s.get(f"{base}/user/{user}/feeds")
    r.raise_for_status()
    feeds = r.json().get('feeds', [])
    assert any(f.get('id') == feed_id for f in feeds)

    # 更新
    new_name = '测试源-更新'
    r = s.put(f"{base}/user/{user}/feeds/{feed_id}", json={"feed_name": new_name, "feed_url": valid_url})
    assert r.status_code == 200

    # 统计
    r = s.get(f"{base}/api/user/{user}/feeds/stats")
    assert r.status_code == 200
    stats = r.json()
    assert 'overview' in stats and 'feeds' in stats

    # 删除
    r = s.delete(f"{base}/user/{user}/feeds/{feed_id}")
    assert r.status_code == 200
    r = s.get(f"{base}/user/{user}/feeds")
    assert all(f.get('id') != feed_id for f in r.json().get('feeds', []))

