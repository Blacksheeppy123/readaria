"""
URL 规范化与内容哈希工具
用于 cross-user content sharing 的去重逻辑
"""
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode
import hashlib
import logging

logger = logging.getLogger(__name__)

# 常见的跟踪参数（URL 去重时需要移除）
TRACKING_PARAMS = {
    'utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 'utm_content',
    'utm_id', 'utm_source_platform', 'utm_creative_format', 'utm_marketing_tactic',
    'fbclid', 'gclid', 'ttclid', 'li_fat_id', 'mc_cid', 'mc_eid',
    '_ga', '_gid', '_gac', '_gl', '_utmz', '_utma',
    'ref', 'source', 'from', 'share_token', 'share_source',
}


def normalize_url(url: str) -> str:
    """
    规范化 URL，用于跨用户内容去重。

    操作:
    1. 去除首尾空白
    2. 协议和主机名转小写
    3. 移除默认端口 (80/443)
    4. 移除 URL fragment (#xxx)
    5. 移除常见跟踪参数 (utm_*, fbclid, gclid 等)
    6. 对查询参数按键排序
    7. 路径去除尾部斜杠（根路径保留）

    Args:
        url: 原始 URL

    Returns:
        规范化后的 URL
    """
    if not url:
        return ""

    try:
        url = url.strip()
        parsed = urlparse(url)

        scheme = parsed.scheme.lower()
        netloc = parsed.netloc.lower()

        # 移除默认端口
        if netloc.endswith(':80') and scheme == 'http':
            netloc = netloc[:-3]
        elif netloc.endswith(':443') and scheme == 'https':
            netloc = netloc[:-4]

        # 路径规范化
        path = parsed.path
        if path != '/' and path.endswith('/'):
            path = path[:-1]

        # 查询参数：移除跟踪参数并排序
        query_params = parse_qsl(parsed.query, keep_blank_values=True)
        filtered_params = [
            (k, v) for k, v in query_params
            if k.lower() not in TRACKING_PARAMS
        ]
        filtered_params.sort(key=lambda x: x[0].lower())
        query = urlencode(filtered_params)

        normalized = urlunparse((scheme, netloc, path, '', query, ''))
        return normalized

    except Exception as e:
        logger.error(f"URL 规范化失败: {url}, 错误: {e}")
        return url


def generate_content_hash(content: str, url: str = "") -> str:
    """
    生成文章内容哈希，用于检测内容变更和去重。

    使用 SHA256(content + url) 作为稳定哈希值。
    加入 URL 是为了防止两篇完全不同的文章恰好内容相同（极罕见）。

    Args:
        content: 文章正文内容
        url: 文章 URL（可选但推荐）

    Returns:
        64 位十六进制字符串
    """
    data = (content or "") + "\n" + (url or "")
    return hashlib.sha256(data.encode('utf-8')).hexdigest()
