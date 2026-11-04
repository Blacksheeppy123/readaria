import asyncio
from pathlib import Path
from types import SimpleNamespace
import sys

import pytest

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from backend.services.tts_stable_playback import StableTtsPlaybackManager, split_sentences


class FakeSpeechService:
    def __init__(self, cache_dir: str):
        self.default_voice = "nova"
        self.cache_dir = Path(cache_dir)

    def _get_cache_key(self, text, voice, article_id=None):
        return f"fake|{voice}|article_{article_id}"

    def _get_cache_file_path(self, cache_key, audio_format="mp3"):
        return self.cache_dir / f"{cache_key}.{audio_format}"

    async def synthesize(self, text, article_id=None, voice=None, audio_format=None, use_cache=True):
        return f"audio:{text}".encode("utf-8")


class SlowSpeechService(FakeSpeechService):
    async def synthesize(self, text, article_id=None, voice=None, audio_format=None, use_cache=True):
        await asyncio.sleep(0.2)
        return b"late-audio"


@pytest.fixture
def fake_settings(tmp_path):
    return SimpleNamespace(
        tts_cache_dir=str(tmp_path / "audio_cache"),
        tts_max_chars_per_request=3000,
        tts_max_article_length=30000,
        tts_long_article_strategy="segment",
        openai_tts_voice="nova",
        tts_segment_generation_timeout_seconds=1,
        tts_first_segments_parallel_count=1,
        tts_segment_generation_concurrency=3,
        tts_first_playable_min_seconds=45,
        tts_segment_target_first=140
    )


@pytest.mark.asyncio
async def test_manager_generates_manifest_segments_and_final(fake_settings, monkeypatch):
    manager = StableTtsPlaybackManager(fake_settings)
    speech_service = FakeSpeechService(fake_settings.tts_cache_dir)

    monkeypatch.setattr(
        "backend.services.tts_stable_playback.mp3_duration_seconds",
        lambda audio_bytes: 12.5
    )
    monkeypatch.setattr(
        "backend.services.tts_stable_playback.merge_mp3_segments",
        lambda segments: b"merged-audio"
    )

    text = "第一句。第二句。第三句。第四句。第五句。"
    prepare_state, response = await manager.ensure_generation_started(
        speech_service=speech_service,
        article_id="123",
        clean_text=text,
        voice="nova"
    )

    assert prepare_state == "started"
    cache_key = response["cache_key"]

    task = manager._active_tasks[cache_key]
    await task

    status = await manager.get_status(
        speech_service=speech_service,
        article_id="123",
        clean_text=text,
        voice="nova"
    )

    assert status["final_ready"] is True
    assert status["status"] == "hit"
    assert status["segments_total"] >= 1
    assert status["segments_ready"] == status["segments_total"]

    manifest_path = manager.get_manifest_path(cache_key)
    final_path = manager.get_final_path(cache_key)

    assert manifest_path.exists()
    assert final_path.exists()
    assert final_path.read_bytes() == b"merged-audio"


@pytest.mark.asyncio
async def test_manager_returns_idle_status_without_manifest(fake_settings):
    manager = StableTtsPlaybackManager(fake_settings)
    speech_service = FakeSpeechService(fake_settings.tts_cache_dir)

    status = await manager.get_status(
        speech_service=speech_service,
        article_id="999",
        clean_text="测试文本",
        voice="nova"
    )

    assert status["status"] == "idle"
    assert status["final_ready"] is False


class _FakeDbManager:
    """模拟 get_tts_cache_entry 返回固定记录。"""

    def __init__(self, entry):
        self._entry = entry

    def get_tts_cache_entry(self, global_article_id, voice, engine):
        return self._entry


def test_split_sentences_preserves_decimal_numbers():
    """小数点不得作为句子边界：x.x%、指数点位、汇率等小数必须保持完整。

    回归：2026-09-03 路透早报所有小数被撕成两半（"295.01"→"295. 01"），
    朗读变成先读整数部分、停顿、再读小数部分。
    """
    units = split_sentences("道琼斯工业指数上涨295.01点，涨幅0.56%，报53061.89点。")
    joined = " ".join(units)
    assert "295.01" in joined
    assert "0.56%" in joined
    assert "53061.89" in joined


