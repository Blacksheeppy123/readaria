"""
播客生成器单元测试
"""
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from backend.services.podcast_generator import PodcastGenerator


class FakeAudioSegment:
    """最小可用的 AudioSegment 替身，用于验证播客合成流程。"""

    def __init__(self, duration_seconds: float = 1.0):
        self.duration_seconds = duration_seconds

    def __add__(self, other):
        return self

    def __radd__(self, other):
        if other == 0:
            return self
        return self.__add__(other)

    def normalize(self):
        return self

    def export(self, path, format="mp3", bitrate="128k"):
        Path(path).write_bytes(b"podcast-audio")


@pytest.mark.unit
@pytest.mark.tts
class TestPodcastGenerator:
    """测试播客生成器的 TTS 集成行为。"""

    @pytest.mark.asyncio
    async def test_synthesize_audio_uses_tts_cache(self, tmp_path):
        """播客分段合成应复用 TTS 磁盘缓存（同 podcast_id 内容固定）。"""
        generator = PodcastGenerator.__new__(PodcastGenerator)
        generator.speech_service = SimpleNamespace(
            synthesize=AsyncMock(return_value=b"segment-audio")
        )
        generator.podcast_cache_dir = tmp_path

        script_data = {
            "segments": [
                {"speaker": "Catherine", "text": "第一段内容"},
                {"speaker": "Alex", "text": "第二段内容"},
            ]
        }

        fake_audio_segment = MagicMock(
            from_file=MagicMock(return_value=FakeAudioSegment()),
            silent=MagicMock(return_value=FakeAudioSegment(duration_seconds=0.0)),
        )

        with patch.dict(sys.modules, {"pydub": SimpleNamespace(AudioSegment=fake_audio_segment)}):
            audio_path, duration = await generator.synthesize_audio(174, script_data)

        assert Path(audio_path) == tmp_path / "podcast_174.mp3"
        assert Path(audio_path).exists()
        assert duration == 1

        calls = generator.speech_service.synthesize.await_args_list
        assert len(calls) == 2
        assert calls[0].kwargs["voice"] == "nova"
        assert calls[1].kwargs["voice"] == "echo"
        assert all(call.kwargs["audio_format"] == "mp3" for call in calls)
        assert all(call.kwargs["use_cache"] is True for call in calls)
        assert calls[0].kwargs["article_id"] == "podcast_174_0"
        assert calls[1].kwargs["article_id"] == "podcast_174_1"
