"""
TTS stable playback manager for mobile-friendly segmented playback.

V2 goals:
- Never expose a growing total file to the browser audio element
- Prepare stable ready-made segments first
- Merge to a final stable file for later replay and Range support
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import tempfile
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from bs4 import BeautifulSoup
from pydub import AudioSegment

logger = logging.getLogger(__name__)


FIRST_PLAYABLE_MIN_SECONDS = 60
SEGMENT_RETRY_LIMIT = 2
STALE_GENERATION_SECONDS = 180
SECONDARY_SPLIT_MAX_CHARS = 180
FALLBACK_CLAUSE_CHUNK_CHARS = 120


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get_error_code(error_str: str) -> str:
    """
    将 TTS 错误映射为标准化的错误码，供前端 i18n 使用。

    避免将原始 API 错误（如 quota exceeded、rate limit 等）直接暴露给用户，
    同时保留原始错误在服务端日志中用于排查。
    """
    if not error_str:
        return "generation_failed"

    error_lower = error_str.lower()

    # OpenAI API 配额/计费相关错误
    if any(k in error_lower for k in ("insufficient_quota", "quota", "billing", "exceeded your current quota")):
        return "quota_exhausted"

    # OpenAI API 限流错误
    if any(k in error_lower for k in ("rate_limit", "rate limit", "too many requests", "429")):
        return "rate_limited"

    # OpenAI API 认证/权限错误
    if any(k in error_lower for k in ("invalid_api_key", "authentication", "unauthorized", "401", "403")):
        return "service_misconfigured"

    # 超时错误
    if any(k in error_lower for k in ("timeout", "timed out")):
        return "generation_timeout"

    # 网络/连接错误
    if any(k in error_lower for k in ("connection", "connect error", "network", "unreachable")):
        return "network_error"

    # 内容安全/审核相关
    if any(k in error_lower for k in ("content_filter", "safety", "moderation", "inappropriate")):
        return "content_not_allowed"

    # 无法归类的错误，返回通用失败码
    return "generation_failed"


def mp3_duration_seconds(audio_bytes: bytes) -> float:
    audio = AudioSegment.from_file(BytesIO(audio_bytes), format="mp3")
    return round(len(audio) / 1000.0, 3)


def merge_mp3_segments(audio_segments: List[bytes]) -> bytes:
    combined = AudioSegment.empty()
    for audio_bytes in audio_segments:
        combined += AudioSegment.from_file(BytesIO(audio_bytes), format="mp3")

    output = BytesIO()
    combined.export(output, format="mp3")
    return output.getvalue()


def sanitize_tts_text(text: str) -> str:
    clean_text = BeautifulSoup(text or "", "html.parser").get_text(separator=" ", strip=True)
    clean_text = re.sub(r"\s+\n", "\n", clean_text)
    clean_text = re.sub(r"\n{3,}", "\n\n", clean_text)
    return clean_text.strip()


def _chunk_text_by_length(text: str, chunk_size: int) -> List[str]:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")

    chunks: List[str] = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))

        # Do not insert a segment boundary inside a numeric token such as
        # ``1.23``.  Sentence-level protection cannot help when a long,
        # punctuation-free unit falls back to fixed-size chunks.
        if end < len(text):
            left = end - 1
            while left >= start and (text[left].isdigit() or text[left] == "."):
                left -= 1
            right = end
            while right < len(text) and (text[right].isdigit() or text[right] == "."):
                right += 1
            token = text[left + 1:right]
            if "." in token and any(char.isdigit() for char in token):
                token_start = left + 1
                # Prefer keeping the token in the next chunk. If it starts
                # at this chunk's beginning, keep it in the current chunk.
                end = token_start if token_start > start else right

        if end <= start:  # defensive guard for an unexpectedly long token
            end = min(start + chunk_size, len(text))
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        start = end

    return chunks


def _split_long_sentence_unit(
    text: str,
    max_chars: int = SECONDARY_SPLIT_MAX_CHARS
) -> List[str]:
    text = (text or "").strip()
    if not text:
        return []

    if len(text) <= max_chars:
        return [text]

    clauses = [
        clause.strip()
        for clause in re.split(r"(?<=[，、；：,;:])\s*", text)
        if clause.strip()
    ]

    if len(clauses) <= 1:
        return _chunk_text_by_length(text, min(max_chars, FALLBACK_CLAUSE_CHUNK_CHARS))

    units: List[str] = []
    current = ""
    for clause in clauses:
        if len(clause) > max_chars:
            if current:
                units.append(current)
                current = ""
            units.extend(_chunk_text_by_length(clause, min(max_chars, FALLBACK_CLAUSE_CHUNK_CHARS)))
            continue

        candidate = f"{current} {clause}".strip() if current else clause
        if current and len(candidate) > max_chars:
            units.append(current)
            current = clause
        else:
            current = candidate

    if current:
        units.append(current)

    return units or _chunk_text_by_length(text, min(max_chars, FALLBACK_CLAUSE_CHUNK_CHARS))


# 小数点保护哨兵：split_sentences 切分前把 "点后紧跟数字" 的 "." 临时替换掉，
# 防止小数被当作句子边界撕裂（2026-09-03 路透早报全量小数误读事故根因）。
# 覆盖 0.5 / .5 / 1.2.3 / 2026.09.02 等所有"点后跟数字"形态；句读 ". "（点后空格）不受影响。
# 使用 SOH 控制字符：非空白符（不被 strip 移除），真实文本中不存在，
# 且仅在函数内部存在（恢复后才返回），若意外泄漏进 SSML 会直接报错而非静默误读。
_DECIMAL_DOT_SENTINEL = "\x01"
_DECIMAL_DOT_RE = re.compile(r"\.(?=\d)")

# 分段算法版本：split_sentences 等文本分段逻辑变更时递增。
# 缓存 key 经由 build_cache_key 单点生成，使所有 provider 经稳定播放路径
# 生成的旧音频整体失效（provider 自身的 model 版本无法覆盖共享分段逻辑的修复）。
SEGMENT_ALGO_VERSION = "segv2"


def split_sentences(text: str) -> List[str]:
    if not text:
        return []

    paragraphs = [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]
    units: List[str] = []

    for paragraph in paragraphs:
        # 保护小数点："295.01" 中的 "." 后紧跟数字，不是句子边界；
        # 否则切分后经 " ".join 变成 "295. 01"，TTS 会先读整数、停顿、再读小数
        protected = _DECIMAL_DOT_RE.sub(_DECIMAL_DOT_SENTINEL, paragraph)
        pieces = re.split(r"(?<=[。！？!?\.])\s*", protected)
        pieces = [piece.strip() for piece in pieces if piece.strip()]
        if not pieces:
            pieces = [protected]
        for piece in pieces:
            units.extend(
                _split_long_sentence_unit(piece.replace(_DECIMAL_DOT_SENTINEL, "."))
            )

    return units


_default_manager: Optional["StableTtsPlaybackManager"] = None


def get_stable_tts_manager(settings) -> "StableTtsPlaybackManager":
    global _default_manager
    if _default_manager is None:
        _default_manager = StableTtsPlaybackManager(settings)
    return _default_manager


class StableTtsPlaybackManager:
    """Manage V2 segmented generation and final-file playback."""

    def __init__(self, settings):
        self.settings = settings
        self.cache_root = Path(settings.tts_cache_dir)
        self.cache_root.mkdir(parents=True, exist_ok=True)
        self._active_tasks: Dict[str, asyncio.Task] = {}
        self._task_guard = asyncio.Lock()
        self._manifest_lock = asyncio.Lock()
        self._segment_semaphore = asyncio.Semaphore(
            getattr(settings, "tts_segment_generation_concurrency", 3)
        )
        self.segment_timeout_seconds = max(
            0.1,
            float(getattr(settings, "tts_segment_generation_timeout_seconds", 45) or 45)
        )

    @property
    def first_playable_min_seconds(self) -> int:
        return getattr(self.settings, "tts_first_playable_min_seconds", 45)

    @property
    def segment_target_first(self) -> int:
        return getattr(self.settings, "tts_segment_target_first", 140)

    @property
    def first_segments_parallel_count(self) -> int:
        return getattr(self.settings, "tts_first_segments_parallel_count", 1)

    def prepare_text(self, raw_text: str) -> str:
        clean_text = sanitize_tts_text(raw_text)
        if not clean_text:
            raise ValueError("文章内容为空")

        if len(clean_text) > self.settings.tts_max_article_length:
            if self.settings.tts_long_article_strategy == "reject":
                raise ValueError(
                    f"文本过长（{len(clean_text)} 字符，限制 {self.settings.tts_max_article_length}）"
                )
            if self.settings.tts_long_article_strategy == "truncate":
                clean_text = clean_text[:self.settings.tts_max_article_length]
                logger.warning(
                    "TTS 文本过长，已截断到 %s 字符",
                    self.settings.tts_max_article_length
                )

        return clean_text

    def normalize_voice(self, speech_service: Any, voice: Optional[str]) -> str:
        if hasattr(speech_service, "_validate_voice"):
            return speech_service._validate_voice(voice)
        if voice:
            return voice
        return getattr(
            speech_service,
            "default_voice",
            getattr(speech_service, "voice_name", self.settings.openai_tts_voice)
        )

    def build_cache_key(
        self,
        speech_service: Any,
        clean_text: str,
        voice: str,
        article_id: str
    ) -> str:
        # 前缀分段算法版本：分段逻辑修复时递增，使所有 provider 旧缓存整体失效
        return f"{SEGMENT_ALGO_VERSION}|{speech_service._get_cache_key(clean_text, voice, article_id)}"

    def get_cache_dir(self, cache_key: str) -> Path:
        return self.cache_root / cache_key

    def get_manifest_path(self, cache_key: str) -> Path:
        return self.get_cache_dir(cache_key) / "manifest.json"

    def get_segment_path(self, cache_key: str, index: int) -> Path:
        return self.get_cache_dir(cache_key) / f"segment_{index:03d}.mp3"

    def get_final_path(self, cache_key: str) -> Path:
        return self.get_cache_dir(cache_key) / "final.mp3"

    def get_legacy_final_path(self, speech_service: Any, cache_key: str) -> Path:
        if hasattr(speech_service, "_get_cache_file_path"):
            return speech_service._get_cache_file_path(cache_key, "mp3")
        return self.cache_root / f"{cache_key}.mp3"

    def resolve_final_path(self, speech_service: Any, cache_key: str) -> Optional[Path]:
        final_path = self.get_final_path(cache_key)
        if final_path.exists():
            return final_path

        legacy_path = self.get_legacy_final_path(speech_service, cache_key)
        if legacy_path.exists():
            return legacy_path

        return None

    def _read_manifest(self, cache_key: str) -> Optional[Dict[str, Any]]:
        manifest_path = self.get_manifest_path(cache_key)
        if not manifest_path.exists():
            return None

        try:
            return json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("读取 TTS manifest 失败: %s", exc)
            return None

    def _write_manifest(self, cache_key: str, manifest: Dict[str, Any]) -> None:
        manifest_path = self.get_manifest_path(cache_key)
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest["updated_at"] = utc_now_iso()

        fd, temp_path = tempfile.mkstemp(
            prefix="manifest_",
            suffix=".json",
            dir=str(manifest_path.parent)
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(manifest, handle, ensure_ascii=False, indent=2)
            os.replace(temp_path, manifest_path)
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    def _split_text_for_segments(self, clean_text: str, max_chars: int) -> List[str]:
        units = split_sentences(clean_text)
        if not units:
            return [clean_text]

        targets = [self.segment_target_first, 420, 420]
        default_target = 700

        segments: List[str] = []
        current_units: List[str] = []

        def current_target() -> int:
            idx = len(segments)
            target = targets[idx] if idx < len(targets) else default_target
            return min(target, max_chars)

        def flush() -> None:
            if current_units:
                segment_text = " ".join(current_units).strip()
                if segment_text:
                    segments.append(segment_text)
                current_units.clear()

        min_first_chars = max(80, int(self.first_playable_min_seconds / 0.21))

        for unit in units:
            if len(unit) > max_chars:
                flush()
                start = 0
                while start < len(unit):
                    chunk_size = current_target()
                    chunk = unit[start:start + chunk_size].strip()
                    if chunk:
                        segments.append(chunk)
                    start += chunk_size
                continue

            candidate = " ".join(current_units + [unit]).strip()
            if current_units and len(candidate) > current_target():
                current_text = " ".join(current_units).strip()
                if len(segments) == 0 and len(current_text) < min_first_chars:
                    pass
                else:
                    flush()

            current_units.append(unit)

        flush()

        return segments or [clean_text[:max_chars]]

    def _recompute_manifest(self, manifest: Dict[str, Any]) -> Dict[str, Any]:
        offset = 0.0
        contiguous_ready_duration = 0.0
        contiguous = True
        ready_count = 0
        total_duration = 0.0

        for segment in manifest["segments"]:
            if segment["status"] == "ready" and segment.get("duration_sec") is not None:
                start_offset = round(offset, 3)
                end_offset = round(offset + float(segment["duration_sec"]), 3)
                segment["start_offset_sec"] = start_offset
                segment["end_offset_sec"] = end_offset
                offset = end_offset
                ready_count += 1
                total_duration += float(segment["duration_sec"])
                if contiguous:
                    contiguous_ready_duration = end_offset
            else:
                segment["start_offset_sec"] = None
                segment["end_offset_sec"] = None
                contiguous = False

        final_ready = bool(manifest.get("final_ready"))
        manifest["segments_total"] = len(manifest["segments"])
        manifest["segments_ready"] = ready_count
        manifest["ready_duration_sec"] = round(contiguous_ready_duration, 3)
        manifest["first_playable_ready"] = final_ready or contiguous_ready_duration >= self.first_playable_min_seconds
        manifest["playback_mode"] = "final" if final_ready else "segmented"

        # next_ready_index = first non-ready segment index (not ready_count)
        next_ready_index = None
        for idx, segment in enumerate(manifest["segments"]):
            if segment["status"] != "ready":
                next_ready_index = idx
                break
        manifest["next_ready_index"] = next_ready_index

        manifest["total_duration_sec"] = round(total_duration, 3) if final_ready else None
        return manifest

    def _build_initial_manifest(
        self,
        article_id: str,
        cache_key: str,
        voice: str,
        clean_text: str
    ) -> Dict[str, Any]:
        segment_texts = self._split_text_for_segments(
            clean_text,
            max_chars=min(self.settings.tts_max_chars_per_request, 900)
        )
        now = utc_now_iso()

        manifest = {
            "article_id": int(article_id) if str(article_id).isdigit() else article_id,
            "cache_key": cache_key,
            "voice": voice,
            "status": "generating",
            "playback_mode": "segmented",
            "segments_total": len(segment_texts),
            "segments_ready": 0,
            "ready_duration_sec": 0,
            "first_playable_ready": False,
            "final_ready": False,
            "created_at": now,
            "updated_at": now,
            "error_info": None,
            "retry_count": 0,
            "next_ready_index": 0,
            "total_duration_sec": None,
            "usage_recorded": False,
            "segments": [
                {
                    "index": index,
                    "status": "pending",
                    "text_length": len(segment_text),
                    "duration_sec": None,
                    "start_offset_sec": None,
                    "end_offset_sec": None,
                    "bytes": None,
                    "error_info": None,
                    "retry_count": 0
                }
                for index, segment_text in enumerate(segment_texts)
            ]
        }
        return self._recompute_manifest(manifest)

    def _task_is_active(self, cache_key: str) -> bool:
        task = self._active_tasks.get(cache_key)
        if not task:
            return False
        if task.done():
            self._active_tasks.pop(cache_key, None)
            return False
        return True

    def _manifest_is_stale(self, manifest: Dict[str, Any]) -> bool:
        updated_at = manifest.get("updated_at")
        if not updated_at:
            return False
        try:
            updated = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
        except ValueError:
            return False
        age = (datetime.now(timezone.utc) - updated).total_seconds()
        return age > STALE_GENERATION_SECONDS

    def _build_response(
        self,
        cache_key: str,
        final_path: Optional[Path],
        manifest: Optional[Dict[str, Any]] = None,
        status_override: Optional[str] = None
    ) -> Dict[str, Any]:
        if final_path and final_path.exists():
            return {
                "status": status_override or "hit",
                "playback_mode": "final",
                "first_playable_ready": True,
                "final_ready": True,
                "segments_total": manifest["segments_total"] if manifest else 0,
                "segments_ready": manifest["segments_ready"] if manifest else 0,
                "ready_duration_sec": manifest["ready_duration_sec"] if manifest else None,
                "next_ready_index": None,
                "total_duration_sec": manifest.get("total_duration_sec") if manifest else None,
                "error": None,
                "error_info": None,
                "cache_key": cache_key,
                "segments": manifest["segments"] if manifest else []
            }

        if not manifest:
            return {
                "status": status_override or "idle",
                "playback_mode": "segmented",
                "first_playable_ready": False,
                "final_ready": False,
                "segments_total": 0,
                "segments_ready": 0,
                "ready_duration_sec": 0,
                "next_ready_index": 0,
                "total_duration_sec": None,
                "error": None,
                "error_info": None,
                "cache_key": cache_key,
                "segments": []
            }

        return {
            "status": status_override or manifest["status"],
            "playback_mode": manifest["playback_mode"],
            "first_playable_ready": manifest["first_playable_ready"],
            "final_ready": manifest["final_ready"],
            "segments_total": manifest["segments_total"],
            "segments_ready": manifest["segments_ready"],
            "ready_duration_sec": manifest["ready_duration_sec"],
            "next_ready_index": manifest.get("next_ready_index"),
            "total_duration_sec": manifest.get("total_duration_sec"),
            "error": manifest.get("error_info"),
            "error_info": manifest.get("error_info"),
            "cache_key": cache_key,
            "segments": manifest["segments"]
        }

    async def get_status(
        self,
        speech_service: Any,
        article_id: str,
        clean_text: str,
        voice: str,
        global_article_id: Optional[int] = None,
        db_manager: Any = None
    ) -> Dict[str, Any]:
        cache_key = self.build_cache_key(speech_service, clean_text, voice, article_id)

        # 若存在 global_article_id，优先查询 tts_cache 表实现跨用户复用
        if db_manager and global_article_id:
            engine = getattr(speech_service, "model", speech_service.__class__.__name__)
            cache_entry = db_manager.get_tts_cache_entry(global_article_id, voice, engine)
            # 记录的 cache_key 必须与当前计算一致（含版本与输出格式），
            # 否则说明是旧格式/旧版本生成的记录，忽略以触发重新生成
            if cache_entry and cache_entry.get("cache_key") == cache_key:
                cache_file = Path(cache_entry["file_path"])
                if cache_file.exists():
                    manifest = self._read_manifest(cache_key)
                    return self._build_response(cache_key, cache_file, manifest)

        manifest = self._read_manifest(cache_key)
        final_path = self.resolve_final_path(speech_service, cache_key)

        if manifest and not final_path and manifest.get("status") == "generating":
            if not self._task_is_active(cache_key) and self._manifest_is_stale(manifest):
                async with self._manifest_lock:
                    # Re-read under lock to avoid racing with other writers
                    manifest = self._read_manifest(cache_key) or manifest
                    if manifest and manifest.get("status") == "generating":
                        manifest["status"] = "failed"
                        manifest["error_info"] = "generation_stale"
                        self._write_manifest(cache_key, manifest)

        manifest = self._read_manifest(cache_key) or manifest
        return self._build_response(cache_key, final_path, manifest)

    async def ensure_generation_started(
        self,
        speech_service: Any,
        article_id: str,
        clean_text: str,
        voice: str,
        global_article_id: Optional[int] = None,
        db_manager: Any = None
    ) -> Tuple[str, Dict[str, Any]]:
        cache_key = self.build_cache_key(speech_service, clean_text, voice, article_id)
        final_path = self.resolve_final_path(speech_service, cache_key)
        if final_path and final_path.exists():
            manifest = self._read_manifest(cache_key)
            return "hit", self._build_response(cache_key, final_path, manifest, status_override="hit")

        manifest = self._read_manifest(cache_key)
        if manifest is None:
            manifest = self._build_initial_manifest(article_id, cache_key, voice, clean_text)
            self._write_manifest(cache_key, manifest)
        elif manifest.get("status") == "generating" and not self._manifest_is_stale(manifest):
            return "generating", self._build_response(cache_key, None, manifest, "generating")

        async with self._task_guard:
            if self._task_is_active(cache_key):
                return "generating", self._build_response(cache_key, None, self._read_manifest(cache_key), "generating")

            manifest = self._read_manifest(cache_key) or manifest
            manifest["status"] = "generating"
            manifest["error_info"] = None
            self._write_manifest(cache_key, manifest)

            task = asyncio.create_task(
                self._generate_article_audio(
                    speech_service=speech_service,
                    article_id=article_id,
                    clean_text=clean_text,
                    voice=voice,
                    cache_key=cache_key,
                    global_article_id=global_article_id,
                    db_manager=db_manager
                )
            )
            self._active_tasks[cache_key] = task

        return "started", self._build_response(cache_key, None, self._read_manifest(cache_key), "started")

    async def _generate_segment(
        self,
        index: int,
        segment_text: str,
        speech_service: Any,
        voice: str,
        cache_key: str,
        article_id: str
    ) -> float:
        """Generate a single segment with retry logic and lock-protected manifest updates.

        Returns:
            Elapsed time in milliseconds for this segment generation.
        """
        start_time = asyncio.get_event_loop().time()
        async with self._segment_semaphore:
            segment_path = self.get_segment_path(cache_key, index)

            # Check skip: both manifest ready AND file exists
            async with self._manifest_lock:
                manifest = self._read_manifest(cache_key)
                if manifest and manifest["segments"][index]["status"] == "ready" and segment_path.exists():
                    return 0.0

            last_error: Optional[str] = None
            for attempt in range(SEGMENT_RETRY_LIMIT + 1):
                try:
                    audio_bytes = await asyncio.wait_for(
                        speech_service.synthesize(
                            text=segment_text,
                            article_id=None,
                            voice=voice,
                            audio_format="mp3",
                            use_cache=False
                        ),
                        timeout=self.segment_timeout_seconds
                    )

                    duration_sec = mp3_duration_seconds(audio_bytes)
                    temp_segment = segment_path.with_suffix(f".tmp.{os.getpid()}")
                    temp_segment.write_bytes(audio_bytes)
                    os.replace(temp_segment, segment_path)

                    # Lock-protected manifest update (success path)
                    async with self._manifest_lock:
                        manifest = self._read_manifest(cache_key)
                        if manifest:
                            segment_state = manifest["segments"][index]
                            segment_state["status"] = "ready"
                            segment_state["duration_sec"] = duration_sec
                            segment_state["bytes"] = len(audio_bytes)
                            segment_state["retry_count"] = attempt
                            # Do NOT clear manifest["error_info"] here (parallel safety)
                            manifest["retry_count"] = int(manifest.get("retry_count") or 0) + attempt
                            self._write_manifest(cache_key, self._recompute_manifest(manifest))
                    return (asyncio.get_event_loop().time() - start_time) * 1000

                except asyncio.TimeoutError:
                    last_error = f"segment_timeout after {self.segment_timeout_seconds}s"
                    logger.error(
                        "TTS segment generation timed out: article_id=%s segment=%s attempt=%s timeout=%ss",
                        article_id, index, attempt, self.segment_timeout_seconds,
                    )
                    async with self._manifest_lock:
                        manifest = self._read_manifest(cache_key)
                        if manifest:
                            segment_state = manifest["segments"][index]
                            segment_state["retry_count"] = attempt + 1
                            segment_state["error_info"] = last_error
                            manifest["retry_count"] = int(manifest.get("retry_count") or 0) + 1
                            if attempt < SEGMENT_RETRY_LIMIT:
                                segment_state["status"] = "pending"
                                self._write_manifest(cache_key, self._recompute_manifest(manifest))
                            else:
                                segment_state["status"] = "failed"
                                manifest["status"] = "failed"
                                manifest["error_info"] = f"segment_{index}_failed: {_get_error_code(last_error)}"
                                self._write_manifest(cache_key, self._recompute_manifest(manifest))
                                raise RuntimeError(last_error)
                    if attempt < SEGMENT_RETRY_LIMIT:
                        await asyncio.sleep(1.0)

                except Exception as exc:
                    last_error = str(exc)
                    logger.error(
                        "TTS segment generation failed: article_id=%s segment=%s attempt=%s error=%s",
                        article_id, index, attempt, exc,
                    )
                    async with self._manifest_lock:
                        manifest = self._read_manifest(cache_key)
                        if manifest:
                            segment_state = manifest["segments"][index]
                            segment_state["retry_count"] = attempt + 1
                            segment_state["error_info"] = last_error
                            manifest["retry_count"] = int(manifest.get("retry_count") or 0) + 1
                            if attempt < SEGMENT_RETRY_LIMIT:
                                segment_state["status"] = "pending"
                                self._write_manifest(cache_key, self._recompute_manifest(manifest))
                            else:
                                segment_state["status"] = "failed"
                                manifest["status"] = "failed"
                                manifest["error_info"] = f"segment_{index}_failed: {_get_error_code(last_error)}"
                                self._write_manifest(cache_key, self._recompute_manifest(manifest))
                                raise RuntimeError(last_error)
                    if attempt < SEGMENT_RETRY_LIMIT:
                        await asyncio.sleep(1.0)

            if last_error:
                raise RuntimeError(last_error)

    async def _generate_article_audio(
        self,
        speech_service: Any,
        article_id: str,
        clean_text: str,
        voice: str,
        cache_key: str,
        global_article_id: Optional[int] = None,
        db_manager: Any = None
    ) -> None:
        try:
            cache_dir = self.get_cache_dir(cache_key)
            cache_dir.mkdir(parents=True, exist_ok=True)

            manifest = self._read_manifest(cache_key)
            if not manifest:
                manifest = self._build_initial_manifest(article_id, cache_key, voice, clean_text)
                self._write_manifest(cache_key, manifest)

            segment_texts = self._split_text_for_segments(
                clean_text,
                max_chars=min(self.settings.tts_max_chars_per_request, 900)
            )

            parallel_count = min(self.first_segments_parallel_count, len(segment_texts))
            parallel_start_time = asyncio.get_event_loop().time()
            seg_durations_ms: List[float] = []

            # Phase 1: Parallel generation of first N segments
            if parallel_count > 0:
                tasks = []
                for i in range(parallel_count):
                    # Mark generating status before launch
                    manifest = self._read_manifest(cache_key) or manifest
                    segment_state = manifest["segments"][i]
                    segment_path = self.get_segment_path(cache_key, i)
                    if segment_state["status"] == "ready" and segment_path.exists():
                        continue
                    segment_state["status"] = "generating"
                    segment_state["error_info"] = None
                    manifest["status"] = "generating"
                    self._write_manifest(cache_key, self._recompute_manifest(manifest))

                    task = asyncio.create_task(
                        self._generate_segment(
                            i, segment_texts[i], speech_service, voice, cache_key, article_id
                        )
                    )
                    tasks.append((i, task))

                if tasks:
                    results = await asyncio.gather(
                        *[t for _, t in tasks],
                        return_exceptions=True
                    )
                    for (idx, _), result in zip(tasks, results):
                        if isinstance(result, Exception):
                            logger.error(
                                "TTS parallel segment failed: article_id=%s segment=%s error=%s",
                                article_id, idx, result
                            )
                            self._active_tasks.pop(cache_key, None)
                            return
                        seg_durations_ms.append(result)

            # Phase 2: Serial generation of remaining segments
            for i in range(parallel_count, len(segment_texts)):
                manifest = self._read_manifest(cache_key) or manifest
                segment_state = manifest["segments"][i]
                segment_path = self.get_segment_path(cache_key, i)

                if segment_state["status"] == "ready" and segment_path.exists():
                    continue

                segment_state["status"] = "generating"
                segment_state["error_info"] = None
                manifest["status"] = "generating"
                self._write_manifest(cache_key, self._recompute_manifest(manifest))

                try:
                    await self._generate_segment(
                        i, segment_texts[i], speech_service, voice, cache_key, article_id
                    )
                except Exception:
                    self._active_tasks.pop(cache_key, None)
                    return

            # Log parallel generation timing
            if parallel_count > 0 and seg_durations_ms:
                first_playable_ready_ms = max(seg_durations_ms)
                logger.info(
                    "[TTS] Segment parallel generation: "
                    "article_id=%s, parallel_count=%s, "
                    "seg0_time=%.0fms, seg1_time=%.0fms, "
                    "first_playable_ready_ms=%.0fms",
                    article_id,
                    parallel_count,
                    seg_durations_ms[0] if len(seg_durations_ms) > 0 else 0,
                    seg_durations_ms[1] if len(seg_durations_ms) > 1 else 0,
                    first_playable_ready_ms
                )

            # Merge final.mp3
            audio_segments: List[bytes] = []
            for index in range(len(segment_texts)):
                segment_path = self.get_segment_path(cache_key, index)
                if not segment_path.exists():
                    raise RuntimeError(f"segment not found: {segment_path.name}")
                audio_segments.append(segment_path.read_bytes())

            final_bytes = merge_mp3_segments(audio_segments)
            final_path = self.get_final_path(cache_key)
            temp_final = final_path.with_suffix(f".tmp.{os.getpid()}")
            temp_final.write_bytes(final_bytes)
            os.replace(temp_final, final_path)

            legacy_final = self.get_legacy_final_path(speech_service, cache_key)
            try:
                if legacy_final != final_path and legacy_final.exists():
                    legacy_final.unlink()
            except Exception as exc:
                logger.warning("清理 legacy final 音频失败: %s", exc)

            manifest = self._read_manifest(cache_key) or manifest
            manifest["status"] = "completed"
            manifest["final_ready"] = True
            manifest["error_info"] = None
            self._write_manifest(cache_key, self._recompute_manifest(manifest))

            if db_manager and global_article_id:
                try:
                    engine = getattr(speech_service, "model", speech_service.__class__.__name__)
                    db_manager.upsert_tts_cache_entry(
                        global_article_id=global_article_id,
                        voice=voice,
                        engine=engine,
                        cache_key=cache_key,
                        file_path=str(final_path),
                        file_size=int(final_path.stat().st_size),
                        duration_seconds=int(manifest.get("total_duration_sec") or 0) or None,
                        format="mp3"
                    )
                except Exception as exc:
                    logger.warning("写入 tts_cache 失败: %s", exc)
        except Exception as exc:
            logger.error("TTS final generation failed: article_id=%s error=%s", article_id, exc, exc_info=True)
            manifest = self._read_manifest(cache_key)
            if manifest:
                manifest["status"] = "failed"
                manifest["error_info"] = _get_error_code(str(exc))
                self._write_manifest(cache_key, self._recompute_manifest(manifest))
        finally:
            self._active_tasks.pop(cache_key, None)

    async def mark_usage_recorded(self, cache_key: str) -> None:
        async with self._manifest_lock:
            manifest = self._read_manifest(cache_key)
            if not manifest:
                return
            manifest["usage_recorded"] = True
            self._write_manifest(cache_key, manifest)

    async def usage_already_recorded(self, cache_key: str) -> bool:
        manifest = self._read_manifest(cache_key)
        return bool(manifest and manifest.get("usage_recorded"))