def test_split_sentences_preserves_various_decimals():
    """多位小数、汇率、百分比等多种形式的小数均应保留。"""
    units = split_sentences("中签率为0.02455315%。日圆报158.70日圆。收益率至4.794%，结束了连涨。")
    joined = " ".join(units)
    assert "0.02455315%" in joined
    assert "158.70" in joined
    assert "4.794%" in joined
    # 句号仍是句子边界
    assert len(units) == 3


def test_split_sentences_still_splits_on_sentence_period():
    """非小数的 ASCII 句点（前后不为数字）仍应作为句子边界。"""
    units = split_sentences("美国股市收高. 欧洲股市小幅收低。")
    assert len(units) == 2
    assert units[0].endswith("收高.")
    assert units[1].startswith("欧洲股市")


def test_split_sentences_preserves_leading_dot_decimals():
    """无前导零的小数（如 .5）也应保持完整（点后紧跟数字即保护）。"""
    units = split_sentences("数值为.5，仍然有效。")
    joined = " ".join(units)
    assert ".5" in joined
    assert ". 5" not in joined


def test_split_sentences_preserves_multi_dot_versions_and_dates():
    """多段版本号/日期（1.2.3、2026.09.02）保持完整，不被撕开。"""
    units = split_sentences("版本1.2.3发布于2026.09.02，修复了问题。")
    joined = " ".join(units)
    assert "1.2.3" in joined
    assert "2026.09.02" in joined


def test_split_sentences_preserves_decimal_across_fixed_chunk_boundary():
    """长句兜底固定切块也不得在小数中间插入分段空格。"""
    text = "字" * 118 + "1.23" + "字" * 200
    joined = " ".join(split_sentences(text))
    assert "1.23" in joined
    assert "1. 23" not in joined


def test_build_cache_key_includes_segment_algo_version(fake_settings):
    """稳定播放层缓存 key 应包含分段算法版本，使分段修复后所有 provider 旧缓存失效。

    回归：分段撕裂修复在稳定播放层，仅 bump AzureSpeechService.model 无法失效
    OpenAI/Google 等其他 provider 历史生成的受影响音频。
    """
    manager = StableTtsPlaybackManager(fake_settings)
    speech_service = FakeSpeechService(fake_settings.tts_cache_dir)
    key = manager.build_cache_key(speech_service, "测试文本", "nova", "123")
    assert key.startswith("segv2|")
    # provider 侧 key 仍作为组成部分保留
    assert speech_service._get_cache_key("测试文本", "nova", "123") in key



@pytest.mark.asyncio
async def test_get_status_ignores_db_entry_with_mismatched_cache_key(fake_settings, tmp_path):
    """DB 记录的 cache_key 与当前计算不一致（如输出格式切换后）时应忽略，不得返回旧格式文件。"""
    manager = StableTtsPlaybackManager(fake_settings)
    speech_service = FakeSpeechService(fake_settings.tts_cache_dir)

    stale_file = tmp_path / "stale_old_format.mp3"
    stale_file.write_bytes(b"old-format-audio")
    db_manager = _FakeDbManager({
        "cache_key": "azure-speech-v2|Audio16Khz32KBitRateMonoMp3|nova|article_123",  # 与当前计算的 key 不匹配
        "file_path": str(stale_file),
    })

    status = await manager.get_status(
        speech_service=speech_service,
        article_id="123",
        clean_text="测试文本",
        voice="nova",
        global_article_id=42,
        db_manager=db_manager,
    )

    assert status["status"] == "idle"
    assert status["final_ready"] is False


@pytest.mark.asyncio
async def test_get_status_serves_db_entry_with_matching_cache_key(fake_settings, tmp_path):
    """DB 记录的 cache_key 与当前计算一致且文件存在时应正常命中（防止过度拦截）。"""
    manager = StableTtsPlaybackManager(fake_settings)
    speech_service = FakeSpeechService(fake_settings.tts_cache_dir)

    expected_key = manager.build_cache_key(speech_service, "测试文本", "nova", "123")
    cached_file = tmp_path / "cached.mp3"
    cached_file.write_bytes(b"cached-audio")
    db_manager = _FakeDbManager({
        "cache_key": expected_key,
        "file_path": str(cached_file),
    })

    status = await manager.get_status(
        speech_service=speech_service,
        article_id="123",
        clean_text="测试文本",
        voice="nova",
        global_article_id=42,
        db_manager=db_manager,
    )

    assert status["status"] == "hit"
    assert status["final_ready"] is True


