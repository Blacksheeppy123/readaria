"""
OpenAI TTS 实现

使用 OpenAI Audio Speech API 实现高质量语音合成
支持：缓存、自动分段、音频合并、错误处理
"""
import asyncio
import hashlib
import os
from pathlib import Path
from typing import Optional, List, AsyncIterator, Tuple
from io import BytesIO
import logging

from openai import AsyncOpenAI
from pydub import AudioSegment

from backend.nlp.speech_service import SpeechService

logger = logging.getLogger(__name__)


class OpenAISpeechService(SpeechService):
    """OpenAI TTS 服务实现"""

    # ✅ 类级别追踪：记录正在运行的生成任务 {cache_key: Task}
    _active_producers = {}

    def __init__(self, settings):
        """
        初始化 Azure OpenAI TTS 服务

        Args:
            settings: 应用配置对象（core.config.settings.Settings）
        """
        self.settings = settings

        # 根据 TTS_PROVIDER 配置选择使用 Azure 还是 OpenAI
        # 默认优先使用 OpenAI（Azure 订阅已取消）
        tts_provider = getattr(settings, 'tts_provider', 'openai').lower()
        use_azure = (tts_provider == 'azure' and
                     settings.azure_openai_tts_endpoint and
                     settings.azure_openai_tts_api_key)

        if use_azure:
            from openai import AsyncAzureOpenAI
            self.client = AsyncAzureOpenAI(
                azure_endpoint=settings.azure_openai_tts_endpoint,
                api_key=settings.azure_openai_tts_api_key,
                api_version=settings.azure_openai_api_version
            )
            # Azure OpenAI 使用部署名称
            self.model = settings.azure_openai_tts_deployment
            self.is_azure = True
            logger.info(
                f"使用 Azure OpenAI TTS 服务 "
                f"(endpoint={settings.azure_openai_tts_endpoint}, "
                f"deployment={self.model})"
            )
        else:
            from openai import AsyncOpenAI
            self.client = AsyncOpenAI(
                api_key=settings.openai_api_key,
                base_url=settings.openai_base_url
            )
            # OpenAI 使用模型名称
            self.model = settings.openai_tts_model
            self.is_azure = False
            logger.info(
                f"使用 OpenAI TTS 服务 "
                f"(model={self.model})"
            )

        # 缓存目录配置
        self.cache_dir = Path(settings.tts_cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # TTS 配置
        self.default_voice = settings.openai_tts_voice
        self.audio_format = settings.openai_tts_format
        self.max_chars_per_request = settings.tts_max_chars_per_request
        self.max_article_length = settings.tts_max_article_length
        self.long_article_strategy = settings.tts_long_article_strategy

        logger.info(
            f"TTS 服务初始化完成 "
            f"(provider={'Azure' if self.is_azure else 'OpenAI'}, "
            f"model={self.model}, voice={self.default_voice}, format={self.audio_format})"
        )

    async def synthesize(
        self,
        text: str,
        article_id: Optional[str] = None,
        lang: Optional[str] = None,
        voice: Optional[str] = None,
        audio_format: Optional[str] = None,  # ✅ 新增格式参数
        use_cache: bool = True,
    ) -> bytes:
        """
        合成语音（TTS）

        Args:
            text: 待朗读文本
            article_id: 文章 ID（优先用作缓存 key，提高缓存命中率）
            lang: 语言标识（OpenAI TTS 支持多语言自动识别，此参数暂未使用）
            voice: 声线标识（默认使用配置中的 default_voice）
            audio_format: 音频格式（aac/mp3/opus，默认使用 self.audio_format）
            use_cache: 是否使用磁盘缓存，False 时跳过缓存读写

        Returns:
            音频二进制数据

        Raises:
            ValueError: 文本过长或为空
            Exception: OpenAI API 调用失败
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

        # 2. 检查缓存
        voice_to_use = voice or self.default_voice
        format_to_use = audio_format or self.audio_format  # ✅ 使用传入的格式
        cache_key = None

        if use_cache:
            cache_key = self._get_cache_key(text, voice_to_use, article_id)
            cached_audio = self._get_from_cache(cache_key, format_to_use)  # ✅ 传递格式参数

            if cached_audio:
                logger.info(
                    f"✅ 缓存命中：{cache_key[:16]}... "
                    f"(article_id={article_id or 'N/A'}, 长度: {len(text)} 字符, 格式: {format_to_use})"
                )
                return cached_audio

        # 3. 处理超长文本（自动分段）
        if len(text) > self.max_chars_per_request:
            logger.info(
                f"文本过长（{len(text)} 字符），自动分段处理 "
                f"(每段最多 {self.max_chars_per_request} 字符)"
            )
            segments = self._split_text(text, self.max_chars_per_request)
            logger.info(f"分段结果：{len(segments)} 段")

            # 批量生成音频
            audio_segments = []
            for i, segment in enumerate(segments, 1):
                logger.info(f"正在合成第 {i}/{len(segments)} 段 ({len(segment)} 字符)...")
                segment_audio = await self._synthesize_single(segment, voice_to_use, format_to_use)  # ✅ 传递格式
                audio_segments.append(segment_audio)

            # 合并音频文件
            logger.info(f"正在合并 {len(audio_segments)} 段音频...")
            merged_audio = self._merge_audio_files(audio_segments)
        else:
            # 单次请求即可完成
            merged_audio = await self._synthesize_single(text, voice_to_use, format_to_use)  # ✅ 传递格式

        # 4. 写入缓存
        if use_cache and cache_key is not None:
            self._save_to_cache(cache_key, merged_audio, format_to_use)  # ✅ 传递格式参数
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
        voice_to_use = voice or self.default_voice
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
                f"✅ 流式缓存命中：{cache_key[:16]}... "
                f"(article_id={article_id or 'N/A'}, 长度: {len(text)} 字符)"
            )
            chunk_size = 4096
            for i in range(0, len(cached_audio), chunk_size):
                yield cached_audio[i:i + chunk_size]
            return

        # 2. 缓存未命中，开始流式生成
        logger.info(f"⚠️ 缓存未命中，开始流式生成 TTS (article_id={article_id or 'N/A'})")

        # 注意：synthesize_stream 已废弃，新架构使用统一的 stream_and_save 方法
        # 这个方法保留是为了向后兼容，实际应该使用 stream_and_save
        raise NotImplementedError(
            "synthesize_stream 已废弃，请使用新的统一播放接口 /api/v1/tts/play/{article_id}"
        )

    async def _synthesize_single(self, text: str, voice: str, audio_format: str) -> bytes:
        """
        单次 OpenAI API 调用（不超过 max_chars_per_request）

        Args:
            text: 待朗读文本（已确保长度符合限制）
            voice: 声线标识
            audio_format: 音频格式（aac/mp3/opus 等）

        Returns:
            音频二进制数据

        Raises:
            Exception: OpenAI API 调用失败
        """
        try:
            response = await self.client.audio.speech.create(
                model=self.model,
                voice=voice,
                input=text,
                response_format=audio_format  # ✅ 使用传入的格式
            )

            # response.content 是 bytes
            return response.content

        except Exception as e:
            logger.error(f"OpenAI TTS API 调用失败: {e}")
            # 包装 OpenAI 配额/限流错误，返回标准化错误码供前端 i18n 使用
            error_str = str(e)
            error_lower = error_str.lower()
            if any(k in error_lower for k in ("insufficient_quota", "quota", "billing", "exceeded your current quota")):
                raise RuntimeError("quota_exhausted") from e
            if any(k in error_lower for k in ("rate_limit", "rate limit", "too many requests", "429")):
                raise RuntimeError("rate_limited") from e
            if any(k in error_lower for k in ("invalid_api_key", "authentication", "unauthorized", "401", "403")):
                raise RuntimeError("service_misconfigured") from e
            raise

    async def _stream_single(self, text: str, voice: str, audio_format: str) -> AsyncIterator[bytes]:
        """
        使用 OpenAI streaming API 进行单段音频流式生成
        """
        try:
            async with self.client.audio.speech.with_streaming_response.create(
                model=self.model,
                voice=voice,
                input=text,
                response_format=audio_format
            ) as response:
                async for chunk in response.iter_bytes(chunk_size=4096):
                    if chunk:
                        yield chunk
        except Exception as e:
            logger.error(f"OpenAI TTS streaming 调用失败: {e}")
            raise

    def _split_text(self, text: str, max_length: int) -> List[str]:
        """
        按段落智能分割文本

        策略：
        1. 优先按双换行符（段落）分割
        2. 段落过长时，按句号分割
        3. 确保每段不超过 max_length

        Args:
            text: 待分割文本
            max_length: 每段最大长度（字符数）

        Returns:
            分段后的文本列表
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

    def _strip_id3_header(self, data: bytes) -> Tuple[bytes, bool, bool]:
        """
        去除 MP3 片段开头的 ID3 头（用于分段拼接时避免重复头部）

        Returns:
            (stripped_data, header_processed, need_more)
        """
        if len(data) < 10:
            return data, False, True

        if data[0:3] == b"ID3":
            # ID3v2 头大小：4 字节同步安全整数（不含 10 字节头）
            size_bytes = data[6:10]
            tag_size = (
                (size_bytes[0] & 0x7F) << 21 |
                (size_bytes[1] & 0x7F) << 14 |
                (size_bytes[2] & 0x7F) << 7 |
                (size_bytes[3] & 0x7F)
            )
            total_header = 10 + tag_size
            if len(data) < total_header:
                return b"", False, True
            return data[total_header:], True, False

        # 无 ID3 头，直接返回
        return data, True, False

    def _merge_audio_files(self, audio_segments: List[bytes]) -> bytes:
        """
        合并多个音频文件（使用 pydub）

        Args:
            audio_segments: 音频二进制数据列表

        Returns:
            合并后的音频二进制数据

        Raises:
            Exception: 音频合并失败
        """
        try:
            combined = AudioSegment.empty()

            for audio_bytes in audio_segments:
                segment = AudioSegment.from_file(
                    BytesIO(audio_bytes),
                    format="mp3"  # 统一使用 MP3
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

    async def _producer_task(
        self,
        clean_text: str,
        voice: str,
        temp_path: Path,
        final_path: Path,
        cache_key: str
    ) -> None:
        """
        生产者任务：负责拉取数据并写入临时文件
        """
        response_ctx_short = None
        response_ctx_long = None

        try:
            logger.info(f"🚀 [Producer] 任务开始: {temp_path.name}")

            # 步骤 3: 检测是否需要分段
            if len(clean_text) <= self.max_chars_per_request:
                # 短文本
                response_ctx_short = self.client.audio.speech.with_streaming_response.create(
                    model=self.model,
                    voice=voice,
                    input=clean_text,
                    response_format="mp3"
                )
                async with response_ctx_short as response:
                    async for chunk in response.iter_bytes(chunk_size=4096):
                        if chunk:
                            # 追加写入临时文件
                            with open(temp_path, 'ab') as f:
                                f.write(chunk)
            else:
                # 长文本：分段生成，去除重复 ID3 头后串流到同一文件
                segments = self._split_text(clean_text, self.max_chars_per_request)
                first_segment = True

                for i, segment in enumerate(segments, 1):
                    header_processed = False
                    pending = b""

                    response_ctx_long = self.client.audio.speech.with_streaming_response.create(
                        model=self.model,
                        voice=voice,
                        input=segment,
                        response_format="mp3"
                    )
                    async with response_ctx_long as response:
                        async for chunk in response.iter_bytes(chunk_size=4096):
                            if not chunk:
                                continue

                            # 第一段保留完整头部，直接写
                            if first_segment:
                                with open(temp_path, 'ab') as f:
                                    f.write(chunk)
                                continue

                            # 后续段落：去掉 ID3 头
                            if not header_processed:
                                pending += chunk
                                stripped, header_processed, need_more = self._strip_id3_header(pending)

                                if not header_processed and need_more:
                                    # 继续累积直到头部够长
                                    continue

                                if stripped:
                                    with open(temp_path, 'ab') as f:
                                        f.write(stripped)
                                pending = b""
                                continue

                            # 头部已处理，直接写入
                            with open(temp_path, 'ab') as f:
                                f.write(chunk)

                    first_segment = False
                    # ✅ 给 HTTP 连接释放时间
                    await asyncio.sleep(0)

            # 生成完成，重命名为正式文件（原子操作）
            if temp_path.exists():
                temp_path.rename(final_path)
                logger.info(f"✅ [Producer] 任务完成，缓存已保存: {final_path.name}")
            else:
                # 临时文件不存在，说明生成过程中出现了未捕获的问题
                raise RuntimeError(f"临时文件未生成: {temp_path}")

        except Exception as e:
            logger.error(f"❌ [Producer] 任务失败: {e}", exc_info=True)
            # 清理临时文件
            if temp_path.exists():
                temp_path.unlink()
            # ✅ 重新抛出异常，让调用方感知到失败
            raise
        finally:
            # ✅ 任务结束，移除注册
            self._active_producers.pop(cache_key, None)
            # ✅ 给事件循环机会处理未决的 I/O 操作（特别是 HTTP 连接清理）
            try:
                await asyncio.sleep(0)
            except Exception:
                pass

    async def _file_tailer(self, temp_path: Path, final_path: Path, start_byte: int = 0, end_byte: int = None, cache_key: str = None) -> AsyncIterator[bytes]:
        """
        文件追踪生成器：读取正在写入的文件
        """
        import asyncio
        
        # 等待文件创建（最多等待 5 秒）
        for _ in range(50):
            if temp_path.exists() or final_path.exists():
                break
            await asyncio.sleep(0.1)
        
        # 如果最终文件已存在，直接读取
        if final_path.exists():
            with open(final_path, 'rb') as f:
                f.seek(start_byte)
                bytes_sent = 0
                while chunk := f.read(4096):
                    # 如果指定了 end_byte，进行截断
                    if end_byte is not None:
                        remaining = (end_byte - start_byte + 1) - bytes_sent
                        if remaining <= 0:
                            break
                        if len(chunk) > remaining:
                            chunk = chunk[:remaining]
                    
                    yield chunk
                    bytes_sent += len(chunk)
                    
                    if end_byte is not None and bytes_sent >= (end_byte - start_byte + 1):
                        break
            return

        # 追踪临时文件
        if not temp_path.exists():
            logger.warning(f"⚠️ [Consumer] 临时文件未找到，停止流式传输: {temp_path.name}")
            return

        current_offset = start_byte
        bytes_sent = 0
        no_new_data_count = 0
        
        while True:
            # 检查是否达到 end_byte
            if end_byte is not None and bytes_sent >= (end_byte - start_byte + 1):
                break

            # 1. 检查是否已转为正式文件
            if not temp_path.exists():
                if final_path.exists():
                    # 切换到正式文件继续读取剩余部分
                    with open(final_path, 'rb') as f:
                        f.seek(current_offset)
                        while chunk := f.read(4096):
                            # 截断逻辑
                            if end_byte is not None:
                                remaining = (end_byte - start_byte + 1) - bytes_sent
                                if remaining <= 0:
                                    break
                                if len(chunk) > remaining:
                                    chunk = chunk[:remaining]
                            
                            yield chunk
                            bytes_sent += len(chunk)
                            
                            if end_byte is not None and bytes_sent >= (end_byte - start_byte + 1):
                                break
                    break
                else:
                    logger.warning(f"⚠️ [Consumer] 临时文件意外消失: {temp_path.name}")
                    break

            # 2. 读取临时文件
            try:
                with open(temp_path, 'rb') as f:
                    f.seek(current_offset)
                    chunk = f.read(4096)
                    
                    if chunk:
                        # 截断逻辑
                        if end_byte is not None:
                            remaining = (end_byte - start_byte + 1) - bytes_sent
                            if remaining <= 0:
                                break
                            if len(chunk) > remaining:
                                chunk = chunk[:remaining]
                        
                        yield chunk
                        current_offset += len(chunk)
                        bytes_sent += len(chunk)
                        no_new_data_count = 0
                    else:
                        # 暂时没有新数据
                        no_new_data_count += 1
                        
                        # ✅ 优化：检查生产者是否还在运行
                        is_producing = cache_key in self._active_producers
                        
                        if not is_producing:
                            # 生产者已结束但文件还没转正？再等等
                            if no_new_data_count > 50: # 5秒
                                logger.warning(
                                    f"⚠️ [Consumer] 生产者已结束但文件未就绪 (offset={current_offset}, start={start_byte}): {temp_path.name}"
                                )
                                break
                        else:
                            # 生产者还在运行，可以等久一点（长文场景避免过早断流）
                            if no_new_data_count > 1200: # 120秒无数据，超时
                                logger.warning(
                                    f"⚠️ [Consumer] 读取超时（可能超前 Range 或生产者僵死）"
                                    f" offset={current_offset}, start={start_byte}, temp={temp_path.name}"
                                )
                                break
                                
                        await asyncio.sleep(0.1)
            except FileNotFoundError:
                continue
            except Exception as e:
                logger.error(f"❌ [Consumer] 读取错误: {e}")
                break

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
        流式透传 + 异步保存（Producer-Consumer 文件共享模式）
        
        支持：
        1. 多客户端共享同一个生成流（避免重复请求 OpenAI）
        2. 支持 Range 请求（断点续传/进度拖拽）
        3. 客户端断开不影响后台生成
        """
        # 步骤 1: 清洗 HTML 标签
        from bs4 import BeautifulSoup
        clean_text = BeautifulSoup(text, "html.parser").get_text(separator=' ', strip=True)
        clean_text = clean_text.strip()

        if not clean_text:
            raise ValueError("文章内容为空")

        # 步骤 2: 检查总长度限制
        if len(clean_text) > self.max_article_length:
            if self.long_article_strategy == "reject":
                raise ValueError(f"文本过长（{len(clean_text)} 字符，限制 {self.max_article_length}）")
            elif self.long_article_strategy == "truncate":
                clean_text = clean_text[:self.max_article_length]
                logger.warning(f"文本过长，已截断到 {self.max_article_length} 字符")

        voice_to_use = voice or self.default_voice
        cache_key = self._get_cache_key(clean_text, voice_to_use, article_id)
        
        final_path = self._get_cache_file_path(cache_key, "mp3")
        temp_path = final_path.with_suffix(".mp3.part")

        # 步骤 2: 检查是否需要启动 Producer
        need_producer = False
        if not final_path.exists():
            if not temp_path.exists():
                need_producer = True
            else:
                # ✅ 优化：临时文件存在，检查它是否还在被生成
                if cache_key not in self._active_producers:
                    # 检查文件年龄
                    import time
                    mtime = temp_path.stat().st_mtime
                    if time.time() - mtime > 60:
                        logger.warning(f"⚠️ 发现僵死临时文件，删除重试: {temp_path.name}")
                        try:
                            temp_path.unlink(missing_ok=True)
                            need_producer = True
                        except Exception:
                            pass # 可能被其他进程删了
                else:
                    logger.info(f"♻️ [Consumer] 加入现有流: {article_id}")

        if need_producer:
            try:
                # 独占创建临时文件（作为锁）
                with open(temp_path, 'xb') as f:
                    pass 
                
                # 启动后台任务
                task = asyncio.create_task(
                    self._producer_task(clean_text, voice_to_use, temp_path, final_path, cache_key)
                )
                self._active_producers[cache_key] = task
                logger.info(f"🚀 [Producer] 新任务启动: {article_id}")
                
            except FileExistsError:
                # 已有其他请求启动了任务，直接复用
                logger.info(f"♻️ [Consumer] 并发冲突，复用现有流: {article_id}")
            except Exception as e:
                logger.error(f"❌ 启动 Producer 失败: {e}")
                raise

        # 步骤 3: 返回文件追踪流
        async for chunk in self._file_tailer(temp_path, final_path, start_byte, end_byte, cache_key):
            yield chunk

    def _get_cache_key(self, text: str, voice: str, article_id: Optional[str] = None) -> str:
        """
        生成缓存 key

        优先策略：
        1. 如果提供 article_id，使用 article_id 作为缓存 key（最优，前后端一致）
        2. 如果没有 article_id，使用 text MD5 哈希（兜底方案）

        Args:
            text: 文本内容
            voice: 声线标识
            article_id: 文章 ID（可选）

        Returns:
            缓存 key 字符串
        """
        if article_id:
            # ✅ 优先使用 article_id 作为缓存 key
            # 包含模型和声线，确保不同配置的音频不会冲突
            cache_key = f"{self.model}|{voice}|article_{article_id}"
            logger.info(f"🔑 使用 article_id 作为缓存 key: {article_id}")
            return cache_key
        else:
            # ⚠️ 兜底：使用 text MD5（适用于无 article_id 的场景，如预览）
            content = f"{self.model}|{voice}|{text}"
            cache_key = hashlib.md5(content.encode('utf-8')).hexdigest()
            logger.info(f"🔑 使用 text MD5 作为缓存 key: {cache_key[:16]}...")
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

        Args:
            cache_key: 缓存 key
            audio_format: 音频格式

        Returns:
            音频二进制数据，未命中时返回 None
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

        Args:
            cache_key: 缓存 key
            audio_data: 音频二进制数据
            audio_format: 音频格式
        """
        cache_file = self._get_cache_file_path(cache_key, audio_format)

        # ✅ 原子写入：先写临时文件，再 rename（原子操作）
        temp_file = cache_file.with_suffix(f'.tmp.{os.getpid()}')  # 加进程 ID 避免冲突
        try:
            with open(temp_file, 'wb') as f:
                f.write(audio_data)

            # 原子操作：rename（即使多进程同时写，也只有一个成功）
            temp_file.rename(cache_file)
            logger.debug(f"缓存已保存: {cache_file.name}")
        except Exception as e:
            # 清理失败的临时文件
            temp_file.unlink(missing_ok=True)
            logger.warning(f"缓存保存失败: {e}")

    async def transcribe(
        self,
        audio: bytes,
        lang_hint: Optional[str] = None
    ) -> str:
        """
        语音识别（STT）- Phase 1 暂不实现

        Raises:
            NotImplementedError: 暂未实现
        """
        raise NotImplementedError("STT 功能暂未实现（Phase 2 计划）")
