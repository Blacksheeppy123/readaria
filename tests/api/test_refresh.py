"""
API 回归 - 刷新与状态/调度
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
def test_refresh_trigger_and_status(wait_for_server):
    base, s, user = _auth_session()

    # 若无订阅，先添加一个
    r = s.get(f"{base}/user/{user}/feeds")
    feeds = r.json().get('feeds', []) if r.status_code == 200 else []
    if not feeds:
        url = os.getenv('TEST_FEED_URL', 'https://rsshub.app/v2ex/topics/hot')
        s.post(f"{base}/user/{user}/feeds", json={"feed_name": "刷新-测试", "feed_url": url})

    # 异步触发刷新
    r = s.post(f"{base}/api/user/{user}/feeds/refresh", params={"async_mode": True})
    assert r.status_code == 200
    assert r.json().get('status') in ('accepted', 'completed', 'success')

    # 轮询状态（容忍无日志环境，返回结构即可）
    ok = False
    for _ in range(6):
        time.sleep(2)
        r = s.get(f"{base}/api/user/{user}/feeds/refresh/status")
        if r.status_code == 200:
            data = r.json()
            assert 'status' in data and 'results' in data
            ok = True
            break
    assert ok, '刷新状态接口不可达'

@pytest.mark.api
def test_scheduler_status(wait_for_server):
    base, s, _ = _auth_session()
    r = s.get(f"{base}/api/scheduler/status")
    assert r.status_code == 200
    assert r.json().get('scheduler', {}).get('running') in (True, False)