@pytest.mark.asyncio
async def test_manager_marks_failed_when_segment_generation_times_out(fake_settings):
    fake_settings.tts_segment_generation_timeout_seconds = 0.01
    manager = StableTtsPlaybackManager(fake_settings)
    speech_service = SlowSpeechService(fake_settings.tts_cache_dir)

    prepare_state, response = await manager.ensure_generation_started(
        speech_service=speech_service,
        article_id="456",
        clean_text="这是一小段测试文本。",
        voice="nova"
    )

    assert prepare_state == "started"
    cache_key = response["cache_key"]

    task = manager._active_tasks[cache_key]
    await task

    status = await manager.get_status(
        speech_service=speech_service,
        article_id="456",
        clean_text="这是一小段测试文本。",
        voice="nova"
    )

    assert status["status"] == "failed"
    assert status["error_info"] is not None
    assert "segment_0_failed" in status["error_info"]
    assert status["segments"][0]["status"] == "failed"
    assert status["segments"][0]["retry_count"] == 3


def test_split_text_uses_configurable_first_target(fake_settings):
    manager = StableTtsPlaybackManager(fake_settings)
    # Use text with actual sentence boundaries so split_sentences produces multiple units
    text = "这是一句测试文本。" * 30  # ~300 chars, multiple sentences
    segments = manager._split_text_for_segments(text, max_chars=900)
    assert len(segments[0]) >= 140
    assert len(segments[0]) < 260


def test_split_sentences_breaks_long_chinese_paragraphs_without_periods():
    long_clause = (
        "宝可梦幻想 哪个小男孩没幻想过生活在这样一个充满宝可梦伙伴的世界，"
        "它们能听懂且愿意倾听我们说话，有着不同的特点和强大的技能，而且都很可爱，"
        "我们可以跟它们睡觉吃饭并肩作战探索世界，永远不再孤独，不管是谁都可以找到最适合自己的宝可梦，"
        "这一切早就可以发生，但这一切终究没有发生，宝可梦复杂的版权问题和躺平在功劳簿上的版权公司 Game Freak "
        "让我们的幻想一直也仅仅是幻想，当然也有人说最近的几个新作阿尔宙斯朱紫比之前好多了。"
    )
    units = split_sentences(long_clause)

    assert len(units) >= 2
    assert max(len(unit) for unit in units) <= 180


def test_split_text_first_segment_respects_target_for_long_paragraphs(fake_settings):
    fake_settings.tts_segment_target_first = 140
    fake_settings.tts_first_playable_min_seconds = 25
    manager = StableTtsPlaybackManager(fake_settings)
    text = (
        "和帕鲁生活在一起的两周。"
        "宝可梦幻想 哪个小男孩没幻想过生活在这样一个充满宝可梦伙伴的世界，"
        "它们能听懂且愿意倾听我们说话，有着不同的特点和强大的技能，而且都很可爱，"
        "我们可以跟它们睡觉吃饭并肩作战探索世界，永远不再孤独，不管是谁都可以找到最适合自己的宝可梦，"
        "这一切早就可以发生，但这一切终究没有发生，宝可梦复杂的版权问题和躺平在功劳簿上的版权公司 Game Freak "
        "让我们的幻想一直也仅仅是幻想，当然也有人说最近的几个新作阿尔宙斯朱紫比之前好多了，"
        "虽然好多了，但只是臭味稀薄一点的狗屎罢了。"
    )
    segments = manager._split_text_for_segments(text, max_chars=900)

    assert len(segments) >= 2
    assert len(segments[0]) < 260


def test_split_text_falls_back_to_fixed_chunks_for_single_super_long_unit(fake_settings):
    manager = StableTtsPlaybackManager(fake_settings)
    text = "无句号长段" * 120
    segments = manager._split_text_for_segments(text, max_chars=900)

    assert len(segments) >= 2
    assert len(segments[0]) < 260


def test_manager_defaults_to_single_first_segment_strategy(fake_settings):
    manager = StableTtsPlaybackManager(fake_settings)

    assert manager.first_segments_parallel_count == 1
    assert manager.segment_target_first == 140


