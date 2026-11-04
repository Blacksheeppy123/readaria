"""
Azure Cognitive Services Speech TTS 单元测试

使用 Mock 替代 Azure SDK，验证：
- 声线映射
- 文本分段与合并
- 缓存
- 错误码映射
"""
import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from backend.nlp import azure_speech as azure_speech_module
from backend.nlp import speech_service as speech_service_module
from backend.nlp.azure_speech import AzureSpeechService
from backend.nlp.speech_service import get_speech_service


FAKE_MP3_BYTES = b"\xff\xfb\x90" + b"\x00" * 100


def _make_settings(**overrides):
    defaults = {
        "azure_speech_key": "fake-key",
        "azure_speech_region": "eastasia",
        "azure_speech_tts_voice": "zh-CN-Xiaoxiao:DragonHDFlashLatestNeural",
        "azure_speech_output_format": "Audio48Khz96KBitRateMonoMp3",
        "tts_cache_dir": "/tmp/azure_tts_test_cache",
        "tts_max_chars_per_request": 3000,
        "tts_max_article_length": 30000,
        "tts_long_article_strategy": "segment",
        "tts_segment_generation_timeout_seconds": 45,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _mock_speechsdk():
    """构造一个可 patch 到 backend.nlp.azure_speech.speechsdk 的 mock 模块。"""
    sdk = MagicMock()
    sdk.ResultReason.SynthesizingAudioCompleted = "SynthesizingAudioCompleted"
    sdk.SpeechConfig = MagicMock(return_value=MagicMock())
    sdk.SpeechSynthesizer = MagicMock(return_value=MagicMock())

    # 用普通类模拟枚举行为：未知格式名 getattr 应返回 None（MagicMock 会自动造属性，无法触发回退路径）
    class _FakeOutputFormat:
        Audio16Khz32KBitRateMonoMp3 = "mp3_format_lo"
        Audio48Khz96KBitRateMonoMp3 = "mp3_format_hi"

    sdk.SpeechSynthesisOutputFormat = _FakeOutputFormat
    return sdk


def test_voice_mapping():
    with patch.object(azure_speech_module, "speechsdk", _mock_speechsdk()):
        svc = AzureSpeechService(_make_settings())
        assert svc._validate_voice("nova") == "nova"
        assert svc._resolve_voice_name("nova", None) == "zh-CN-Xiaoxiao:DragonHDFlashLatestNeural"
        assert svc._resolve_voice_name("echo", None) == "zh-CN-Yunyi:DragonHDFlashLatestNeural"
        assert svc._resolve_voice_name(None, None) == "zh-CN-Xiaoxiao:DragonHDFlashLatestNeural"
        assert svc._resolve_voice_name("default", None) == "zh-CN-Xiaoxiao:DragonHDFlashLatestNeural"
        # Azure voice 名称直接透传
        assert svc._resolve_voice_name("zh-CN-XiaomoNeural", None) == "zh-CN-XiaomoNeural"


def test_resolve_english_voice():
    with patch.object(azure_speech_module, "speechsdk", _mock_speechsdk()):
        svc = AzureSpeechService(_make_settings())
        assert svc._resolve_voice_name("nova", "en") == "en-US-Tiana:DragonHDFlashLatestNeural"
        assert svc._resolve_voice_name("echo", "en-US") == "en-US-Jimmie:DragonHDFlashLatestNeural"


def test_output_format_from_settings():
    """输出格式应从 settings.azure_speech_output_format 读取（默认 48kHz/96kbps）。"""
    sdk = _mock_speechsdk()
    with patch.object(azure_speech_module, "speechsdk", sdk):
        svc = AzureSpeechService(_make_settings())
        svc._speech_config.set_speech_synthesis_output_format.assert_called_with("mp3_format_hi")


def test_cache_key_version_bumped():
    """缓存 key 前缀应带 v3 版本号（v3: 修复小数撕裂后使旧音频整体失效）。"""
    with patch.object(azure_speech_module, "speechsdk", _mock_speechsdk()):
        svc = AzureSpeechService(_make_settings())
        assert svc.model == "azure-speech-v3"
        key = svc._get_cache_key("你好", "nova", article_id="42")
        assert key.startswith("azure-speech-v3|")


def test_cache_key_includes_output_format():
    """缓存 key 应包含实际生效的输出格式名，切换格式后旧缓存不命中。"""
    with patch.object(azure_speech_module, "speechsdk", _mock_speechsdk()):
        svc_hi = AzureSpeechService(
            _make_settings(azure_speech_output_format="Audio48Khz96KBitRateMonoMp3")
        )
        svc_lo = AzureSpeechService(
            _make_settings(azure_speech_output_format="Audio16Khz32KBitRateMonoMp3")
        )
        key_hi = svc_hi._get_cache_key("你好", "nova", article_id="42")
        key_lo = svc_lo._get_cache_key("你好", "nova", article_id="42")
        assert "Audio48Khz96KBitRateMonoMp3" in key_hi
        assert "Audio16Khz32KBitRateMonoMp3" in key_lo
        assert key_hi != key_lo


def test_unknown_output_format_falls_back_and_keys_on_default():
    """未知格式名应回退默认格式，且缓存 key 使用回退后的实际格式名。"""
    sdk = _mock_speechsdk()
    with patch.object(azure_speech_module, "speechsdk", sdk):
        svc = AzureSpeechService(_make_settings(azure_speech_output_format="BogusFormat"))
        svc._speech_config.set_speech_synthesis_output_format.assert_called_with("mp3_format_hi")
        key = svc._get_cache_key("你好", "nova", article_id="42")
        assert "Audio48Khz96KBitRateMonoMp3" in key
        assert "BogusFormat" not in key


def test_build_ssml_keeps_numbers_as_plain_text():
    """数字与百分比保持裸文本直发，不使用 say-as 标记。

    回归：2026-09-03 STT 回环验证证明 <say-as interpret-as="number">x.x</say-as>%
    会把 % 与数字拆散读成"x点x百分号"；Flash 音色对裸文本 x.x% 能正确读作
    "百分之x点x"。小数撕裂的真正根因在 split_sentences，已于该层修复。
    """
    with patch.object(azure_speech_module, "speechsdk", _mock_speechsdk()):
        svc = AzureSpeechService(_make_settings())
        ssml = svc._build_ssml("涨幅0.56%，报53061.89点", "zh-CN-Xiaoxiao:DragonHDFlashLatestNeural")
        assert "<say-as" not in ssml
        assert "0.56%" in ssml
        assert "53061.89" in ssml


def test_build_ssml_escapes_text():
    with patch.object(azure_speech_module, "speechsdk", _mock_speechsdk()):
        svc = AzureSpeechService(_make_settings())
        ssml = svc._build_ssml("1 < 2 & 3 > 0", "zh-CN-Xiaoxiao:DragonHDFlashLatestNeural")
        assert "1 &lt; 2 &amp; 3 &gt; 0" in ssml
        assert 'xml:lang="zh-CN"' in ssml
        assert 'voice name="zh-CN-Xiaoxiao:DragonHDFlashLatestNeural"' in ssml


@pytest.mark.unit
@pytest.mark.tts
@pytest.mark.asyncio
async def test_synthesize_short_text_caches(tmp_path):
    settings = _make_settings(tts_cache_dir=str(tmp_path))
    sdk = _mock_speechsdk()

    result_mock = MagicMock()
    result_mock.reason = sdk.ResultReason.SynthesizingAudioCompleted
    result_mock.audio_data = FAKE_MP3_BYTES
    result_mock.cancellation_details = None
    sdk.SpeechSynthesizer.return_value.speak_ssml_async.return_value.get.return_value = result_mock

    with patch.object(azure_speech_module, "speechsdk", sdk):
        svc = AzureSpeechService(settings)
        audio = await svc.synthesize(text="你好世界", article_id="123", voice="nova")
        assert audio == FAKE_MP3_BYTES

        # 第二次调用应命中缓存，不再访问 SDK
        sdk.SpeechSynthesizer.reset_mock()
        audio2 = await svc.synthesize(text="你好世界", article_id="123", voice="nova")
        assert audio2 == FAKE_MP3_BYTES
        sdk.SpeechSynthesizer.assert_not_called()


@pytest.mark.unit
@pytest.mark.tts
@pytest.mark.asyncio
async def test_synthesize_long_text_segments_and_merges(tmp_path):
    """超长文本应分段调用 SDK，并合并音频。"""
    settings = _make_settings(tts_cache_dir=str(tmp_path), tts_max_chars_per_request=50)
    sdk = _mock_speechsdk()

    result_mock = MagicMock()
    result_mock.reason = sdk.ResultReason.SynthesizingAudioCompleted
    result_mock.audio_data = FAKE_MP3_BYTES
    result_mock.cancellation_details = None
    sdk.SpeechSynthesizer.return_value.speak_ssml_async.return_value.get.return_value = result_mock

    merged_bytes = b"MERGED_MP3_BYTES"

    with patch.object(azure_speech_module, "speechsdk", sdk):
        svc = AzureSpeechService(settings)
        with patch.object(svc, "_merge_audio_files", return_value=merged_bytes):
            text = "。".join([f"这是第{i}句测试文本" for i in range(20)])
            audio = await svc.synthesize(text=text, article_id="long", voice="nova", use_cache=False)
            assert audio == merged_bytes
            # 应触发多次 SDK 调用
            assert sdk.SpeechSynthesizer.return_value.speak_ssml_async.call_count >= 2


@pytest.mark.unit
@pytest.mark.tts
@pytest.mark.asyncio
async def test_quota_error_mapping(tmp_path):
    settings = _make_settings(tts_cache_dir=str(tmp_path))
    sdk = _mock_speechsdk()

    result_mock = MagicMock()
    result_mock.reason = "Canceled"
    cancellation = MagicMock()
    cancellation.error_details = "Usage quota exceeded."
    result_mock.cancellation_details = cancellation
    sdk.SpeechSynthesizer.return_value.speak_ssml_async.return_value.get.return_value = result_mock

    with patch.object(azure_speech_module, "speechsdk", sdk):
        svc = AzureSpeechService(settings)
        with pytest.raises(RuntimeError) as exc_info:
            await svc.synthesize(text="测试", article_id="quota", voice="nova")
        assert "quota_exhausted" in str(exc_info.value)


@pytest.mark.unit
@pytest.mark.tts
def test_factory_falls_back_when_credentials_missing():
    """当选择 azure_speech 但缺少凭据时，工厂函数应回退到 OpenAI TTS。"""
    speech_service_module._speech_service_instance = None

    settings = _make_settings(
        tts_provider="azure_speech",
        azure_speech_key=None,
        azure_speech_region=None,
        openai_api_key="fake-openai-key",
        openai_base_url="https://api.openai.com/v1",
        openai_tts_model="tts-1",
        openai_tts_voice="nova",
        openai_tts_format="mp3",
        tts_cache_dir="/tmp/fallback_test_cache",
        tts_max_chars_per_request=3000,
        tts_max_article_length=30000,
        tts_long_article_strategy="segment",
    )

    with patch("backend.nlp.openai_speech.AsyncOpenAI", MagicMock()), \
         patch.dict(os.environ, {"HTTP_PROXY": "", "HTTPS_PROXY": "", "ALL_PROXY": ""}, clear=False):
        svc = get_speech_service(settings)
        assert svc.__class__.__name__ == "OpenAISpeechService"

    speech_service_module._speech_service_instance = None


@pytest.mark.unit
@pytest.mark.tts
def test_factory_selects_azure_speech_when_configured(tmp_path):
    """当 azure_speech 配置完整时，工厂函数应返回 AzureSpeechService。"""
    speech_service_module._speech_service_instance = None

    settings = _make_settings(
        tts_provider="azure_speech",
        tts_cache_dir=str(tmp_path),
    )
    sdk = _mock_speechsdk()

    with patch.object(azure_speech_module, "speechsdk", sdk):
        svc = get_speech_service(settings)
        assert svc.__class__.__name__ == "AzureSpeechService"

    speech_service_module._speech_service_instance = None


@pytest.mark.unit
@pytest.mark.tts
def test_resolve_full_azure_voice_name_with_explicit_lang():
    """完整 Azure voice 名称在显式 lang 下也必须透传（用户音色选择功能 2026-09-07）。

    修复前：voice='zh-CN-YunyangNeural' + lang='zh' 时，
    VOICE_MAP.get(全名, default) 不命中而错误回退到默认晓晓。
    """
    with patch.object(azure_speech_module, "speechsdk", _mock_speechsdk()):
        svc = AzureSpeechService(_make_settings())
        # 完整名 + 显式 lang → 透传
        assert svc._resolve_voice_name("zh-CN-YunyangNeural", "zh") == "zh-CN-YunyangNeural"
        assert svc._resolve_voice_name("zh-CN-Xiaoshuang:DragonHDFlashLatestNeural", "zh-CN") == "zh-CN-Xiaoshuang:DragonHDFlashLatestNeural"
        assert svc._resolve_voice_name("en-US-Ava:DragonLatestNeural", "en") == "en-US-Ava:DragonLatestNeural"
        assert svc._resolve_voice_name("zh-CN-YunyangNeural", "auto") == "zh-CN-YunyangNeural"
        # 回归：None / 逻辑名行为完全不变
        assert svc._resolve_voice_name(None, None) == "zh-CN-Xiaoxiao:DragonHDFlashLatestNeural"
        assert svc._resolve_voice_name(None, "en") == "en-US-Tiana:DragonHDFlashLatestNeural"
        assert svc._resolve_voice_name("nova", "en") == "en-US-Tiana:DragonHDFlashLatestNeural"
        assert svc._resolve_voice_name("echo", "zh") == "zh-CN-Yunyi:DragonHDFlashLatestNeural"
        assert svc._resolve_voice_name("nova", "zh") == "zh-CN-Xiaoxiao:DragonHDFlashLatestNeural"


@pytest.mark.unit
@pytest.mark.tts
def test_malicious_voice_name_rejected():
    """恶意 voice 名称（SSML 注入）必须回退默认音色（2026-09-08 code review）。

    voice 参数会插入 SSML <voice name="..."> 属性，完整名透传必须做严格字符集校验。
    """
    with patch.object(azure_speech_module, "speechsdk", _mock_speechsdk()):
        svc = AzureSpeechService(_make_settings())
        malicious = 'x-Neural"><script>alert(1)</script>'
        assert svc._validate_voice(malicious) == "zh-CN-Xiaoxiao:DragonHDFlashLatestNeural"
        assert svc._resolve_voice_name(malicious, None) == "zh-CN-Xiaoxiao:DragonHDFlashLatestNeural"
        assert svc._resolve_voice_name(malicious, "zh") == "zh-CN-Xiaoxiao:DragonHDFlashLatestNeural"
        # 含引号/空格/尖括号/斜杠的全名一律拒绝
        for bad in ['zh-CN-Yunyang"Neural', 'zh CN-YunyangNeural', 'zh-CN-Yun<yang>Neural', 'zh-CN/YunyangNeural']:
            assert svc._resolve_voice_name(bad, "zh") == "zh-CN-Xiaoxiao:DragonHDFlashLatestNeural"
        # 合法全名（含冒号的 DragonHD 形式）不受影响
        assert svc._resolve_voice_name("zh-CN-Xiaoshuang:DragonHDFlashLatestNeural", "zh") == "zh-CN-Xiaoshuang:DragonHDFlashLatestNeural"
        assert svc._resolve_voice_name("en-US-Ava:DragonLatestNeural", "en") == "en-US-Ava:DragonLatestNeural"
