"""
Feed URL 管理器 - 智能选择本地/公共RSSHub
"""
import re
from typing import Optional, Dict, List
from urllib.parse import urlparse
import logging

logger = logging.getLogger(__name__)

class FeedURLManager:
    """Feed URL管理器，智能路由到本地或公共RSSHub"""

    # 需要认证的RSSHub路由（建议使用本地RSSHub）
    REQUIRES_AUTH = [
        'bilibili',
        'xiaohongshu',
        'twitter',
        'youtube',
        'instagram',
        'pixiv',
        'weibo',
        'wechat'  # Week 5: 微信公众号需要 Cookie 认证
    ]

    # 已知有问题的路由（需要特殊处理）
    PROBLEMATIC_ROUTES = {
        'xiaohongshu': {
            'issues': ['strict_anti_crawler', 'puppeteer_required', 'frequent_timeouts'],
            'fallback_strategy': 'skip_on_local_fail',
            'retry_count': 1  # 减少重试次数
        },
        'pixiv': {
            'issues': ['token_required', 'public_instances_blocked'],
            'fallback_strategy': 'skip_completely',
            'retry_count': 0
        }
    }

    # 不需要认证的路由（可以使用公共RSSHub）
    NO_AUTH_REQUIRED = [
        'v2ex',
        'github',
        'zhihu',  # 部分路由可能需要
        'douban',
        'juejin'
    ]

    # 公共RSSHub实例列表（按优先级）
    PUBLIC_RSSHUB_INSTANCES = [
        'https://rsshub.app',
        'https://rsshub.moeyy.cn',
        'https://rsshub.uneasy.win',
        'https://yangzhi.app'
    ]

    def __init__(self, local_rsshub_url: str = 'http://localhost:1200',
                 prefer_local: bool = False,
                 force_local: bool = False,
                 platform_routing: Optional[Dict[str, str]] = None):
        """
        初始化Feed URL管理器

        2026-05-18: 本地 RSSHub 已移除，force_local / prefer_local / platform_routing
        中的 local 策略均被忽略，所有 RSSHub 源直接使用公共实例。
        """
        self.local_rsshub_url = local_rsshub_url.rstrip('/')
        # 本地 RSSHub 已退役，强制关闭本地模式
        if force_local or prefer_local:
            logger.warning(
                "force_local/prefer_local 已废弃（本地 RSSHub 已移除），"
                "所有源将使用公共 RSSHub 实例"
            )
        self.prefer_local = False
        self.force_local = False
        self.platform_routing = platform_routing or {}

        # Week 5: WeWe RSS 服务配置（微信公众号订阅服务）
        self.wewe_rss_url = 'http://localhost:4000'  # 可从环境变量读取

    def parse_rsshub_route(self, url: str) -> Optional[Dict[str, str]]:
        """
        解析RSSHub URL，提取路由信息

        Args:
            url: RSS feed URL

        Returns:
            包含host, platform, route的字典，如果不是RSSHub URL则返回None
        """
        try:
            parsed = urlparse(url)

            # 检查是否是RSSHub URL
            if 'rsshub' not in parsed.netloc.lower():
                return None

            # 提取路径部分
            path = parsed.path.lstrip('/')
            if not path:
                return None

            # 解析路由：/platform/route/params
            parts = path.split('/', 1)
            platform = parts[0]
            route = parts[1] if len(parts) > 1 else ''

            return {
                'host': f"{parsed.scheme}://{parsed.netloc}",
                'platform': platform,
                'route': route,
                'full_path': path
            }
        except Exception as e:
            logger.error(f"解析RSSHub URL失败: {url}, 错误: {e}")
            return None

    def requires_authentication(self, platform: str) -> bool:
        """
        判断平台是否需要认证

        Args:
            platform: 平台名称（如bilibili, xiaohongshu等）

        Returns:
            是否需要认证
        """
        return platform.lower() in self.REQUIRES_AUTH

    def is_problematic_route(self, platform: str) -> Dict:
        """
        检查是否是已知问题路由
        """
        return self.PROBLEMATIC_ROUTES.get(platform.lower(), {})

    def should_skip_route(self, platform: str, failed_locally: bool = False) -> bool:
        """
        判断是否应该跳过某个路由
        """
        route_info = self.is_problematic_route(platform)
        if not route_info:
            return False

        strategy = route_info.get('fallback_strategy', '')

        if strategy == 'skip_completely':
            return True
        elif strategy == 'skip_on_local_fail' and failed_locally:
            return True

        return False

    # 2026-05-18: 已退役的本地 RSSHub hosts，需要 normalize 到公共实例
    RETIRED_LOCAL_HOSTS = {
        'localhost:1200', '127.0.0.1:1200', 'rsshub:1200',
        'rsshub.marlinworks.xyz', 'rsshub.marlinworks.xyz:1200',
    }

    def _is_retired_local_rsshub(self, url: str) -> bool:
        """检查是否使用了已退役的本地 RSSHub host"""
        try:
            parsed = urlparse(url)
            return parsed.netloc.lower() in self.RETIRED_LOCAL_HOSTS
        except Exception:
            return False

    def _normalize_retired_local(self, url: str) -> str:
        """将退役的本地 RSSHub URL normalize 到公共实例"""
        try:
            parsed = urlparse(url)
            # 保留路径和查询参数
            public_url = f"https://rsshub.app{parsed.path}"
            if parsed.query:
                public_url += f"?{parsed.query}"
            logger.info(f"Normalize retired local RSSHub: {url} -> {public_url}")
            return public_url
        except Exception as e:
            logger.warning(f"Normalize retired local RSSHub failed: {url}, error: {e}")
            return url

    def get_optimal_url(self, url: str, check_local_available: bool = False) -> str:
        """
        获取最优的Feed URL

        2026-05-18: 本地 RSSHub 已移除，所有 RSSHub 源直接使用公共实例。

        Args:
            url: 原始Feed URL
            check_local_available: 是否检查本地RSSHub可用性（已废弃）

        Returns:
            优化后的Feed URL
        """
        # 防御性处理：将退役的本地 RSSHub hosts normalize 到公共实例
        if self._is_retired_local_rsshub(url):
            return self._normalize_retired_local(url)

        # 如果不是RSSHub URL，直接返回
        route_info = self.parse_rsshub_route(url)
        if not route_info:
            return url

        # 本地 RSSHub 已移除，所有源直接使用公共 RSSHub
        return url

    def convert_to_local(self, url: str) -> str:
        """
        将RSSHub URL转换为本地RSSHub URL

        2026-05-18: 本地 RSSHub 已移除，此方法已废弃，直接返回公共实例 URL。
        """
        logger.warning("convert_to_local() 已废弃（本地 RSSHub 已移除），使用 convert_to_public()")
        return self.convert_to_public(url)

    def convert_to_public(self, url: str, instance_index: int = 0) -> str:
        """
        将RSSHub URL转换为公共RSSHub URL

        Args:
            url: 原始RSSHub URL
            instance_index: 公共实例索引

        Returns:
            公共RSSHub URL
        """
        route_info = self.parse_rsshub_route(url)
        if not route_info:
            return url

        # 选择公共实例
        if instance_index >= len(self.PUBLIC_RSSHUB_INSTANCES):
            instance_index = 0

        public_host = self.PUBLIC_RSSHUB_INSTANCES[instance_index]
        public_url = f"{public_host}/{route_info['full_path']}"
        logger.debug(f"转换URL: {url} -> {public_url}")
        return public_url

    def get_all_variants(self, url: str) -> List[str]:
        """
        获取一个URL的所有可用变体（本地+所有公共实例）

        Args:
            url: 原始Feed URL

        Returns:
            URL变体列表
        """
        route_info = self.parse_rsshub_route(url)
        if not route_info:
            return [url]

        # 2026-05-18: 本地 RSSHub 已移除，仅返回公共实例 URL
        variants = []
        for i in range(len(self.PUBLIC_RSSHUB_INSTANCES)):
            variants.append(self.convert_to_public(url, i))

        return variants

    def classify_feed_url(self, url: str) -> Dict[str, str]:
        """
        分类Feed URL类型

        Args:
            url: Feed URL

        Returns:
            包含分类信息的字典
        """
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower()

            # 判断是否是RSSHub URL
            route_info = self.parse_rsshub_route(url)
            if route_info:
                return {
                    'type': 'rsshub',
                    'platform': route_info['platform'],
                    'requires_auth': self.requires_authentication(route_info['platform']),
                    'domain': domain
                }

            # 判断是否是已知的第三方RSS服务
            if 'folo.is' in domain:
                return {
                    'type': 'third_party_rss',
                    'platform': 'twitter',  # folo.is 主要是Twitter RSS
                    'requires_auth': False,
                    'domain': domain,
                    'service': 'folo.is'
                }
            elif 'nitter' in domain:
                return {
                    'type': 'third_party_rss',
                    'platform': 'twitter',
                    'requires_auth': False,
                    'domain': domain,
                    'service': 'nitter'
                }
            elif any(feed_indicator in parsed.path for feed_indicator in ['/feed', '/rss', '.xml', '.atom']):
                return {
                    'type': 'direct_rss',
                    'platform': 'rss',
                    'requires_auth': False,
                    'domain': domain
                }
            else:
                return {
                    'type': 'unknown',
                    'platform': 'unknown',
                    'requires_auth': False,
                    'domain': domain
                }

        except Exception as e:
            logger.error(f"分类URL失败: {url}, 错误: {e}")
            return {
                'type': 'unknown',
                'platform': 'unknown',
                'requires_auth': False,
                'domain': ''
            }

    def analyze_feed_list(self, feed_urls: List[str]) -> Dict[str, any]:
        """
        分析一组feed URL，统计需要认证的数量

        Args:
            feed_urls: Feed URL列表

        Returns:
            分析结果字典
        """
        stats = {
            'total': len(feed_urls),
            'rsshub_feeds': 0,
            'direct_rss_feeds': 0,
            'third_party_rss_feeds': 0,
            'requires_auth': 0,
            'no_auth_required': 0,
            'platforms': {},
            'services': {},
            'recommendations': []
        }

        for url in feed_urls:
            classification = self.classify_feed_url(url)
            feed_type = classification['type']
            platform = classification['platform']

            # 统计类型
            if feed_type == 'rsshub':
                stats['rsshub_feeds'] += 1
            elif feed_type == 'third_party_rss':
                stats['third_party_rss_feeds'] += 1
                # 统计第三方服务
                service = classification.get('service', 'unknown')
                if service not in stats['services']:
                    stats['services'][service] = 0
                stats['services'][service] += 1
            elif feed_type == 'direct_rss':
                stats['direct_rss_feeds'] += 1

            # 统计平台
            if platform not in stats['platforms']:
                stats['platforms'][platform] = 0
            stats['platforms'][platform] += 1

            # 统计认证需求
            if classification['requires_auth']:
                stats['requires_auth'] += 1
            else:
                stats['no_auth_required'] += 1

        # 生成建议
        if stats['requires_auth'] > 0:
            stats['recommendations'].append(
                f"发现 {stats['requires_auth']} 个需要认证的源，建议配置本地RSSHub Cookie"
            )

            # 列出需要配置的平台
            auth_platforms = [p for p in stats['platforms'].keys()
                            if self.requires_authentication(p)]
            if auth_platforms:
                stats['recommendations'].append(
                    f"需要配置Cookie的平台: {', '.join(auth_platforms)}"
                )

        if stats['no_auth_required'] > 0:
            stats['recommendations'].append(
                f"有 {stats['no_auth_required']} 个源无需认证，可直接使用"
            )

        if stats['third_party_rss_feeds'] > 0:
            stats['recommendations'].append(
                f"发现 {stats['third_party_rss_feeds']} 个第三方RSS服务源"
            )

        return stats

    # ================== Week 5: 微信公众号链接解析 ==================

    @staticmethod
    def parse_wechat_link(url: str) -> Optional[Dict[str, str]]:
        """
        解析微信公众号链接，转换为 RSSHub 路由

        支持的链接格式：
        1. 文章链接: https://mp.weixin.qq.com/s/xxxxx
        2. 历史消息页:
           - https://mp.weixin.qq.com/mp/profile_ext?action=home&__biz=xxxxx
           - https://mp.weixin.qq.com/mp/author?action=show&__biz=xxxxx&author_id=...

        Args:
            url: 微信公众号链接

        Returns:
            包含 platform, biz_id, rsshub_route 的字典，如果无法解析则返回 None

        Examples:
            >>> manager = FeedURLManager()
            >>> result = manager.parse_wechat_link('https://mp.weixin.qq.com/s/abc123')
            >>> print(result)
            {'platform': 'wechat', 'biz_id': None, 'rsshub_route': None}

            >>> result = manager.parse_wechat_link('https://mp.weixin.qq.com/mp/profile_ext?action=home&__biz=MzU4MTc2NTc5NQ==')
            >>> print(result)
            {'platform': 'wechat', 'biz_id': 'MzU4MTc2NTc5NQ==', 'rsshub_route': 'https://rsshub.app/wechat/mp/msgalbum/MzU4MTc2NTc5NQ=='}
        """
        try:
            parsed = urlparse(url)

            # 检查是否是微信公众号域名
            if 'mp.weixin.qq.com' not in parsed.netloc:
                return None

            result = {
                'platform': 'wechat',
                'biz_id': None,
                'rsshub_route': None,
                'article_url': None
            }

            # 解析文章链接
            if '/s/' in parsed.path or '/s?' in parsed.path:
                # 这是文章链接，无法直接转换为订阅，需要用户提供 biz
                result['article_url'] = url
                logger.info(f"检测到微信文章链接: {url}")
                logger.info("提示: 文章链接无法直接订阅，请提供公众号历史消息页链接")
                return result

            # 解析历史消息页/作者页链接（包含 __biz 参数）
            if '/mp/profile_ext' in parsed.path or '/mp/author' in parsed.path:
                # 提取 __biz 参数
                from urllib.parse import parse_qs
                query_params = parse_qs(parsed.query)
                biz_id = query_params.get('__biz', [None])[0]

                if biz_id:
                    result['biz_id'] = biz_id
                    # 构造 RSSHub 路由
                    # 使用 mp/msgalbum 路由（消息与消息集）
                    result['rsshub_route'] = f"https://rsshub.app/wechat/mp/msgalbum/{biz_id}"
                    logger.info(f"成功解析微信公众号链接: biz={biz_id}")
                    return result
                else:
                    logger.warning(f"微信公众号链接缺少 __biz 参数: {url}")
                    return result

            logger.warning(f"无法识别的微信公众号链接格式: {url}")
            return result

        except Exception as e:
            logger.error(f"解析微信链接失败: {url}, 错误: {e}")
            return None

    @staticmethod
    def is_wechat_link(url: str) -> bool:
        """
        判断是否为微信公众号链接

        Args:
            url: 待判断的 URL

        Returns:
            是否为微信公众号链接
        """
        try:
            parsed = urlparse(url)
            return 'mp.weixin.qq.com' in parsed.netloc
        except Exception:
            return False

    def convert_wechat_to_rsshub(self, url: str) -> Optional[str]:
        """
        将微信公众号链接转换为 RSSHub 订阅链接

        Args:
            url: 微信公众号链接

        Returns:
            RSSHub 订阅链接，如果无法转换则返回 None
        """
        parse_result = self.parse_wechat_link(url)

        if not parse_result or not parse_result.get('rsshub_route'):
            return None

        # 2026-05-18: 本地 RSSHub 已移除，直接返回公共 RSSHub URL
        return parse_result['rsshub_route']

    # ================== Week 5: WeWe RSS 微信公众号订阅服务 ==================

    @staticmethod
    def is_wewe_rss_feed(url: str) -> bool:
        """
        判断是否为 WeWe RSS 订阅源

        WeWe RSS 是基于微信读书的公众号 RSS 订阅服务

        支持的 URL 格式：
        - http://localhost:4000/feed/account_id
        - http://localhost:4000/feed/account_id.atom
        - http://localhost:4000/feed/account_id.rss
        - http://localhost:4000/feed/account_id.json
        - http://wewe-rss:4000/feed/...（Docker 内部）

        Args:
            url: 待判断的 URL

        Returns:
            是否为 WeWe RSS 订阅源

        Examples:
            >>> FeedURLManager.is_wewe_rss_feed('http://localhost:4000/feed/abc123')
            True
            >>> FeedURLManager.is_wewe_rss_feed('http://localhost:4000/feed/abc123.atom')
            True
            >>> FeedURLManager.is_wewe_rss_feed('https://rsshub.app/wechat/sogou/id')
            False
        """
        try:
            parsed = urlparse(url)

            # 检查端口和路径
            is_wewe_port = parsed.port == 4000 or ':4000' in parsed.netloc
            has_feed_path = '/feed/' in parsed.path

            # 检查主机名（支持 localhost 和 wewe-rss）
            is_wewe_host = (
                'localhost' in parsed.netloc or
                'wewe-rss' in parsed.netloc or
                '127.0.0.1' in parsed.netloc
            )

            result = is_wewe_host and is_wewe_port and has_feed_path

            if result:
                logger.info(f"检测到 WeWe RSS 订阅源: {url}")

            return result

        except Exception as e:
            logger.error(f"检测 WeWe RSS 订阅源失败: {url}, 错误: {e}")
            return False

    @staticmethod
    def is_wechat2rss_feed(url: str) -> bool:
        """
        判断是否为 wechat2rss 订阅源

        wechat2rss 是付费的微信公众号 RSS 订阅服务 (https://wechat2rss.xlab.app)

        支持的 URL 格式：
        - http://127.0.0.1:4001/feed/account_id.xml
        - http://localhost:4001/feed/account_id.xml
        - http://wechat2rss:8080/feed/...（Docker 内部）

        Args:
            url: 待判断的 URL

        Returns:
            是否为 wechat2rss 订阅源

        Examples:
            >>> FeedURLManager.is_wechat2rss_feed('http://127.0.0.1:4001/feed/3551111165.xml')
            True
            >>> FeedURLManager.is_wechat2rss_feed('http://localhost:4001/feed/abc123.xml')
            True
            >>> FeedURLManager.is_wechat2rss_feed('https://rsshub.app/wechat/sogou/id')
            False
        """
        try:
            parsed = urlparse(url)

            # 检查端口（外部 4001 或 Docker 内部 8080）
            is_wechat2rss_port = parsed.port in (4001, 8080) or ':4001' in parsed.netloc or ':8080' in parsed.netloc
            has_feed_path = '/feed/' in parsed.path

            # 检查主机名（支持 localhost、127.0.0.1 和 wechat2rss）
            is_wechat2rss_host = (
                'localhost' in parsed.netloc or
                'wechat2rss' in parsed.netloc or
                '127.0.0.1' in parsed.netloc
            )

            result = is_wechat2rss_host and is_wechat2rss_port and has_feed_path

            if result:
                logger.info(f"检测到 wechat2rss 订阅源: {url}")

            return result

        except Exception as e:
            logger.error(f"检测 wechat2rss 订阅源失败: {url}, 错误: {e}")
            return False


