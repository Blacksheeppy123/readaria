"""
RSS管理API核心功能测试
快速验证MVP功能
"""
import pytest
import requests


@pytest.mark.api
@pytest.mark.smoke
@pytest.mark.rss
class TestRSSAPI:
    """RSS API核心功能测试"""

    @pytest.mark.e2e
    @pytest.mark.external
    def test_server_health(self, api_client, api_base_url, wait_for_server):
        """测试服务器健康状态"""
        response = api_client.get(f"{api_base_url}/")
        assert response.status_code == 200
        assert "Readaria RSS Manager" in response.text

    @pytest.mark.e2e
    @pytest.mark.external
    def test_get_empty_feeds_list(self, api_client_auth, api_base_url, test_user_id, clean_user_feeds):
        """测试获取空的订阅源列表"""
        response = api_client_auth.get(f"{api_base_url}/user/{test_user_id}/feeds")
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "success"
        assert data["feeds"] == []

    @pytest.mark.external  # 需要 RSSHub
    def test_feed_url_validation_valid(self, api_client, api_base_url, test_feed_data):
        """测试有效RSS URL验证"""
        test_data = {"feed_url": test_feed_data["valid_feed"]["feed_url"]}

        response = api_client.post(f"{api_base_url}/api/feeds/test", json=test_data)
        assert response.status_code == 200

        data = response.json()
        # 公共实例可能返回 429/403，服务端会降级 status=warning
        assert data["status"] in ("success", "warning")
        assert isinstance(data.get("optimal_url"), str)
        assert "optimal_url" in data

    @pytest.mark.external  # 需要 RSSHub
    def test_feed_url_validation_bilibili(self, api_client, api_base_url, test_feed_data):
        """测试B站URL智能路由"""
        test_data = {"feed_url": test_feed_data["bilibili_feed"]["feed_url"]}

        response = api_client.post(f"{api_base_url}/api/feeds/test", json=test_data)
        assert response.status_code == 200

        data = response.json()
        assert data["status"] in ("success", "warning")
        # 2026-05-18: 本地 RSSHub 已移除，验证仍使用公共 RSSHub
        assert "rsshub.app" in data["optimal_url"]

    def test_feed_url_validation_problematic(self, api_client, api_base_url, test_feed_data):
        """测试问题源检测"""
        test_data = {"feed_url": test_feed_data["problematic_feed"]["feed_url"]}

        response = api_client.post(f"{api_base_url}/api/feeds/test", json=test_data)
        assert response.status_code == 200

        data = response.json()
        # 可能成功或失败，但应该标记为有问题
        assert data["is_problematic"] is True
        assert len(data["issues"]) > 0

    def test_add_valid_feed(self, api_client_auth, api_base_url, test_user_id, test_feed_data, clean_user_feeds):
        """测试添加有效订阅源"""
        feed_data = test_feed_data["valid_feed"]

        response = api_client_auth.post(f"{api_base_url}/user/{test_user_id}/feeds", json=feed_data)
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "success"
        assert "feed_id" in data

        # 验证添加成功 - 获取订阅源列表
        response = api_client_auth.get(f"{api_base_url}/user/{test_user_id}/feeds")
        assert response.status_code == 200

        data = response.json()
        assert len(data["feeds"]) == 1
        assert data["feeds"][0]["feed_name"] == feed_data["feed_name"]

    def test_add_feed_missing_data(self, api_client_auth, api_base_url, test_user_id):
        """测试添加订阅源时缺少必要数据"""
        # 缺少feed_url
        incomplete_data = {"feed_name": "测试源"}

        response = api_client_auth.post(f"{api_base_url}/user/{test_user_id}/feeds", json=incomplete_data)
        assert response.status_code == 400

        data = response.json()
        assert "feed_url 必填" in data["detail"]

    def test_get_feeds_stats(self, api_client_auth, api_base_url, test_user_id, test_feed_data, clean_user_feeds):
        """测试获取订阅源统计信息"""
        # 先添加一个订阅源
        feed_data = test_feed_data["valid_feed"]
        response = api_client_auth.post(f"{api_base_url}/user/{test_user_id}/feeds", json=feed_data)
        assert response.status_code == 200

        # 获取统计信息
        response = api_client_auth.get(f"{api_base_url}/api/user/{test_user_id}/feeds/stats")
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "success"
        assert "overview" in data
        assert "feeds" in data

        # 验证统计数据
        overview = data["overview"]
        assert overview["total"] == 1
        assert overview["rsshub_feeds"] == 1

    def test_get_articles_list(self, api_client_auth, api_base_url, test_user_id):
        """测试获取文章列表"""
        response = api_client_auth.get(f"{api_base_url}/api/user/{test_user_id}/feeds/articles")
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "success"
        assert "articles" in data
        assert "pagination" in data


