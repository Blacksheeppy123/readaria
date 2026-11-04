"""
OpenAI Client with OpenRouter Fallback
当主 OpenAI 接口返回 rate limit 或配额错误时，自动切换到 OpenRouter
"""

import logging
from typing import Optional

from openai import OpenAI, RateLimitError, APIStatusError

from core.config.settings import settings

logger = logging.getLogger(__name__)

# 2026-10-26: gpt-4.1-nano 已下线（OpenAI deprecations），gpt-4.1-mini 2027-01-14 下线。
# 官方推荐替代：gpt-5.6-luna（nano 档）、gpt-6-luna（mini 档）。
DEFAULT_MODEL = "gpt-5.6-luna"

# 新一代模型（gpt-5*/gpt-6*/o 系列）的 chat completions 限制（已实测验证 2026-10-26）：
# - 不支持 max_tokens，必须用 max_completion_tokens
# - temperature 只支持默认值 1，传其他值报 400
_RESTRICTED_MODEL_PREFIXES = ("gpt-5", "gpt-6", "o1", "o3", "o4")


def _build_completion_params(
    model: str,
    temperature: float,
    max_tokens: int,
    extra: dict,
) -> dict:
    """按模型能力构造请求参数，兼容新旧两代 OpenAI 模型。"""
    # 防止调用方经 **kwargs 传入冲突的 token 上限参数，最终只保留一个键
    extra.pop("max_tokens", None)
    extra.pop("max_completion_tokens", None)
    # OpenRouter 模型名带 provider 前缀（如 openai/gpt-6-luna），取最后一段匹配
    model_id = model.rsplit("/", 1)[-1]
    params = {"model": model, **extra}
    if model_id.startswith(_RESTRICTED_MODEL_PREFIXES):
        params["max_completion_tokens"] = max_tokens
        if temperature != 1:
            logger.debug(f"{model} 仅支持默认 temperature=1，忽略 temperature={temperature}")
    else:
        params["temperature"] = temperature
        params["max_tokens"] = max_tokens
    return params


def get_primary_client() -> OpenAI:
    return OpenAI(
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
    )


def get_fallback_client() -> Optional[OpenAI]:
    if not settings.openrouter_api_key:
        return None
    return OpenAI(
        api_key=settings.openrouter_api_key,
        base_url=settings.openrouter_base_url,
    )


def chat_completion_with_fallback(
    *,
    messages: list,
    model: str = DEFAULT_MODEL,
    temperature: float = 0.7,
    max_tokens: int = 4096,
    **kwargs,
):
    """
    同步 chat completion，主 OpenAI 失败时 fallback 到 OpenRouter。
    """
    primary = get_primary_client()
    try:
        return primary.chat.completions.create(
            messages=messages,
            **_build_completion_params(model, temperature, max_tokens, kwargs),
        )
    except (RateLimitError, APIStatusError) as e:
        # 仅对 429 (rate limit) 和 quota 相关错误进行 fallback
        if isinstance(e, APIStatusError) and e.status_code not in (429, 402):
            raise

        fallback = get_fallback_client()
        if not fallback:
            logger.error("OpenAI 调用失败且未配置 OpenRouter fallback")
            raise

        fallback_model = settings.openrouter_model
        logger.warning(
            f"OpenAI rate limit，切换到 OpenRouter ({fallback_model}): {e}"
        )
        return fallback.chat.completions.create(
            messages=messages,
            **_build_completion_params(fallback_model, temperature, max_tokens, kwargs),
        )


def get_chat_llm_with_fallback():
    """
    返回带 fallback 的 LangChain ChatOpenAI。
    主 LLM 失败时自动切换到 OpenRouter。
    """
    from langchain_openai import ChatOpenAI

    primary_llm = ChatOpenAI(
        api_key=settings.openai_api_key,
        model=settings.openai_model,
        base_url=settings.openai_base_url,
    )

    if not settings.openrouter_api_key:
        return primary_llm

    fallback_llm = ChatOpenAI(
        api_key=settings.openrouter_api_key,
        model=settings.openrouter_model,
        base_url=settings.openrouter_base_url,
    )

    return primary_llm.with_fallbacks([fallback_llm])
