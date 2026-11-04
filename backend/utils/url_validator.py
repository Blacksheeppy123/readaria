"""
URL 验证与归一化工具
防止 SSRF 攻击和恶意 URL 注入
"""
from urllib.parse import urlparse, urlunparse
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class URLValidator:
    """URL 验证器"""

    def __init__(self, allowed_schemes: list[str], allowed_rsshub_hosts: list[str]):
        """
        初始化 URL 验证器

        Args:
            allowed_schemes: 允许的协议列表，如 ['http', 'https']
            allowed_rsshub_hosts: 允许的 RSSHub 主机列表
        """
        self.allowed_schemes = [s.lower() for s in allowed_schemes]
        self.allowed_rsshub_hosts = [h.lower() for h in allowed_rsshub_hosts]

    def normalize_url(self, url: str) -> str:
        """
        归一化 URL

        操作:
        1. 转换为小写（主机名部分）
        2. 移除尾部斜杠
        3. 移除默认端口 (80/443)
        4. 去除 URL 片段 (#xxx)

        Args:
            url: 原始 URL

        Returns:
            归一化后的 URL
        """
        try:
            parsed = urlparse(url.strip())

            # 标准化协议和主机名
            scheme = parsed.scheme.lower()
            netloc = parsed.netloc.lower()

            # 移除默认端口
            if netloc.endswith(':80') and scheme == 'http':
                netloc = netloc[:-3]
            elif netloc.endswith(':443') and scheme == 'https':
                netloc = netloc[:-4]

            # 移除尾部斜杠（路径部分）
            path = parsed.path.rstrip('/') if parsed.path != '/' else parsed.path

            # 重组 URL（不包含 fragment）
            normalized = urlunparse((
                scheme,
                netloc,
                path,
                parsed.params,
                parsed.query,
                ''  # 移除 fragment
            ))

            return normalized

        except Exception as e:
            logger.error(f"URL 归一化失败: {url}, 错误: {e}")
            return url

    def validate_url(self, url: str, check_rsshub_host: bool = False) -> tuple[bool, str]:
        """
        验证 URL 是否安全

        Args:
            url: 待验证的 URL
            check_rsshub_host: 是否检查 RSSHub 主机白名单

        Returns:
            (是否有效, 错误消息)
        """
        if not url or not url.strip():
            return False, "URL 不能为空"

        try:
            parsed = urlparse(url)

            # 1. 检查协议
            if parsed.scheme.lower() not in self.allowed_schemes:
                return False, f"不允许的协议: {parsed.scheme}。仅支持: {', '.join(self.allowed_schemes)}"

            # 2. 检查主机名
            if not parsed.netloc:
                return False, "缺少主机名"

            # 3. 阻止内网地址（防止 SSRF）
            hostname = parsed.hostname
            if hostname:
                hostname_lower = hostname.lower()

                # 3a. 阻止常见的危险主机名（精确匹配）
                dangerous_hosts = {
                    'localhost', '127.0.0.1', '0.0.0.0',
                    '::1', '::ffff:127.0.0.1',
                    'metadata.google.internal',  # GCP 元数据服务
                    '169.254.169.254',  # AWS/Azure/腾讯云元数据服务
                }

                if hostname_lower in dangerous_hosts:
                    return False, f"不允许访问内网地址: {hostname}"

                # 3b. 阻止内网 IP 段（通过 DNS 解析校验）
                # 先尝试按 IP 地址解析
                import ipaddress
                try:
                    ip = ipaddress.ip_address(hostname_lower)
                    if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                        return False, f"不允许访问内网地址: {hostname}"
                except ValueError:
                    # 不是 IP 地址，是域名 — 尝试 DNS 解析
                    import socket
                    try:
                        addrinfos = socket.getaddrinfo(hostname, None)
                        for addrinfo in addrinfos:
                            resolved_ip = addrinfo[4][0]
                            ip = ipaddress.ip_address(resolved_ip)
                            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                                return False, f"不允许访问内网地址: {hostname} ({resolved_ip})"
                    except (socket.gaierror, ValueError):
                        pass  # DNS 解析失败，继续后续校验

                # 3c. 阻止内网 IP 段（基于字符串前缀的兜底校验）
                if hostname_lower.startswith('10.') or \
                   hostname_lower.startswith('192.168.'):
                    return False, f"不允许访问内网地址: {hostname}"
                if hostname_lower.startswith('172.'):
                    parts = hostname_lower.split('.')
                    if len(parts) >= 2:
                        try:
                            second_octet = int(parts[1])
                            if 16 <= second_octet <= 31:
                                return False, f"不允许访问内网地址: {hostname}"
                        except ValueError:
                            pass

                # 4. 检查 RSSHub 主机白名单（精确匹配，fail-closed）
                # 当调用方要求检查 RSSHub 白名单时，hostname 必须严格在白名单中
                if check_rsshub_host:
                    allowed_hosts_set = {h.lower() for h in self.allowed_rsshub_hosts}
                    if hostname_lower not in allowed_hosts_set:
                        return False, f"RSSHub 主机不在白名单中: {hostname}。允许的主机: {', '.join(self.allowed_rsshub_hosts)}"

            # 5. 检查危险字符
            dangerous_chars = ['<', '>', '"', "'", '`']
            for char in dangerous_chars:
                if char in url:
                    return False, f"URL 包含危险字符: {char}"

            return True, ""

        except Exception as e:
            logger.error(f"URL 验证失败: {url}, 错误: {e}")
            return False, f"URL 格式错误: {str(e)}"

    def validate_and_normalize(self, url: str, check_rsshub_host: bool = False) -> tuple[bool, str, str]:
        """
        验证并归一化 URL

        Args:
            url: 原始 URL
            check_rsshub_host: 是否检查 RSSHub 主机白名单

        Returns:
            (是否有效, 归一化后的 URL 或空字符串, 错误消息)
        """
        is_valid, error_msg = self.validate_url(url, check_rsshub_host)
        if not is_valid:
            return False, "", error_msg

        normalized_url = self.normalize_url(url)
        return True, normalized_url, ""


def create_url_validator_from_settings(settings) -> URLValidator:
    """
    从配置创建 URL 验证器

    Args:
        settings: Settings 实例

    Returns:
        URLValidator 实例
    """
    return URLValidator(
        allowed_schemes=settings.allowed_url_schemes_list,
        allowed_rsshub_hosts=settings.rsshub_allowed_hosts_list
    )


# 使用示例
if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)

    validator = URLValidator(
        allowed_schemes=['http', 'https'],
        allowed_rsshub_hosts=['rsshub.app', 'localhost', '127.0.0.1']
    )

    test_urls = [
        ("https://rsshub.app/bilibili/user/dynamic/731771", True, True),
        ("http://192.168.1.1/admin", False, False),  # 内网地址
        ("https://metadata.google.internal/", False, False),  # 元数据服务
        ("ftp://example.com/feed.xml", False, False),  # 非法协议
        ("https://rsshub.malicious.com/test", True, False),  # 非白名单 RSSHub
        ("https://example.com/feed.xml", True, True),
        ("https://example.com/feed<script>alert('XSS')</script>", False, False),  # 危险字符
    ]

    print("=== URL 验证测试 ===\n")
    for url, check_rsshub, expected in test_urls:
        is_valid, error_msg = validator.validate_url(url, check_rsshub_host=check_rsshub)
        status = "✅" if is_valid == expected else "❌"
        print(f"{status} {url}")
        if not is_valid:
            print(f"   错误: {error_msg}")
        elif check_rsshub:
            print(f"   通过 (RSSHub 白名单检查)")
        print()
