"""
Azure Cognitive Services Speech (TTS) 实现

使用 Azure AI Speech SDK 的神经语音实现高质量语音合成。
每月 50 万字符免费额度，适合替代 OpenAI TTS 降低成本。

支持：缓存、自动分段、音频合并、错误标准化处理。
"""
import asyncio
import hashlib
import html
import os
import re
from abc import ABC
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from pathlib import Path
from typing import AsyncIterator, List, Optional, Tuple

import logging

from pydub import AudioSegment

from backend.nlp.speech_service import SpeechService

try:
    import azure.cognitiveservices.speech as speechsdk
except ImportError:  # pragma: no cover
    speechsdk = None  # type: ignore

logger = logging.getLogger(__name__)

# Azure SDK 的 speak_*_async 是同步阻塞调用，使用线程池避免阻塞事件循环
_azure_tts_executor = ThreadPoolExecutor(max_workers=8, thread_name_prefix="azure_tts_")


class AzureSpeechService(SpeechService):
    """Azure Cognitive Services Speech TTS 服务实现"""

    # 类级别追踪：记录正在运行的生成任务 {cache_key: Task}
    _active_producers = {}

    # 完整 Azure 音色名的合法字符集（字母/数字/冒号/连字符/下划线/点）。
    # voice 会插入 SSML <voice name="..."> 属性，严格校验防 SSML 注入（2026-09-08 review）。
    _FULL_VOICE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9\-_.:]*$")

    # 声线映射：保留前端传入的 OpenAI 风格 voice 名称作为逻辑名，
    # 内部映射到 Azure Neural voice。未识别时按语言选择默认声音。
    # 2026-09 起升级为 DragonHD Flash 新一代音色（标准神经计费，自然度更高）。
    VOICE_MAP = {
        # 女声
        "nova": "zh-CN-Xiaoxiao:DragonHDFlashLatestNeural",
        "shimmer": "zh-CN-Xiaoxiao:DragonHDFlashLatestNeural",
        "alloy": "zh-CN-Xiaoxiao:DragonHDFlashLatestNeural",
        "default": "zh-CN-Xiaoxiao:DragonHDFlashLatestNeural",
        # 男声
        "echo": "zh-CN-Yunyi:DragonHDFlashLatestNeural",
        "fable": "zh-CN-Yunyi:DragonHDFlashLatestNeural",
        "onyx": "zh-CN-Yunyi:DragonHDFlashLatestNeural",
    }

    ENGLISH_VOICE_MAP = {
        "nova": "en-US-Tiana:DragonHDFlashLatestNeural",
        "shimmer": "en-US-Tiana:DragonHDFlashLatestNeural",
        "alloy": "en-US-Tiana:DragonHDFlashLatestNeural",
        "default": "en-US-Tiana:DragonHDFlashLatestNeural",
        "echo": "en-US-Jimmie:DragonHDFlashLatestNeural",
        "fable": "en-US-Jimmie:DragonHDFlashLatestNeural",
        "onyx": "en-US-Jimmie:DragonHDFlashLatestNeural",
    }

    def __init__(self, settings):
        """
        初始化 Azure Speech TTS 服务

        Args:
            settings: 应用配置对象（core.config.settings.Settings）
        """
        self.settings = settings

        # 凭据
        self.speech_key = getattr(settings, "azure_speech_key", None) or os.environ.get("AZURE_SPEECH_KEY")
        self.speech_region = getattr(settings, "azure_speech_region", None) or os.environ.get("AZURE_SPEECH_REGION")

        if not self.speech_key or not self.speech_region:
            raise ValueError(
                "Azure Speech TTS 需要配置 AZURE_SPEECH_KEY 和 AZURE_SPEECH_REGION。"
                "请在 Azure Portal 创建 Speech 资源并写入 .env。"
            )

        # 延迟导入，避免未安装依赖时直接报错
        if speechsdk is None:
            raise ImportError(
                "Azure Speech SDK 未安装。请运行: pip install azure-cognitiveservices-speech"
            )
        self._speechsdk = speechsdk

        # 缓存目录
        self.cache_dir = Path(settings.tts_cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # TTS 配置
        self.default_voice = getattr(settings, "azure_speech_tts_voice", "zh-CN-Xiaoxiao:DragonHDFlashLatestNeural")
        self.audio_format = "mp3"  # Azure Speech SDK 此实现固定输出 MP3
        self.max_chars_per_request = min(getattr(settings, "tts_max_chars_per_request", 3000), 3000)
        self.max_article_length = settings.tts_max_article_length
        self.long_article_strategy = settings.tts_long_article_strategy

        # 用于缓存 key 前缀；音色/码率/文本处理等重大变更时递增版本号，使旧缓存整体失效
        # v3: 2026-09-03 修复 split_sentences 撕裂小数 + 移除 say-as（见 docs/bugs/）
        self.model = "azure-speech-v3"

        # 配置 SDK：输出格式可配置（默认 48kHz 96kbps MP3）
        # Azure 按字符计费，提升码率不增加费用
        self._speech_config = self._speechsdk.SpeechConfig(
            subscription=self.speech_key,
            region=self.speech_region,
        )
        output_format_name = getattr(
            settings, "azure_speech_output_format", "Audio48Khz96KBitRateMonoMp3"
        )
        output_format = getattr(
            self._speechsdk.SpeechSynthesisOutputFormat, output_format_name, None
        )
        if output_format is None:
            logger.warning(
                f"未知的 azure_speech_output_format={output_format_name}，"
                f"回退到 Audio48Khz96KBitRateMonoMp3"
            )
            output_format_name = "Audio48Khz96KBitRateMonoMp3"
            output_format = self._speechsdk.SpeechSynthesisOutputFormat.Audio48Khz96KBitRateMonoMp3
        # 实际生效的格式名，用于缓存 key（切换格式后旧缓存不命中）
        self.output_format_name = output_format_name
        self._speech_config.set_speech_synthesis_output_format(output_format)

        logger.info(
            f"Azure Speech TTS 服务初始化完成 "
            f"(region={self.speech_region}, default_voice={self.default_voice})"
        )

    def _validate_voice(self, voice: Optional[str]) -> str:
        """将逻辑 voice 名称标准化为 Azure voice 名称。"""
        if not voice:
            return self.default_voice
        normalized = voice.lower().strip()
        if normalized in self.VOICE_MAP or normalized in self.ENGLISH_VOICE_MAP:
            return normalized
        # 用户已传完整 Azure voice 名称时，严格字符集校验后透传
        # （防 SSML 注入：voice 会插入 <voice name="..."> 属性，2026-09-08 review）
        if "Neural" in voice and "-" in voice and self._FULL_VOICE_NAME_RE.fullmatch(voice):
            return voice
        return self.default_voice

    def _resolve_voice_name(self, voice: Optional[str], lang: Optional[str]) -> str:
        """根据 voice 名称和语言返回 Azure Neural voice 名称。"""
        # 显式传入完整 Azure voice 名称时直接透传（用户音色选择功能 2026-09-07）。
        # 必须放在 lang 映射之前：全名不是 VOICE_MAP/ENGLISH_VOICE_MAP 的 key，
        # 否则 lang=zh/en 时会被 .get(validated, default) 错误回退到默认音色。
        # 严格字符集校验防止恶意 voice 造成 SSML 注入（2026-09-08 review）。
        if voice and "Neural" in voice and "-" in voice:
            if self._FULL_VOICE_NAME_RE.fullmatch(voice):
                return voice
            voice = None  # 非法音色名：按未指定处理
        validated = self._validate_voice(voice)

        # 显式指定英文
        if lang and lang.lower().startswith("en"):
            return self.ENGLISH_VOICE_MAP.get(validated, self.ENGLISH_VOICE_MAP["default"])

        # 显式指定中文
        if lang and lang.lower().startswith("zh"):
            return self.VOICE_MAP.get(validated, self.VOICE_MAP["default"])

        # 如果传入的是 Azure voice 名称且包含语言前缀，直接返回
        if validated and "-" in validated and "Neural" in validated:
            return validated

        # 默认中文音色
        return self.VOICE_MAP.get(validated, self.default_voice)

    def _resolve_lang(self, voice_name: str) -> str:
        """根据 Azure voice 名称推断 SSML xml:lang。"""
        if voice_name.lower().startswith("en-"):
            return "en-US"
        if voice_name.lower().startswith("ja-"):
            return "ja-JP"
        if voice_name.lower().startswith("ko-"):
            return "ko-KR"
        if voice_name.lower().startswith("fr-"):
            return "fr-FR"
        if voice_name.lower().startswith("de-"):
            return "de-DE"
        return "zh-CN"

    def _build_ssml(self, text: str, voice_name: str) -> str:
        """构建 SSML，对文本进行 XML 转义。

        数字/百分比保持裸文本直发：Flash 音色能正确朗读 x.x%（"百分之x点x"），
        而 <say-as interpret-as="number"> 反而会把 % 拆散读成"百分号"
        （2026-09-03 STT 回环验证结论，见 docs/bugs/20260903 小数撕裂修复记录）。
        """
        lang = self._resolve_lang(voice_name)
        escaped_text = html.escape(text)
        return (
            f'<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" '
            f'xml:lang="{lang}">'
            f'<voice name="{voice_name}">'
            f'<prosody rate="+0%">{escaped_text}</prosody>'
            f'</voice></speak>'
        )

    async def synthesize(
        self,
        text: str,
        article_id: Optional[str] = None,
        lang: Optional[str] = None,
        voice: Optional[str] = None,
        audio_format: Optional[str] = None,  # 接口兼容参数，Azure 固定 MP3
        use_cache: bool = True,
    ) -> bytes:
        """
        合成语音（TTS）

        Args:
            text: 待朗读文本
            article_id: 文章 ID（用于缓存 key）
            lang: 语言提示
            voice: 逻辑声线名称
            audio_format: 仅作兼容，固定输出 MP3
            use_cache: 是否使用磁盘缓存

        Returns:
            MP3 音频二进制数据
        """
        if not text or not text.strip():
            raise ValueError("待朗读文本不能为空")

        text = text.strip()

        # 检查文章总长度
        if len(text) > self.max_article_length:
            if self.long_article_strategy == "reject":
                raise ValueError(
                    f"文本过长（{len(text)} 字符），超过上限 {self.max_article_length} 字符"
                )
            elif self.long_article_strategy == "truncate":
                logger.warning(
                    f"文本过长（{len(text)} 字符），截断至 {self.max_article_length} 字符"
                )
                text = text[:self.max_article_length]

        voice_to_use = self._validate_voice(voice)
        format_to_use = self.audio_format  # 固定 MP3
        cache_key = None

        # 检查缓存
        if use_cache:
            cache_key = self._get_cache_key(text, voice_to_use, article_id)
            cached_audio = self._get_from_cache(cache_key, format_to_use)
            if cached_audio:
                logger.info(
                    f"✅ 缓存命中：{cache_key[:16]}... "
                    f"(article_id={article_id or 'N/A'}, 长度: {len(text)} 字符)"
                )
                return cached_audio

        # 处理超长文本（自动分段）
        if len(text) > self.max_chars_per_request:
            logger.info(
                f"文本过长（{len(text)} 字符），自动分段处理 "
                f"(每段最多 {self.max_chars_per_request} 字符)"
            )
            segments = self._split_text(text, self.max_chars_per_request)
            logger.info(f"分段结果：{len(segments)} 段")

            audio_segments = []
            for i, segment in enumerate(segments, 1):
                logger.info(f"正在合成第 {i}/{len(segments)} 段 ({len(segment)} 字符)...")
                segment_audio = await self._synthesize_single(segment, voice_to_use, lang)
                audio_segments.append(segment_audio)

            logger.info(f"正在合并 {len(audio_segments)} 段音频...")
            merged_audio = self._merge_audio_files(audio_segments)
        else:
            merged_audio = await self._synthesize_single(text, voice_to_use, lang)

        # 写入缓存
        if use_cache and cache_key is not None:
            self._save_to_cache(cache_key, merged_audio, format_to_use)
            logger.info(
                f"音频合成完成：{cache_key[:16]}... "
                f"(文本长度: {len(text)} 字符, 音频大小: {len(merged_audio)} bytes)"
            )
        else:
            logger.info(
                f"音频合成完成（跳过缓存）"
                f"(article_id={article_id or 'N/A'}, 文本长度: {len(text)} 字符, "
                f"音频大小: {len(merged_audio)} bytes)"
            )

        return merged_audio

    async def synthesize_stream(
        self,
        text: str,
        article_id: Optional[str] = None,
        lang: Optional[str] = None,
        voice: Optional[str] = None,
        audio_format: Optional[str] = None
    ) -> AsyncIterator[bytes]:
        """
        流式合成语音（兼容旧接口）。

        Azure Speech SDK 不暴露流式字节生成器，因此先完整合成再分块返回。
        """
        audio_bytes = await self.synthesize(
            text=text,
            article_id=article_id,
            lang=lang,
            voice=voice,
            audio_format=audio_format,
            use_cache=False,
        )
        chunk_size = 4096
        for i in range(0, len(audio_bytes), chunk_size):
            yield audio_bytes[i:i + chunk_size]

    def _synthesize_single_sync(self, ssml: str) -> bytes:
        """在线程池中执行 Azure SDK 调用。"""
        synthesizer = self._speechsdk.SpeechSynthesizer(
            speech_config=self._speech_config,
            audio_config=None,
        )
        result = synthesizer.speak_ssml_async(ssml).get()

        if result.reason == self._speechsdk.ResultReason.SynthesizingAudioCompleted:
            return result.audio_data

        cancellation = result.cancellation_details
        error_msg = cancellation.error_details if cancellation else str(result.reason)
        raise RuntimeError(f"Azure Speech TTS 合成失败: {error_msg}")

    async def _synthesize_single(self, text: str, voice: str, lang: Optional[str]) -> bytes:
        """单次 Azure Speech SDK 调用。"""
        voice_name = self._resolve_voice_name(voice, lang)
        ssml = self._build_ssml(text, voice_name)

        try:
            loop = asyncio.get_event_loop()
            return await asyncio.wait_for(
                loop.run_in_executor(_azure_tts_executor, self._synthesize_single_sync, ssml),
                timeout=self.settings.tts_segment_generation_timeout_seconds,
            )
        except asyncio.TimeoutError:
            logger.error("Azure Speech TTS 合成超时")
            raise RuntimeError("generation_timeout") from None
        except Exception as exc:
            logger.error(f"Azure Speech TTS API 调用失败: {exc}")
            error_str = str(exc)
            error_lower = error_str.lower()
            # Azure 常见错误映射
            if any(k in error_lower for k in (
                "quota", "exceeded", "usage quota", "429",
            )):
                raise RuntimeError("quota_exhausted") from exc
            if any(k in error_lower for k in ("rate limit", "rate_limit", "too many requests")):
                raise RuntimeError("rate_limited") from exc
            if any(k in error_lower for k in (
                "authentication", "unauthorized", "forbidden", "401", "403", "invalid subscription"
            )):
                raise RuntimeError("service_misconfigured") from exc
            raise

    def _split_text(self, text: str, max_length: int) -> List[str]:
        """
        按段落/句子智能分割文本（与 OpenAISpeechService 保持一致）
        """
        paragraphs = text.split('\n\n')
        segments: List[str] = []
        current_segment = ""

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            if len(para) > max_length:
                sentences = para.replace('。', '.|').replace('. ', '.|').split('|')
                for sentence in sentences:
                    sentence = sentence.strip()
                    if not sentence:
                        continue

                    if len(sentence) > max_length:
                        for i in range(0, len(sentence), max_length):
                            chunk = sentence[i:i + max_length]
                            if current_segment and len(current_segment) + len(chunk) > max_length:
                                segments.append(current_segment.strip())
                                current_segment = chunk
                            else:
                                current_segment += chunk
                    else:
                        if current_segment and len(current_segment) + len(sentence) > max_length:
                            segments.append(current_segment.strip())
                            current_segment = sentence
                        else:
                            current_segment += sentence
            else:
                if current_segment and len(current_segment) + len(para) + 2 > max_length:
                    segments.append(current_segment.strip())
                    current_segment = para + '\n\n'
                else:
                    current_segment += para + '\n\n'

        if current_segment.strip():
            segments.append(current_segment.strip())

        return segments

    def _merge_audio_files(self, audio_segments: List[bytes]) -> bytes:
        """
        合并多个 MP3 音频文件
        """
        try:
            combined = AudioSegment.empty()
            for audio_bytes in audio_segments:
                segment = AudioSegment.from_file(BytesIO(audio_bytes), format="mp3")
                combined += segment

            output = BytesIO()
            combined.export(output, format="mp3")
            logger.info(f"音频合并完成：{len(audio_segments)} 段 → MP3 格式")
            return output.getvalue()
        except Exception as exc:
            logger.error(f"音频合并失败: {exc}")
            raise

    def _get_cache_key(self, text: str, voice: str, article_id: Optional[str] = None) -> str:
        """生成缓存 key（含版本与输出格式，升级音色/码率后旧缓存自动失效）。"""
        if article_id:
            cache_key = f"{self.model}|{self.output_format_name}|{voice}|article_{article_id}"
            logger.info(f"🔑 使用 article_id 作为缓存 key: {article_id}")
            return cache_key
        else:
            content = f"{self.model}|{self.output_format_name}|{voice}|{text}"
            cache_key = hashlib.md5(content.encode('utf-8')).hexdigest()
            logger.info(f"🔑 使用 text MD5 作为缓存 key: {cache_key[:16]}...")
            return cache_key

    def _get_cache_file_path(self, cache_key: str, audio_format: Optional[str] = None) -> Path:
        """获取缓存文件路径。"""
        fmt = audio_format or self.audio_format
        return self.cache_dir / f"{cache_key}.{fmt}"

    def _get_from_cache(self, cache_key: str, audio_format: Optional[str] = None) -> Optional[bytes]:
        """从缓存读取音频。"""
        cache_file = self._get_cache_file_path(cache_key, audio_format)
        if cache_file.exists():
            try:
                with open(cache_file, 'rb') as f:
                    return f.read()
            except Exception as exc:
                logger.warning(f"缓存读取失败: {exc}")
                return None
        return None

    def _save_to_cache(self, cache_key: str, audio_data: bytes, audio_format: Optional[str] = None) -> None:
        """保存音频到缓存（原子写入）。"""
        cache_file = self._get_cache_file_path(cache_key, audio_format)
        temp_file = cache_file.with_suffix(f'.tmp.{os.getpid()}')
        try:
            with open(temp_file, 'wb') as f:
                f.write(audio_data)
            temp_file.rename(cache_file)
            logger.debug(f"缓存已保存: {cache_file.name}")
        except Exception as exc:
            temp_file.unlink(missing_ok=True)
            logger.warning(f"缓存保存失败: {exc}")

    async def transcribe(
        self,
        audio: bytes,
        lang_hint: Optional[str] = None
    ) -> str:
        """语音识别（STT）- 暂不实现。"""
        raise NotImplementedError("STT 功能暂未实现（Phase 2 计划）")
