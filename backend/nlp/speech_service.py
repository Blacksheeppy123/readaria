"""
语音服务抽象接口 (TTS/STT)

提供统一的语音合成和识别接口，支持多供应商切换（OpenAI / Azure / 国内厂商 / 本地模型）
"""
from abc import ABC, abstractmethod
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class SpeechService(ABC):
    """语音服务抽象接口"""

    @abstractmethod
    async def synthesize(
        self,
        text: str,
        article_id: Optional[str] = None,
        lang: Optional[str] = None,
        voice: Optional[str] = None,
        audio_format: Optional[str] = None,
        use_cache: bool = True,
    ) -> bytes:
        """
        合成语音（TTS）

        Args:
            text: 待朗读文本
            article_id: 文章 ID（可选，用于缓存标识，提高缓存命中率）
            lang: 语言标识（"zh", "en", "auto" 等），None 表示自动检测
            voice: 声线标识（逻辑名称，由实现类映射到具体 voice id）
            audio_format: 音频格式（mp3/opus/aac 等），None 表示使用默认配置
            use_cache: 是否使用磁盘缓存，False 时跳过缓存读写

        Returns:
            音频二进制数据（格式由实现类决定，默认推荐 mp3）

        Raises:
            Exception: 合成失败时抛出异常
        """
        pass

    @abstractmethod
    async def synthesize_stream(
        self,
        text: str,
        article_id: Optional[str] = None,
        lang: Optional[str] = None,
        voice: Optional[str] = None,
        audio_format: Optional[str] = None
    ):
        """
        流式合成语音（支持边生成边返回）

        Args:
            text: 待朗读文本
            article_id: 文章 ID（用于缓存与统计）
            lang: 语言标识
            voice: 声线标识
            audio_format: 音频格式（mp3/opus/aac 等），None 时使用默认配置

        Returns:
            Async iterator yielding audio bytes

        Raises:
            Exception: 合成失败时抛出异常
        """
        pass

    @abstractmethod
    async def transcribe(
        self,
        audio: bytes,
        lang_hint: Optional[str] = None
    ) -> str:
        """
        语音识别（STT）

        Args:
            audio: 音频二进制数据
            lang_hint: 语言提示（"zh", "en" 等），None 表示自动检测

        Returns:
            识别后的文本

        Raises:
            NotImplementedError: Phase 1 暂不实现，抛出此异常
        """
        raise NotImplementedError("STT 功能暂未实现（Phase 2 计划）")


# ✅ 单例模式：避免重复初始化 TTS 服务
_speech_service_instance = None


def get_speech_service(settings) -> SpeechService:
    """
    工厂函数：根据配置返回对应的语音服务实现（单例模式）

    Args:
        settings: 应用配置对象（core.config.settings.Settings）

    Returns:
        SpeechService 实现实例（单例）

    Raises:
        ValueError: 配置的 provider 不支持时抛出异常
    """
    global _speech_service_instance

    # 单例模式：如果已初始化，直接返回
    if _speech_service_instance is not None:
        return _speech_service_instance

    # 根据配置选择 TTS provider
    provider = getattr(settings, 'tts_provider', 'openai').lower()

    if provider == 'google':
        # Google Cloud TTS
        from backend.nlp.google_speech import GoogleSpeechService
        _speech_service_instance = GoogleSpeechService(settings)
    elif provider == 'azure':
        # Azure OpenAI TTS
        from backend.nlp.openai_speech import OpenAISpeechService
        _speech_service_instance = OpenAISpeechService(settings)
    elif provider == 'azure_speech':
        # Azure Cognitive Services Speech TTS（免费额度方案）
        try:
            from backend.nlp.azure_speech import AzureSpeechService
            _speech_service_instance = AzureSpeechService(settings)
        except Exception as exc:
            logger.warning(
                f"⚠️ Azure Speech TTS 初始化失败，将回退到 OpenAI TTS: {exc}"
            )
            from backend.nlp.openai_speech import OpenAISpeechService
            _speech_service_instance = OpenAISpeechService(settings)
    elif provider == 'openai':
        # OpenAI TTS
        from backend.nlp.openai_speech import OpenAISpeechService
        _speech_service_instance = OpenAISpeechService(settings)
    else:
        raise ValueError(f"不支持的 TTS provider: {provider}")

    return _speech_service_instance


__all__ = ['SpeechService', 'get_speech_service']