def test_next_ready_index_is_first_non_ready(fake_settings):
    manager = StableTtsPlaybackManager(fake_settings)
    manifest = {
        "segments": [
            {"status": "ready", "duration_sec": 10.0, "start_offset_sec": None, "end_offset_sec": None},
            {"status": "pending", "duration_sec": None, "start_offset_sec": None, "end_offset_sec": None},
            {"status": "ready", "duration_sec": 10.0, "start_offset_sec": None, "end_offset_sec": None},
        ],
        "final_ready": False
    }
    result = manager._recompute_manifest(manifest)
    assert result["next_ready_index"] == 1


class ParallelSpeechService(FakeSpeechService):
    def __init__(self, cache_dir: str, delay: float = 0.1):
        super().__init__(cache_dir)
        self.delay = delay
        self.concurrent_count = 0
        self.max_concurrent = 0
        self._lock = asyncio.Lock()

    async def synthesize(self, text, article_id=None, voice=None, audio_format=None, use_cache=True):
        async with self._lock:
            self.concurrent_count += 1
            self.max_concurrent = max(self.max_concurrent, self.concurrent_count)
        await asyncio.sleep(self.delay)
        async with self._lock:
            self.concurrent_count -= 1
        return f"audio:{text}".encode("utf-8")


@pytest.mark.asyncio
async def test_parallel_first_segments_run_concurrently(fake_settings, monkeypatch):
    fake_settings.tts_first_segments_parallel_count = 2
    manager = StableTtsPlaybackManager(fake_settings)
    speech_service = ParallelSpeechService(fake_settings.tts_cache_dir, delay=0.15)

    monkeypatch.setattr(
        "backend.services.tts_stable_playback.mp3_duration_seconds",
        lambda audio_bytes: 12.5
    )
    monkeypatch.setattr(
        "backend.services.tts_stable_playback.merge_mp3_segments",
        lambda segments: b"merged-audio"
    )

    text = "这是测试文本的第一句话。这是第二句话。这是第三句话。这是第四句话。这是第五句话。这是第六句话。这是第七句话。这是第八句话。这是第九句话。这是第十句话。" * 8

    prepare_state, response = await manager.ensure_generation_started(
        speech_service=speech_service,
        article_id="789",
        clean_text=text,
        voice="nova"
    )

    assert prepare_state == "started"
    cache_key = response["cache_key"]

    task = manager._active_tasks[cache_key]
    await task

    assert speech_service.max_concurrent >= 2

    status = await manager.get_status(
        speech_service=speech_service,
        article_id="789",
        clean_text=text,
        voice="nova"
    )
    assert status["final_ready"] is True


@pytest.mark.asyncio
async def test_semaphore_limits_concurrency(fake_settings, monkeypatch):
    fake_settings.tts_segment_generation_concurrency = 1
    fake_settings.tts_first_segments_parallel_count = 2
    manager = StableTtsPlaybackManager(fake_settings)
    speech_service = ParallelSpeechService(fake_settings.tts_cache_dir, delay=0.1)

    monkeypatch.setattr(
        "backend.services.tts_stable_playback.mp3_duration_seconds",
        lambda audio_bytes: 12.5
    )
    monkeypatch.setattr(
        "backend.services.tts_stable_playback.merge_mp3_segments",
        lambda segments: b"merged-audio"
    )

    text = "这是测试文本的第一句话。这是第二句话。这是第三句话。这是第四句话。这是第五句话。这是第六句话。这是第七句话。这是第八句话。这是第九句话。这是第十句话。" * 8

    prepare_state, response = await manager.ensure_generation_started(
        speech_service=speech_service,
        article_id="999",
        clean_text=text,
        voice="nova"
    )

    task = manager._active_tasks[response["cache_key"]]
    await task

    assert speech_service.max_concurrent == 1


def test_first_playable_threshold_uses_settings(fake_settings):
    fake_settings.tts_first_playable_min_seconds = 30
    manager = StableTtsPlaybackManager(fake_settings)
    manifest = {
        "segments": [
            {"status": "ready", "duration_sec": 35.0, "start_offset_sec": None, "end_offset_sec": None},
        ],
        "final_ready": False
    }
    result = manager._recompute_manifest(manifest)
    assert result["first_playable_ready"] is True

    fake_settings.tts_first_playable_min_seconds = 50
    manager2 = StableTtsPlaybackManager(fake_settings)
    manifest2 = {
        "segments": [
            {"status": "ready", "duration_sec": 35.0, "start_offset_sec": None, "end_offset_sec": None},
        ],
        "final_ready": False
    }
    result2 = manager2._recompute_manifest(manifest2)
    assert result2["first_playable_ready"] is False
