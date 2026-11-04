"""
API 回归 - 认证链路
"""
import os
import pytest
import requests


@pytest.mark.api
@pytest.mark.smoke
@pytest.mark.auth
@pytest.mark.e2e  # 需要完整的 API 服务器
@pytest.mark.external  # 需要外部服务
def test_login_me_logout(wait_for_server):
    base = os.getenv('TEST_BASE_URL', 'http://localhost:8000')
    username = os.getenv('TEST_USERNAME', 'test-user')
    password = os.getenv('TEST_PASSWORD', 'test123')

    s = requests.Session()
    s.headers.update({'Content-Type': 'application/json'})

    # 登录
    r = s.post(f"{base}/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, f"login failed: {r.text}"
    data = r.json()
    assert data.get('access_token')
    token = data['access_token']
    s.headers['Authorization'] = f"Bearer {token}"

    # /me
    r = s.get(f"{base}/api/auth/me")
    assert r.status_code == 200
    me = r.json()
    assert me.get('username') == username

    # 登出
    r = s.post(f"{base}/api/auth/logout")
    assert r.status_code == 200

