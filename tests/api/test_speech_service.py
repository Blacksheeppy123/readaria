"""
TTS 语音服务单元测试

测试 OpenAI TTS 实现的核心功能：
- 文本分割逻辑
- 缓存 key 生成
- 短文本合成（模拟）
- 长文本分段合成（模拟）
"""
import os
import sys
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from backend.nlp.openai_speech import OpenAISpeechService
from backend.nlp.speech_service import get_speech_service
from core.config.settings import settings


@pytest.fixture
def mock_settings():
    """创建模拟的 settings 对象"""
    settings_mock = MagicMock()
    # OpenAI 配置（用于回退）
    settings_mock.openai_api_key = "test-api-key"
    settings_mock.openai_base_url = "https://api.openai.com/v1"
    # Azure OpenAI TTS 配置（设置为空，使用 OpenAI 回退）
    settings_mock.azure_openai_tts_endpoint = ""
    settings_mock.azure_openai_tts_api_key = ""
    settings_mock.azure_openai_tts_deployment = "tts"
    settings_mock.azure_openai_api_version = "2024-02-15-preview"
    # TTS 配置
    settings_mock.tts_cache_dir = "/tmp/test_tts_cache"
    settings_mock.openai_tts_model = "tts-1-hd"
    settings_mock.openai_tts_voice = "alloy"
    settings_mock.openai_tts_format = "mp3"
    settings_mock.tts_max_chars_per_request = 3000
    settings_mock.tts_max_article_length = 30000
    settings_mock.tts_long_article_strategy = "segment"
    return settings_mock


@pytest.fixture
def speech_service(mock_settings):
    """创建 OpenAISpeechService 实例"""
    with patch('backend.nlp.openai_speech.AsyncOpenAI'):
        service = OpenAISpeechService(mock_settings)
        return service


@pytest.mark.unit
class TestTextSplitting:
    """测试文本分割逻辑"""

    def test_split_short_text(self, speech_service):
        """测试短文本（无需分割）"""
        text = "这是一段短文本，不需要分割。"
        segments = speech_service._split_text(text, max_length=3000)
        assert len(segments) == 1
        assert segments[0] == text

    def test_split_by_paragraphs(self, speech_service):
        """测试按段落分割"""
        text = "第一段内容。\n\n第二段内容。\n\n第三段内容。"
        segments = speech_service._split_text(text, max_length=20)
        # 每段都会被独立处理
        assert len(segments) >= 1
        # 验证所有分段拼接后等于原文（去掉空白）
        combined = ''.join(segments).replace('\n\n', '').strip()
        original = text.replace('\n\n', '').strip()
        assert combined == original

    def test_split_by_sentences(self, speech_service):
        """测试按句子分割（段落过长时）"""
        text = "这是第一句话。这是第二句话。这是第三句话。" * 50  # 超过 max_length
        segments = speech_service._split_text(text, max_length=100)
        assert len(segments) > 1
        # 验证分段都不超过 max_length
        for segment in segments:
            assert len(segment) <= 100 or '。' not in segment  # 允许强制截断的情况

    def test_split_force_truncate(self, speech_service):
        """测试强制截断（单句超长）"""
        # 一个非常长的句子，没有标点符号
        text = "a" * 5000
        segments = speech_service._split_text(text, max_length=1000)
        assert len(segments) >= 5  # 至少分成 5 段
        # 验证每段长度不超过 max_length
        for segment in segments:
            assert len(segment) <= 1000


@pytest.mark.unit
class TestCacheKey:
    """测试缓存 key 生成"""

    def test_cache_key_generation(self, speech_service):
        """测试缓存 key 是否一致"""
        text = "测试文本"
        voice = "alloy"

        key1 = speech_service._get_cache_key(text, voice)
        key2 = speech_service._get_cache_key(text, voice)

        # 相同输入应生成相同的 key
        assert key1 == key2
        # key 应该是 32 位十六进制字符串（MD5）
        assert len(key1) == 32
        assert all(c in '0123456789abcdef' for c in key1)

    def test_cache_key_different_inputs(self, speech_service):
        """测试不同输入生成不同的 key"""
        key1 = speech_service._get_cache_key("文本1", "alloy")
        key2 = speech_service._get_cache_key("文本2", "alloy")
        key3 = speech_service._get_cache_key("文本1", "nova")

        # 不同文本或不同声音应生成不同的 key
        assert key1 != key2
        assert key1 != key3


