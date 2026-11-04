"""
Google Cloud TTS 实现

使用 Google Cloud Text-to-Speech API 实现高质量语音合成
支持：缓存、自动分段、音频合并、错误处理
文档: https://cloud.google.com/text-to-speech/docs

Last updated: 2026-03-11-v3
"""
import asyncio
import hashlib
import os
from pathlib import Path
from typing import Optional, List, AsyncIterator, Tuple
from io import BytesIO
import logging
from concurrent.futures import ThreadPoolExecutor

from pydub import AudioSegment

from backend.nlp.speech_service import SpeechService

logger = logging.getLogger(__name__)

# Dedicated thread pool for Google Cloud TTS to avoid gRPC threading issues
_tts_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="google_tts_")


class GoogleSpeechService(SpeechService):
    """Google Cloud TTS 服务实现"""

    # 类级别追踪：记录正在运行的生成任务 {cache_key: Task}
    _active_producers = {}

    def __init__(self, settings):
        """
        初始化 Google Cloud TTS 服务

        Args:
            settings: 应用配置对象（core.config.settings.Settings）
        """
        self.settings = settings
        self._client = None  # 延迟初始化客户端

        # 导入 Google Cloud TTS 客户端
        try:
            from google.cloud import texttospeech
            from google.oauth2 import service_account
            self._texttospeech_module = texttospeech
            self._service_account_module = service_account
        except ImportError:
            raise ImportError(
                "Google Cloud TTS 依赖未安装。请运行: "
                "pip install google-cloud-texttospeech"
            )

        # 凭据路径（用于延迟初始化）
        self._credentials_path = settings.resolved_google_credentials_path
        self._client_initialized = False

        # 缓存目录配置
        self.cache_dir = Path(settings.tts_cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # TTS 配置
        self.voice_name = settings.google_cloud_tts_voice
        self.language_code = settings.google_cloud_tts_language_code
        self.audio_format = "mp3"  # Google TTS 输出 MP3
        # Google Cloud TTS 有 5000 字节限制（中文约 1600 字符），使用更保守的值
        self.max_chars_per_request = min(settings.tts_max_chars_per_request, 1500)
        self.max_article_length = settings.tts_max_article_length
        self.long_article_strategy = settings.tts_long_article_strategy

        # 导入 Google Cloud 类型
        from google.cloud import texttospeech
        self.texttospeech = texttospeech

        logger.info(
            f"Google TTS 服务初始化完成 "
            f"(voice={self.voice_name}, language={self.language_code}, format={self.audio_format})"
        )

    @property
    def client(self):
        """延迟初始化 Google Cloud TTS 客户端"""
        if not self._client_initialized:
            texttospeech = self._texttospeech_module
            service_account = self._service_account_module
            credentials_path = self._credentials_path

            if credentials_path and os.path.exists(credentials_path):
                import json
                try:
                    with open(credentials_path, 'r') as f:
                        creds_info = json.load(f)

                    if creds_info.get('type') == 'service_account':
                        credentials = service_account.Credentials.from_service_account_file(
                            credentials_path
                        )
                        self._client = texttospeech.TextToSpeechClient(credentials=credentials)
                        logger.info(f"使用 Google Cloud TTS 服务（服务账号凭据: {credentials_path}）")
                    else:
                        os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = credentials_path
                        self._client = texttospeech.TextToSpeechClient()
                        logger.info(f"使用 Google Cloud TTS 服务（用户授权凭据: {credentials_path}）")
                except (json.JSONDecodeError, KeyError) as e:
                    logger.warning(f"无法解析凭据文件，尝试使用默认方式: {e}")
                    self._client = texttospeech.TextToSpeechClient()
                    logger.info("使用 Google Cloud TTS 服务（默认凭据）")
            else:
                self._client = texttospeech.TextToSpeechClient()
                logger.info("使用 Google Cloud TTS 服务（默认凭据）")

            self._client_initialized = True

        return self._client

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
            article_id: 文章 ID（优先用作缓存 key，提高缓存命中率）
            lang: 语言标识（Google TTS 使用此参数选择语音）
            voice: 声线标识（覆盖默认语音）
            audio_format: 音频格式（Google TTS 只支持 mp3/ogg/opus）
            use_cache: 是否使用磁盘缓存，False 时跳过缓存读写

        Returns:
            音频二进制数据（MP3 格式）
        """
        # 1. 输入校验
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

        # 2. 检查缓存并验证 voice
        voice_to_use = voice or self.voice_name
        voice_to_use = self._validate_voice(voice_to_use)
        format_to_use = audio_format or self.audio_format
        cache_key = None

        if use_cache:
            cache_key = self._get_cache_key(text, voice_to_use, article_id)
            cached_audio = self._get_from_cache(cache_key, format_to_use)

            if cached_audio:
                logger.info(
                    f"缓存命中：{cache_key[:16]}... "
                    f"(article_id={article_id or 'N/A'}, 长度: {len(text)} 字符, 格式: {format_to_use})"
                )
                return cached_audio

        # 3. 处理超长文本（自动分段）
        if len(text) > self.max_chars_per_request:
            logger.info(
                f"[Google TTS] 文本过长（{len(text)} 字符），自动分段处理 "
                f"(每段最多 {self.max_chars_per_request} 字符)"
            )
            segments = self._split_text(text, self.max_chars_per_request)
            logger.info(f"[Google TTS] 分段结果：{len(segments)} 段")

            # 批量生成音频
            audio_segments = []
            for i, segment in enumerate(segments, 1):
                logger.info(f"[Google TTS] 正在合成第 {i}/{len(segments)} 段 ({len(segment)} 字符)...")
                try:
                    segment_audio = await self._synthesize_single(segment, voice_to_use, lang)
                    audio_segments.append(segment_audio)
                    logger.info(f"[Google TTS] 第 {i}/{len(segments)} 段合成完成")
                except Exception as e:
                    logger.error(f"[Google TTS] 第 {i}/{len(segments)} 段合成失败: {e}")
                    raise

            # 合并音频文件
            logger.info(f"正在合并 {len(audio_segments)} 段音频...")
            merged_audio = self._merge_audio_files(audio_segments)
        else:
            # 单次请求即可完成
            merged_audio = await self._synthesize_single(text, voice_to_use, lang)

        # 4. 写入缓存
        if use_cache and cache_key is not None:
            self._save_to_cache(cache_key, merged_audio, format_to_use)
            logger.info(
                f"音频合成完成：{cache_key[:16]}... "
                f"(文本长度: {len(text)} 字符, 音频大小: {len(merged_audio)} bytes, 格式: {format_to_use})"
            )
        else:
            logger.info(
                f"音频合成完成（跳过缓存）"
                f"(article_id={article_id or 'N/A'}, 文本长度: {len(text)} 字符, "
                f"音频大小: {len(merged_audio)} bytes, 格式: {format_to_use})"
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
        流式合成语音（边生成边返回）
        """
        if not text or not text.strip():
            raise ValueError("待朗读文本不能为空")

        text = text.strip()
        voice_to_use = voice or self.voice_name
        format_to_use = audio_format or self.audio_format or "mp3"

        # 长文本策略与非流式保持一致
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

        cache_key = self._get_cache_key(text, voice_to_use, article_id)

        # 1. 优先检查正常缓存（格式匹配）
        cached_audio = self._get_from_cache(cache_key, format_to_use)
        if cached_audio:
            logger.info(
                f"流式缓存命中：{cache_key[:16]}... "
                f"(article_id={article_id or 'N/A'}, 长度: {len(text)} 字符)"
            )
            chunk_size = 4096
            for i in range(0, len(cached_audio), chunk_size):
                yield cached_audio[i:i + chunk_size]
            return

        # 2. 缓存未命中，开始流式生成
        logger.info(f"缓存未命中，开始流式生成 TTS (article_id={article_id or 'N/A'})")

        # Google TTS 不支持真正的流式生成，使用 synthesize 后分块返回
        audio_data = await self.synthesize(text, article_id, lang, voice, audio_format)
        chunk_size = 4096
        for i in range(0, len(audio_data), chunk_size):
            yield audio_data[i:i + chunk_size]

    async def _synthesize_single(
        self,
        text: str,
        voice: str,
        lang: Optional[str] = None
    ) -> bytes:
        """
        单次 Google Cloud TTS API 调用

        Args:
            text: 待朗读文本（已确保长度符合限制）
            voice: 声线标识
            lang: 语言代码

        Returns:
            音频二进制数据（MP3 格式）
        """
        try:
            # 构建合成输入
            synthesis_input = self.texttospeech.SynthesisInput(text=text)

            # 构建语音参数
            language_code = lang or self.language_code
            voice_params = self.texttospeech.VoiceSelectionParams(
                language_code=language_code,
                name=voice
            )

            # 构建音频配置（MP3 格式）
            audio_config = self.texttospeech.AudioConfig(
                audio_encoding=self.texttospeech.AudioEncoding.MP3
            )

            logger.info(f"[Google TTS] 调用 API: voice={voice}, lang={language_code}, text_len={len(text)}")

            # 调用 API（使用专用线程池 + 30 秒超时）
            # 使用专用线程池避免与 gRPC 内部线程模型冲突
            loop = asyncio.get_event_loop()
            response = await asyncio.wait_for(
                loop.run_in_executor(
                    _tts_executor,
                    self._sync_synthesize_speech,
                    synthesis_input,
                    voice_params,
                    audio_config
                ),
                timeout=30.0
            )

            logger.info(f"[Google TTS] API 调用成功: audio_len={len(response)}")
            return response

        except asyncio.TimeoutError:
            logger.error(f"[Google TTS] API 调用超时 (30s): voice={voice}")
            raise RuntimeError("Google Cloud TTS API 调用超时，请检查网络连接或 API 配额")
        except Exception as e:
            logger.error(f"Google Cloud TTS API 调用失败: {e}")
            raise

    def _sync_synthesize_speech(self, synthesis_input, voice_params, audio_config):
        """同步调用 Google Cloud TTS API（在线程池中执行）

        注意：每个线程创建独立的 gRPC 客户端，避免线程安全问题
        立即提取音频内容返回，避免跨线程访问 gRPC 响应对象
        """
        from google.cloud import texttospeech

        # 在线程中创建新的客户端实例（避免跨线程共享 gRPC 通道）
        client = texttospeech.TextToSpeechClient()
        response = client.synthesize_speech(
            input=synthesis_input,
            voice=voice_params,
            audio_config=audio_config
        )
        # 立即提取音频内容，避免跨线程访问 gRPC 响应对象
        return response.audio_content

    def _split_text(self, text: str, max_length: int) -> List[str]:
        """
        按段落智能分割文本

        策略：
        1. 优先按双换行符（段落）分割
        2. 段落过长时，按句号分割
        3. 确保每段不超过 max_length
        """
        # 按段落分割
        paragraphs = text.split('\n\n')

        segments = []
        current_segment = ""

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            # 如果当前段落本身就超长，需要进一步分割
            if len(para) > max_length:
                # 按句号分割（支持中英文句号）
                sentences = para.replace('。', '.|').replace('. ', '.|').split('|')

                for sentence in sentences:
                    sentence = sentence.strip()
                    if not sentence:
                        continue

                    # 句子过长，强制截断（避免无限循环）
                    if len(sentence) > max_length:
                        for i in range(0, len(sentence), max_length):
                            chunk = sentence[i:i + max_length]
                            if current_segment and len(current_segment) + len(chunk) > max_length:
                                segments.append(current_segment.strip())
                                current_segment = chunk
                            else:
                                current_segment += chunk
                    else:
                        # 句子长度合理，尝试累积到当前段
                        if current_segment and len(current_segment) + len(sentence) > max_length:
                            segments.append(current_segment.strip())
                            current_segment = sentence
                        else:
                            current_segment += sentence

            else:
                # 段落长度合理，尝试累积到当前段
                if current_segment and len(current_segment) + len(para) + 2 > max_length:
                    # 当前段已满，保存并开始新段
                    segments.append(current_segment.strip())
                    current_segment = para + '\n\n'
                else:
                    # 累积到当前段
                    current_segment += para + '\n\n'

        # 保存最后一段
        if current_segment.strip():
            segments.append(current_segment.strip())

        return segments

    def _merge_audio_files(self, audio_segments: List[bytes]) -> bytes:
        """
        合并多个音频文件（使用 pydub）

        Args:
            audio_segments: 音频二进制数据列表

        Returns:
            合并后的音频二进制数据
        """
        try:
            combined = AudioSegment.empty()

            for audio_bytes in audio_segments:
                segment = AudioSegment.from_file(
                    BytesIO(audio_bytes),
                    format="mp3"
                )
                combined += segment

            # 导出为 MP3
            output = BytesIO()
            combined.export(output, format="mp3")
            logger.info(
                f"音频合并完成：{len(audio_segments)} 段 → MP3 格式"
            )
            return output.getvalue()

        except Exception as e:
            logger.error(f"音频合并失败: {e}")
            raise

    def _get_cache_key(self, text: str, voice: str, article_id: Optional[str] = None) -> str:
        """
        生成缓存 key

        优先策略：
        1. 如果提供 article_id，使用 article_id 作为缓存 key（最优，前后端一致）
        2. 如果没有 article_id，使用 text MD5 哈希（兜底方案）
        """
        if article_id:
            # 优先使用 article_id 作为缓存 key
            # 包含模型和声线，确保不同配置的音频不会冲突
            cache_key = f"google|{voice}|article_{article_id}"
            logger.info(f"使用 article_id 作为缓存 key: {article_id}")
            return cache_key
        else:
            # 兜底：使用 text MD5（适用于无 article_id 的场景，如预览）
            content = f"google|{voice}|{text}"
            cache_key = hashlib.md5(content.encode('utf-8')).hexdigest()
            logger.info(f"使用 text MD5 作为缓存 key: {cache_key[:16]}...")
            return cache_key

    def _get_cache_file_path(self, cache_key: str, audio_format: Optional[str] = None) -> Path:
        """
        获取缓存文件路径（支持不同音频格式）
        """
        fmt = audio_format or self.audio_format
        return self.cache_dir / f"{cache_key}.{fmt}"

    def _get_from_cache(self, cache_key: str, audio_format: Optional[str] = None) -> Optional[bytes]:
        """
        从缓存读取音频
        """
        cache_file = self._get_cache_file_path(cache_key, audio_format)

        if cache_file.exists():
            try:
                with open(cache_file, 'rb') as f:
                    return f.read()
            except Exception as e:
                logger.warning(f"缓存读取失败: {e}")
                return None

        return None

    def _save_to_cache(self, cache_key: str, audio_data: bytes, audio_format: Optional[str] = None) -> None:
        """
        保存音频到缓存（原子写入，避免并发冲突）
        """
        cache_file = self._get_cache_file_path(cache_key, audio_format)

        # 原子写入：先写临时文件，再 rename（原子操作）
        temp_file = cache_file.with_suffix(f'.tmp.{os.getpid()}')
        try:
            with open(temp_file, 'wb') as f:
                f.write(audio_data)

            # 原子操作：rename
            temp_file.rename(cache_file)
            logger.debug(f"缓存已保存: {cache_file.name}")
        except Exception as e:
            # 清理失败的临时文件
            temp_file.unlink(missing_ok=True)
            logger.warning(f"缓存保存失败: {e}")

    async def stream_and_save(
        self,
        article_id: str,
        text: str,
        voice: Optional[str] = None,
        metadata: Optional[dict] = None,
        request = None,
        start_byte: int = 0,
        end_byte: int = None
    ) -> AsyncIterator[bytes]:
        """
        流式透传 + 异步保存（简化版，用于兼容 API 端点）

        与 OpenAI 版本不同，Google TTS 不支持真正的流式生成，
        所以这里先完整生成后分块返回。
        """
        from bs4 import BeautifulSoup

        # 清洗 HTML 标签
        clean_text = BeautifulSoup(text, "html.parser").get_text(separator=' ', strip=True)
        clean_text = clean_text.strip()

        if not clean_text:
            raise ValueError("文章内容为空")

        # 检查总长度限制
        if len(clean_text) > self.max_article_length:
            if self.long_article_strategy == "reject":
                raise ValueError(f"文本过长（{len(clean_text)} 字符，限制 {self.max_article_length}）")
            elif self.long_article_strategy == "truncate":
                clean_text = clean_text[:self.max_article_length]
                logger.warning(f"文本过长，已截断到 {self.max_article_length} 字符")

        # 验证 voice 是否有效
        voice_to_use = self._validate_voice(voice)

        cache_key = self._get_cache_key(clean_text, voice_to_use, article_id)

        final_path = self._get_cache_file_path(cache_key, "mp3")

        # 检查缓存
        cached_audio = self._get_from_cache(cache_key, "mp3")
        if cached_audio:
            logger.info(f"♻️ [Google TTS] 缓存命中: {article_id}")
            chunk_size = 4096
            for i in range(start_byte, len(cached_audio), chunk_size):
                yield cached_audio[i:i + chunk_size]
            return

        # 缓存未命中，生成音频
        logger.info(f"🚀 [Google TTS] 开始生成: {article_id}")

        try:
            audio_data = await self.synthesize(clean_text, article_id, None, voice_to_use, "mp3")

            # 分块返回
            chunk_size = 4096
            for i in range(start_byte, len(audio_data), chunk_size):
                yield audio_data[i:i + chunk_size]

            logger.info(f"✅ [Google TTS] 生成完成: {article_id} ({len(audio_data)} bytes)")

        except Exception as e:
            logger.error(f"❌ [Google TTS] 生成失败: {article_id}, error={e}")
            raise

    def _validate_voice(self, voice: Optional[str]) -> str:
        """
        验证并转换 voice 参数

        Google Cloud TTS 的 voice 格式为 "cmn-CN-Standard-A"
        如果传入的是 OpenAI voice（如 "nova", "alloy" 等），则使用默认 Google voice

        Args:
            voice: 传入的 voice 参数

        Returns:
            有效的 Google Cloud TTS voice 名称
        """
        if voice and voice.startswith("cmn-"):
            # 已经是有效的 Google voice 格式
            return voice

        # 如果是 OpenAI voice 或无效值，使用默认 Google voice
        if voice and voice not in ["nova", "alloy", "echo", "fable", "onyx", "shimmer"]:
            # 可能是有效的 Google voice，尝试使用
            return voice

        # 使用默认 Google voice
        logger.info(f"[Google TTS] 传入的 voice '{voice}' 不是有效的 Google voice，使用默认值: {self.voice_name}")
        return self.voice_name

    async def transcribe(
        self,
        audio: bytes,
        lang_hint: Optional[str] = None
    ) -> str:
        """
        语音识别（STT）- 暂未实现
        """
        raise NotImplementedError("STT 功能暂未实现（Phase 2 计划）")
