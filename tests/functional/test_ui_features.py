"""
RSS管理UI功能测试
使用requests测试UI相关功能
"""
import pytest
import requests
from bs4 import BeautifulSoup


@pytest.mark.functional
class TestUIFeatures:
    """UI功能测试"""

    def test_main_page_loads(self, api_client, api_base_url, wait_for_server):
        """测试主页面加载"""
        response = api_client.get(f"{api_base_url}/")
        assert response.status_code == 200

        # 检查HTML内容
        soup = BeautifulSoup(response.text, 'html.parser')
        # 现阶段后端返回占位页或前端 dev server 未由后端托管，只校验标题包含关键字
        title = soup.find('title').text if soup.find('title') else ''
        assert 'Readaria RSS Manager' in title

    @pytest.mark.xfail(strict=False, reason="后端未托管旧版静态文件，使用 SPA 开发服务器")
    def test_static_files_loading(self, api_client, api_base_url):
        """测试静态文件加载"""
        static_files = [
            "/static/css/main.css",
            "/static/js/app.js",
            "/static/js/feeds.js",
            "/static/js/articles.js"
        ]

        for file_path in static_files:
            response = api_client.get(f"{api_base_url}{file_path}")
            assert response.status_code == 200, f"静态文件 {file_path} 加载失败"

    @pytest.mark.xfail(strict=False, reason="旧版静态 UI 结构已废弃")
    def test_ui_structure(self, api_client, api_base_url):
        """测试UI结构完整性"""
        response = api_client.get(f"{api_base_url}/")
        soup = BeautifulSoup(response.text, 'html.parser')

        # 检查主要UI元素
        assert soup.find('header', class_='header'), "缺少头部"
        assert soup.find('aside', class_='sidebar'), "缺少侧边栏"
        assert soup.find('section', class_='content-area'), "缺少内容区域"

        # 检查导航菜单
        nav_items = soup.find_all('a', class_='nav-item')
        assert len(nav_items) == 3, "导航菜单项数量不正确"

        nav_texts = [item.find('span').text for item in nav_items]
        expected_navs = ['订阅管理', '文章浏览', '统计信息']
        for expected in expected_navs:
            assert expected in nav_texts, f"缺少导航项: {expected}"

    @pytest.mark.xfail(strict=False, reason="旧版静态 UI 模态结构已废弃")
    def test_modal_structure(self, api_client, api_base_url):
        """测试模态框结构"""
        response = api_client.get(f"{api_base_url}/")
        soup = BeautifulSoup(response.text, 'html.parser')

        # 检查添加订阅源模态框
        add_modal = soup.find('div', id='add-feed-modal')
        assert add_modal, "缺少添加订阅源模态框"

        # 检查删除确认模态框
        delete_modal = soup.find('div', id='delete-confirm-modal')
        assert delete_modal, "缺少删除确认模态框"

        # 检查表单元素
        form = add_modal.find('form', id='feed-form')
        assert form, "缺少订阅源表单"

        # 检查必要的输入字段
        feed_name_input = form.find('input', id='feed-name')
        feed_url_input = form.find('input', id='feed-url')
        assert feed_name_input, "缺少订阅源名称输入框"
        assert feed_url_input, "缺少订阅源URL输入框"


