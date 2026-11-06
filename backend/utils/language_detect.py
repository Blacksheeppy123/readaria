"""
文章内容语言检测工具。

AI 摘要使用文章内容的语言生成；用户 UI 语言偏好（users.preferred_language）
仅作为内容语言检测失败时的 fallback。
"""
import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

# 与 backend/nlp/processor.py 中摘要 prompt 支持的语言保持一致
SUPPORTED_SUMMARY_LANGUAGES = frozenset({'zh', 'en', 'ja', 'ko', 'fr', 'de', 'es', 'ru'})

# 过短的文本语言检测结果不可靠，直接回退到 fallback
MIN_DETECT_LENGTH = 40

_HTML_RE = re.compile(r"<[^>]+>")
_CJK_RE = re.compile(r"[一-鿿]")
_HIRAGANA_KATAKANA_RE = re.compile(r"[぀-ヿ]")
_HANGUL_RE = re.compile(r"[가-힯]")
_LATIN_RE = re.compile(r"[A-Za-z]")

try:
    from langdetect import DetectorFactory, detect as _langdetect_detect

    # langdetect 内部依赖随机采样，固定 seed 保证结果可复现
    DetectorFactory.seed = 0
    _HAS_LANGDETECT = True
except Exception:  # pragma: no cover - langdetect 未安装时降级为启发式检测
    _HAS_LANGDETECT = False


def normalize_detected_language(code: str) -> Optional[str]:
    """把 langdetect 返回的代码（如 zh-cn、zh-tw、en）归一化为摘要支持的语言代码；不支持时返回 None"""
    if not code:
        return None
    code = code.lower().split('-')[0]
    return code if code in SUPPORTED_SUMMARY_LANGUAGES else None


def detect_content_language(text: str, fallback: str = 'en') -> str:
    """
    检测文本（文章正文/摘要）的语言。

    Args:
        text: 待检测文本
        fallback: 检测失败或文本过短时返回的语言（调用方通常传用户偏好语言）

    Returns:
        摘要支持的语言代码（zh/en/ja/ko/fr/de/es/ru），失败时返回 fallback
    """
    if not text:
        return fallback
    cleaned = _HTML_RE.sub(' ', text).strip()
    if len(cleaned) < MIN_DETECT_LENGTH:
        return fallback

    if _HAS_LANGDETECT:
        try:
            detected = normalize_detected_language(_langdetect_detect(cleaned))
            if detected:
                return detected
        except Exception as e:
            logger.warning(f"语言检测失败，使用 fallback={fallback}: {e}")

    heuristic = _heuristic_detect(cleaned)
    return heuristic or fallback


def _heuristic_detect(text: str) -> Optional[str]:
    """轻量启发式检测（langdetect 不可用或结果不支持时的兜底）：基于文字系统判断 CJK 语言"""
    sample = text[:1000]
    if _HANGUL_RE.search(sample):
        return 'ko'
    if _HIRAGANA_KATAKANA_RE.search(sample):
        return 'ja'
    cjk_count = len(_CJK_RE.findall(sample))
    latin_count = len(_LATIN_RE.findall(sample))
    if cjk_count > latin_count:
        return 'zh'
    return None


def summary_matches_language(summary: str, language: str) -> bool:
    """
    校验已缓存摘要的实际语言与缓存键（language）是否一致。

    用于存量脏缓存的自愈检查：修复前缓存键是用户 UI 语言，个别条目可能出现
    摘要语言与缓存键不符的情况，检测到不一致时调用方应重新生成。
    """
    if not summary:
        return False
    # 摘要文本较短时检测结果不可靠，默认信任缓存
    if len(summary.strip()) < MIN_DETECT_LENGTH:
        return True
    return detect_content_language(summary, fallback=language) == language