@pytest.mark.unit
class TestSynthesizeValidation:
    """测试输入校验"""

    @pytest.mark.asyncio
    async def test_empty_text_rejection(self, speech_service):
        """测试空文本被拒绝"""
        with pytest.raises(ValueError, match="待朗读文本不能为空"):
            await speech_service.synthesize("")

    @pytest.mark.asyncio
    async def test_whitespace_text_rejection(self, speech_service):
        """测试仅空格文本被拒绝"""
        with pytest.raises(ValueError, match="待朗读文本不能为空"):
            await speech_service.synthesize("   \n\t  ")

    @pytest.mark.asyncio
    async def test_text_too_long_reject(self, mock_settings, speech_service):
        """测试超长文本被拒绝（reject 策略）"""
        mock_settings.tts_long_article_strategy = "reject"
        mock_settings.tts_max_article_length = 100
        speech_service.long_article_strategy = "reject"
        speech_service.max_article_length = 100

        long_text = "a" * 200
        with pytest.raises(ValueError, match="文本过长"):
            await speech_service.synthesize(long_text)


@pytest.mark.unit
class TestSynthesizeCacheControl:
    """测试缓存开关"""

    @pytest.mark.asyncio
    async def test_synthesize_can_skip_cache(self, speech_service):
        """测试关闭缓存时不会读写磁盘缓存"""
        with patch.object(speech_service, "_get_from_cache") as mock_get_cache, \
             patch.object(speech_service, "_save_to_cache") as mock_save_cache, \
             patch.object(speech_service, "_synthesize_single", new=AsyncMock(return_value=b"audio-bytes")):
            audio_bytes = await speech_service.synthesize(
                "测试播客片段",
                voice="alloy",
                use_cache=False,
            )

        assert audio_bytes == b"audio-bytes"
        mock_get_cache.assert_not_called()
        mock_save_cache.assert_not_called()


@pytest.mark.unit
class TestServiceFactory:
    """测试服务工厂"""

    def test_get_speech_service(self):
        """测试获取 TTS 服务实例"""
        service = get_speech_service(settings)
        assert service is not None
        # 根据配置返回对应的服务类型
        if settings.tts_provider == "openai":
            assert isinstance(service, OpenAISpeechService)
        elif settings.tts_provider == "google":
            from backend.nlp.google_speech import GoogleSpeechService
            assert isinstance(service, GoogleSpeechService)
        else:
            pytest.fail(f"未知的 TTS provider: {settings.tts_provider}")


@pytest.mark.integration
@pytest.mark.skipif(
    not os.getenv('OPENAI_API_KEY'),
    reason="需要 OPENAI_API_KEY 环境变量才能运行集成测试"
)
class TestRealTTSIntegration:
    """真实 OpenAI TTS API 集成测试（需要 API key）"""

    @pytest.mark.asyncio
    async def test_real_short_text_synthesis(self):
        """测试真实的短文本合成（需要实际 API key）"""
        service = get_speech_service(settings)
        text = "这是一段测试文本。"

        audio_bytes = await service.synthesize(text)

        # 验证返回的是音频数据
        assert isinstance(audio_bytes, bytes)
        assert len(audio_bytes) > 0
        # MP3 文件头检查（ID3 或 MPEG frame sync）
        # MPEG frame sync: 前11位都是1 (0xff, 0xe0-0xff)
        assert audio_bytes[:3] == b'ID3' or (audio_bytes[0] == 0xff and (audio_bytes[1] & 0xe0) == 0xe0)


# pytest 标记说明：
# @pytest.mark.unit - 单元测试，不依赖外部服务
# @pytest.mark.integration - 集成测试，需要真实 API key
# @pytest.mark.asyncio - 异步测试
