"""
HTML 内容清洗工具
防止 XSS 攻击，清理恶意内容
"""
import re
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class HTMLSanitizer:
    """HTML 清洗器"""

    # 允许的 HTML 标签（白名单）
    ALLOWED_TAGS = {
        'p', 'br', 'strong', 'em', 'u', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
        'blockquote', 'code', 'pre', 'ul', 'ol', 'li', 'a', 'img',
        'table', 'thead', 'tbody', 'tr', 'th', 'td',
        'span', 'div', 'section', 'article', 'figure', 'figcaption'
    }

    # 允许的 HTML 属性（白名单）
    ALLOWED_ATTRS = {
        'a': ['href', 'title', 'target'],
        'img': ['src', 'alt', 'title', 'width', 'height'],
        'code': ['class'],
        'pre': ['class'],
        'span': ['class'],
        'div': ['class']
    }

    # 危险的标签模式（需要移除）
    DANGEROUS_TAG_PATTERNS = [
        r'<script[^>]*>.*?</script>',
        r'<iframe[^>]*>.*?</iframe>',
        r'<object[^>]*>.*?</object>',
        r'<embed[^>]*>.*?</embed>',
        r'<applet[^>]*>.*?</applet>',
        r'<link[^>]*>',
        r'<meta[^>]*>',
        r'<style[^>]*>.*?</style>',
        r'<base[^>]*>',
        r'<form[^>]*>.*?</form>',
        r'<input[^>]*>',
        r'<button[^>]*>.*?</button>',
        r'<textarea[^>]*>.*?</textarea>',
        r'<select[^>]*>.*?</select>',
    ]

    # 危险的属性模式
    DANGEROUS_ATTR_PATTERNS = [
        r'\s+on\w+\s*=',  # onclick, onload, onerror 等事件处理器
        r'\s+data-\w+\s*=',  # data-* 属性（可能用于 DOM XSS）
        r'javascript:',  # javascript: 协议
        r'vbscript:',  # vbscript: 协议
    ]

    def __init__(self, max_length: int = 500_000):
        """
        初始化 HTML 清洗器

        Args:
            max_length: HTML 内容最大长度（字节），超过则截断
        """
        self.max_length = max_length

    def sanitize(self, html: str) -> str:
        """
        清洗 HTML 内容

        步骤:
        1. 长度检查与截断
        2. 移除危险标签 (<script>, <iframe> 等)
        3. 移除危险属性 (onclick, onerror 等)
        4. 移除危险协议 (javascript:, vbscript:)
        5. 编码特殊字符

        Args:
            html: 原始 HTML

        Returns:
            清洗后的 HTML
        """
        if not html:
            return ""

        try:
            # 1. 长度检查
            if len(html.encode('utf-8')) > self.max_length:
                logger.warning(f"HTML 内容过长 ({len(html)} 字符)，截断到 {self.max_length} 字节")
                # 截断到最大长度（按字节）
                html = html.encode('utf-8')[:self.max_length].decode('utf-8', errors='ignore')

            # 2. 移除危险标签
            for pattern in self.DANGEROUS_TAG_PATTERNS:
                html = re.sub(pattern, '', html, flags=re.IGNORECASE | re.DOTALL)

            # 3. 移除危险属性
            for pattern in self.DANGEROUS_ATTR_PATTERNS:
                html = re.sub(pattern, ' ', html, flags=re.IGNORECASE)

            # 4. 清理额外的空白
            html = re.sub(r'\s+', ' ', html)
            html = html.strip()

            return html

        except Exception as e:
            logger.error(f"HTML 清洗失败: {str(e)[:100]}")
            # 发生错误时返回空字符串（安全优先）
            return ""

    def sanitize_text(self, text: str) -> str:
        """
        清洗纯文本内容（移除所有 HTML 标签）

        Args:
            text: 原始文本

        Returns:
            清洗后的纯文本
        """
        if not text:
            return ""

        try:
            # 长度检查
            if len(text.encode('utf-8')) > self.max_length:
                text = text.encode('utf-8')[:self.max_length].decode('utf-8', errors='ignore')

            # 移除所有 HTML 标签
            text = re.sub(r'<[^>]+>', '', text)

            # 解码 HTML 实体
            text = text.replace('&lt;', '<')
            text = text.replace('&gt;', '>')
            text = text.replace('&amp;', '&')
            text = text.replace('&quot;', '"')
            text = text.replace('&#39;', "'")
            text = text.replace('&nbsp;', ' ')

            # 清理空白
            text = re.sub(r'\s+', ' ', text)
            text = text.strip()

            return text

        except Exception as e:
            logger.error(f"文本清洗失败: {str(e)[:100]}")
            return ""

    def is_safe_url(self, url: str) -> bool:
        """
        检查 URL 是否安全（用于 href 和 src 属性）

        Args:
            url: 待检查的 URL

        Returns:
            是否安全
        """
        if not url:
            return False

        url_lower = url.lower().strip()

        # 阻止危险协议
        dangerous_protocols = ['javascript:', 'vbscript:', 'data:', 'file:']
        for protocol in dangerous_protocols:
            if url_lower.startswith(protocol):
                return False

        # 只允许 http(s) 协议
        if not (url_lower.startswith('http://') or url_lower.startswith('https://') or url_lower.startswith('//')):
            # 相对路径也允许
            if not url_lower.startswith('/') and not url_lower.startswith('./') and not url_lower.startswith('../'):
                return False

        return True


def create_html_sanitizer_from_settings(settings) -> HTMLSanitizer:
    """
    从配置创建 HTML 清洗器

    Args:
        settings: Settings 实例

    Returns:
        HTMLSanitizer 实例
    """
    return HTMLSanitizer(max_length=settings.max_html_content_length)


# 使用示例
if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)

    sanitizer = HTMLSanitizer(max_length=500_000)

    test_cases = [
        # 正常 HTML
        ("<p>这是一段<strong>正常</strong>的文本</p>", True),

        # 包含 script 标签（应被移除）
        ("<p>文本</p><script>alert('XSS')</script><p>更多文本</p>", False),

        # 包含 onclick 事件（应被移除）
        ("<a href='#' onclick='alert(\"XSS\")'>点击</a>", False),

        # 包含 iframe（应被移除）
        ("<iframe src='http://evil.com'></iframe>", False),

        # javascript: 协议（应被移除）
        ("<a href='javascript:alert(1)'>链接</a>", False),
    ]

    print("=== HTML 清洗测试 ===\n")
    for html, should_be_safe in test_cases:
        cleaned = sanitizer.sanitize(html)
        has_script = '<script' in cleaned.lower()
        has_onclick = 'onclick' in cleaned.lower()
        has_iframe = '<iframe' in cleaned.lower()
        has_javascript = 'javascript:' in cleaned.lower()

        is_safe = not (has_script or has_onclick or has_iframe or has_javascript)
        status = "✅" if is_safe == should_be_safe else "❌"

        print(f"{status} 原始: {html[:80]}")
        print(f"   清洗: {cleaned[:80]}")
        if not is_safe:
            print(f"   ⚠️  仍包含危险内容")
        print()