def create_feed_url_manager(mode: str = 'smart') -> FeedURLManager:
    """
    创建Feed URL管理器的工厂函数

    2026-05-18: 本地 RSSHub 已移除，'local' 和 'prefer_local' 模式已被废弃，
    所有模式均等效于 'public'（使用公共 RSSHub 实例）。

    Args:
        mode: 模式选择（已废弃，保留仅用于向后兼容）

    Returns:
        FeedURLManager实例
    """
    if mode in ('local', 'prefer_local'):
        logger.warning(f"create_feed_url_manager(mode='{mode}') 已废弃（本地 RSSHub 已移除），使用 public 模式")
    return FeedURLManager()


# 使用示例
if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)

    # 创建管理器
    manager = create_feed_url_manager('smart')

    # 测试URL
    test_urls = [
        'https://rsshub.app/bilibili/user/dynamic/731771',
        'https://rsshub.app/v2ex/topics/hot',
        'https://rsshub.app/xiaohongshu/user/5f3a9b9e00000000010035fe/notes',
        'https://lastweekin.ai/feed',
        'https://rsshub.app/youtube/user/@xiao_lin_shuo'
    ]

    print("=== Feed URL优化测试 ===\n")
    for url in test_urls:
        optimal = manager.get_optimal_url(url)
        print(f"原始: {url}")
        print(f"优化: {optimal}")
        print()

    # 分析feed列表
    print("=== Feed列表分析 ===\n")
    stats = manager.analyze_feed_list(test_urls)
    print(f"总计: {stats['total']} 个feed")
    print(f"RSSHub源: {stats['rsshub_feeds']} 个")
    print(f"直接RSS源: {stats['direct_rss_feeds']} 个")
    print(f"需要认证: {stats['requires_auth']} 个")
    print(f"无需认证: {stats['no_auth_required']} 个")
    print(f"\n平台分布:")
    for platform, count in stats['platforms'].items():
        auth = "🔐 需要认证" if manager.requires_authentication(platform) else "🔓 无需认证"
        print(f"  - {platform}: {count} 个 {auth}")
    print(f"\n建议:")
    for rec in stats['recommendations']:
        print(f"  • {rec}")