@pytest.mark.functional
class TestFeedURLValidation:
    """Feed URL验证功能测试"""

    def test_url_validation_api_integration(self, api_client, api_base_url, test_feed_data):
        """测试URL验证API集成"""
        test_cases = [
            {
                "name": "有效RSS源",
                "url": test_feed_data["valid_feed"]["feed_url"],
                "expected_status": "success"
            },
            {
                "name": "B站源（智能路由）",
                "url": test_feed_data["bilibili_feed"]["feed_url"],
                "expected_status": "success"
            },
            {
                "name": "问题源",
                "url": test_feed_data["problematic_feed"]["feed_url"],
                "expected_problematic": True
            }
        ]

        for test_case in test_cases:
            test_data = {"feed_url": test_case["url"]}
            response = api_client.post(f"{api_base_url}/api/feeds/test", json=test_data)

            assert response.status_code == 200, f"URL验证失败: {test_case['name']}"

            data = response.json()

            if "expected_status" in test_case:
                # 公共实例可能 429/403，视为 warning；本地/可用时为 success
                assert data["status"] in (test_case["expected_status"], "warning"), \
                    f"状态不符合预期: {test_case['name']} -> {data['status']}"

            if test_case.get("expected_problematic"):
                assert data["is_problematic"] is True, \
                    f"未检测到问题源: {test_case['name']}"

            print(f"✅ {test_case['name']}: {data['status']} - {data['message']}")


@pytest.mark.functional
def test_complete_user_workflow(api_client, api_base_url, test_user_id, test_feed_data, clean_user_feeds):
    """测试完整用户工作流程"""
    print("\n🚀 开始完整用户工作流程测试")

    # 1. 访问主页
    response = api_client.get(f"{api_base_url}/")
    assert response.status_code == 200
    print("✅ 1. 主页访问成功")

    # 2. 获取空的订阅源列表
    response = api_client.get(f"{api_base_url}/user/{test_user_id}/feeds")
    assert response.status_code == 200
    assert len(response.json()["feeds"]) == 0
    print("✅ 2. 空订阅源列表获取成功")

    # 3. 测试URL有效性
    test_data = {"feed_url": test_feed_data["valid_feed"]["feed_url"]}
    response = api_client.post(f"{api_base_url}/api/feeds/test", json=test_data)
    assert response.status_code == 200
    assert response.json().get("status") in ("success", "warning")
    print("✅ 3. URL有效性验证成功")

    # 4. 添加订阅源
    feed_data = test_feed_data["valid_feed"]
    response = api_client.post(f"{api_base_url}/user/{test_user_id}/feeds", json=feed_data)
    assert response.status_code == 200
    feed_id = response.json()["feed_id"]
    print(f"✅ 4. 订阅源添加成功 (ID: {feed_id})")

    # 5. 验证订阅源出现在列表中
    response = api_client.get(f"{api_base_url}/user/{test_user_id}/feeds")
    assert response.status_code == 200
    feeds = response.json()["feeds"]
    assert len(feeds) == 1
    assert feeds[0]["feed_name"] == feed_data["feed_name"]
    print("✅ 5. 订阅源列表更新成功")

    # 6. 获取统计信息
    response = api_client.get(f"{api_base_url}/api/user/{test_user_id}/feeds/stats")
    assert response.status_code == 200
    stats = response.json()
    assert stats["overview"]["total"] == 1
    print("✅ 6. 统计信息获取成功")

    # 7. 刷新订阅源
    response = api_client.post(f"{api_base_url}/api/user/{test_user_id}/feeds/refresh")
    assert response.status_code == 200
    refresh_result = response.json()
    assert refresh_result.get("status") in ("completed", "accepted", "success")
    print(f"✅ 7. 订阅源刷新成功 ({refresh_result['success_count']}/{refresh_result['total_feeds']})")

    # 8. 获取文章列表
    response = api_client.get(f"{api_base_url}/api/user/{test_user_id}/feeds/articles")
    assert response.status_code == 200
    articles = response.json()
    assert "articles" in articles
    print("✅ 8. 文章列表获取成功")

    # 9. 删除订阅源
    response = api_client.delete(f"{api_base_url}/user/{test_user_id}/feeds/{feed_id}")
    assert response.status_code == 200
    print("✅ 9. 订阅源删除成功")

    # 10. 验证删除
    response = api_client.get(f"{api_base_url}/user/{test_user_id}/feeds")
    assert response.status_code == 200
    assert len(response.json()["feeds"]) == 0
    print("✅ 10. 删除验证成功")

    print("🎉 完整用户工作流程测试通过！")