@pytest.mark.api
@pytest.mark.functional
class TestRSSFeedManagement:
    """RSS订阅源管理功能测试"""

    def test_full_crud_workflow(self, api_client_auth, api_base_url, test_user_id, test_feed_data, clean_user_feeds):
        """测试完整的CRUD工作流程"""
        feed_data = test_feed_data["valid_feed"]

        # 1. 创建订阅源
        response = api_client_auth.post(f"{api_base_url}/user/{test_user_id}/feeds", json=feed_data)
        assert response.status_code == 200
        feed_id = response.json()["feed_id"]

        # 2. 读取订阅源
        response = api_client_auth.get(f"{api_base_url}/user/{test_user_id}/feeds")
        assert response.status_code == 200
        feeds = response.json()["feeds"]
        assert len(feeds) == 1
        assert feeds[0]["id"] == feed_id

        # 3. 更新订阅源
        updated_data = {
            "feed_name": "V2EX热门话题（已更新）",
            "feed_url": feed_data["feed_url"]
        }
        response = api_client_auth.put(f"{api_base_url}/user/{test_user_id}/feeds/{feed_id}", json=updated_data)
        assert response.status_code == 200

        # 验证更新
        response = api_client_auth.get(f"{api_base_url}/user/{test_user_id}/feeds")
        feeds = response.json()["feeds"]
        assert feeds[0]["feed_name"] == updated_data["feed_name"]

        # 4. 删除订阅源
        response = api_client_auth.delete(f"{api_base_url}/user/{test_user_id}/feeds/{feed_id}")
        assert response.status_code == 200

        # 验证删除
        response = api_client_auth.get(f"{api_base_url}/user/{test_user_id}/feeds")
        feeds = response.json()["feeds"]
        assert len(feeds) == 0

    def test_refresh_feeds(self, api_client_auth, api_base_url, test_user_id, test_feed_data, clean_user_feeds):
        """测试刷新订阅源功能"""
        # 先添加一个有效的订阅源
        feed_data = test_feed_data["valid_feed"]
        response = api_client_auth.post(f"{api_base_url}/user/{test_user_id}/feeds", json=feed_data)
        assert response.status_code == 200

        # 刷新所有订阅源
        response = api_client_auth.post(f"{api_base_url}/api/user/{test_user_id}/feeds/refresh")
        assert response.status_code == 200

        data = response.json()
        # Week3 切换为异步模式，可能返回 accepted；也可能completed/success
        assert data.get("status") in ("accepted", "completed", "success")

    def test_delete_nonexistent_feed(self, api_client_auth, api_base_url, test_user_id):
        """测试删除不存在的订阅源"""
        fake_feed_id = 99999
        response = api_client_auth.delete(f"{api_base_url}/user/{test_user_id}/feeds/{fake_feed_id}")
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "not_found"


@pytest.mark.api
@pytest.mark.smoke
def test_api_endpoints_availability(api_client_auth, api_base_url, wait_for_server):
    """快速烟雾测试 - 验证所有关键API端点可访问"""
    user_id = "test-user"

    # Root endpoint doesn't require auth
    response = api_client_auth.get(f"{api_base_url}/")
    assert response.status_code == 200

    # Authenticated endpoints
    endpoints = [
        ("GET", f"/user/{user_id}/feeds"),
        ("GET", f"/api/user/{user_id}/feeds/stats"),
        ("GET", f"/api/user/{user_id}/feeds/articles"),
    ]

    for method, endpoint in endpoints:
        if method == "GET":
            response = api_client_auth.get(f"{api_base_url}{endpoint}")
            assert response.status_code in [200, 400], f"端点 {endpoint} 不可访问"

    print("✅ 所有关键API端点可访问")
