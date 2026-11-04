#!/usr/bin/env python3
"""
RSS管理UI快速测试运行器
MVP功能验证
"""

import subprocess
import sys
import os
import time
import argparse
import requests

def check_server():
    """检查服务器是否运行"""
    try:
        response = requests.get("http://localhost:8000/", timeout=5)
        return response.status_code == 200
    except:
        return False

def run_tests():
    """运行测试套件"""
    parser = argparse.ArgumentParser(description='Run Jasmine test suites')
    parser.add_argument('--base-url', default=os.getenv('TEST_BASE_URL', 'http://localhost:8000'))
    parser.add_argument('--user', default=os.getenv('TEST_USER_ID', 'test-user'))
    parser.add_argument('--smoke-only', action='store_true')
    args = parser.parse_args()

    os.environ['TEST_BASE_URL'] = args.base_url
    os.environ['TEST_USER_ID'] = args.user
    os.environ['TEST_USERNAME'] = os.getenv('TEST_USERNAME', args.user)
    os.environ['TEST_PASSWORD'] = os.getenv('TEST_PASSWORD', 'test123')

    print("🧪 RSS管理UI MVP功能测试")
    print("=" * 50)

    # 检查服务器状态
    if not check_server():
        print("❌ 错误: 服务器未运行")
        print("请先启动服务器: python backend/api/main.py")
        return False

    print("✅ 服务器运行正常")

    # 切换到项目根目录（scripts 的上一级）
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.chdir(project_root)

    # 安装测试依赖
    print("\n📦 安装测试依赖...")
    try:
        subprocess.run([
            sys.executable, "-m", "pip", "install", "-q",
            "pytest", "pytest-asyncio", "pytest-html", "requests", "beautifulsoup4"
        ], check=True)
        print("✅ 测试依赖安装成功")
    except subprocess.CalledProcessError:
        print("❌ 测试依赖安装失败")
        return False

    # 运行测试
    print("\n🚀 运行测试套件...")

    test_commands = []
    test_commands.append({
        "name": "烟雾测试 (快速验证)",
        "cmd": [sys.executable, "-m", "pytest", "-v", "-m", "smoke", "tests/"]
    })
    if not args.smoke_only:
        test_commands.append({
            "name": "API功能测试",
            "cmd": [sys.executable, "-m", "pytest", "-v", "-m", "api", "tests/api/"]
        })
        test_commands.append({
            "name": "UI功能测试",
            "cmd": [sys.executable, "-m", "pytest", "-v", "-m", "functional", "tests/functional/"]
        })

    results = []

    for test_group in test_commands:
        print(f"\n📋 运行: {test_group['name']}")
        print("-" * 40)

        try:
            result = subprocess.run(
                test_group["cmd"],
                capture_output=True,
                text=True,
                timeout=300  # 5分钟超时
            )

            if result.returncode == 0:
                print(f"✅ {test_group['name']} - 通过")
                results.append((test_group['name'], True, ""))
            else:
                print(f"❌ {test_group['name']} - 失败")
                results.append((test_group['name'], False, result.stdout + result.stderr))
                print("错误输出:")
                print(result.stdout)
                print(result.stderr)

        except subprocess.TimeoutExpired:
            print(f"⏰ {test_group['name']} - 超时")
            results.append((test_group['name'], False, "测试超时"))

        except Exception as e:
            print(f"💥 {test_group['name']} - 异常: {e}")
            results.append((test_group['name'], False, str(e)))

    # 生成测试报告
    print("\n" + "=" * 50)
    print("📊 测试结果汇总")
    print("=" * 50)

    passed = 0
    total = len(results)

    for name, success, error in results:
        status = "✅ 通过" if success else "❌ 失败"
        print(f"{status} - {name}")
        if success:
            passed += 1
        elif error and len(error) < 200:
            print(f"   错误: {error}")

    print(f"\n🎯 总计: {passed}/{total} 测试组通过")

    if passed == total:
        print("🎉 所有测试通过！RSS管理UI MVP功能验证成功！")
        return True
    else:
        print("⚠️  部分测试失败，请检查上述错误信息")
        return False

if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
