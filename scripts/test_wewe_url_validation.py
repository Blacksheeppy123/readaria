#!/usr/bin/env python3
"""
测试 WeWe RSS URL 验证
"""
import sys
import os

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from backend.utils.url_validator import URLValidator

def test_wewe_rss_urls():
    """测试 WeWe RSS URL 的验证逻辑"""

    validator = URLValidator(
        allowed_schemes=['http', 'https'],
        allowed_rsshub_hosts=['rsshub.app', 'localhost', '127.0.0.1']
    )

    test_cases = [
        # (URL, 是否应该通过, 描述)
        ("http://127.0.0.1:4000/feeds/MP_WXS_2392306830.atom", True, "WeWe RSS localhost URL"),
        ("http://localhost:4000/feeds/MP_WXS_123456.atom", True, "WeWe RSS localhost with domain"),
        ("http://127.0.0.1:4000/api/status", True, "WeWe RSS API endpoint"),
        ("http://192.168.1.100:4000/feeds/test.atom", True, "WeWe RSS 内网 IP"),
        ("http://192.168.1.1/admin", False, "非 WeWe RSS 内网地址"),
        ("https://rsshub.app/bilibili/user/123", True, "RSSHub URL (应该保持通过)"),
        ("http://localhost:1200/bilibili/user/123", True, "RSSHub localhost (应该保持通过)"),
        ("http://metadata.google.internal/", False, "危险的元数据服务"),
        ("http://127.0.0.1:8080/feeds/test.atom", True, "包含 /feeds/ 路径的 localhost"),
    ]

    print("=" * 70)
    print("WeWe RSS URL 验证测试")
    print("=" * 70)

    passed = 0
    failed = 0

    for url, should_pass, description in test_cases:
        is_valid, error_msg = validator.validate_url(url, check_rsshub_host=False)

        # 判断测试是否通过
        test_passed = is_valid == should_pass

        if test_passed:
            status = "✅ PASS"
            passed += 1
        else:
            status = "❌ FAIL"
            failed += 1

        print(f"\n{status} | {description}")
        print(f"  URL: {url}")
        print(f"  预期: {'通过' if should_pass else '拒绝'} | 实际: {'通过' if is_valid else '拒绝'}")

        if not is_valid:
            print(f"  错误信息: {error_msg}")

    print("\n" + "=" * 70)
    print(f"测试结果: {passed} 通过, {failed} 失败")
    print("=" * 70)

    return failed == 0


if __name__ == '__main__':
    success = test_wewe_rss_urls()
    sys.exit(0 if success else 1)
