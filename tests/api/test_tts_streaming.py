"""
TTS 流式播放和缓存集成测试

测试 v2 MP3 流式架构的核心功能：
- /api/v1/tts/play/{article_id} 统一播放接口
- stream_and_save() 流式透传 + 异步保存
- 缓存命中/未命中逻辑
- 原子写入（并发安全）
"""
import os
import sys
import pytest
import asyncio
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, mock_open
from fastapi.testclient import TestClient

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from backend.nlp.openai_speech import OpenAISpeechService
from core.config.settings import settings


@pytest.fixture
def mock_settings():
    """创建模拟的 settings 对象"""
    settings_mock = MagicMock()
    settings_mock.openai_api_key = "test-api-key"
    settings_mock.openai_base_url = "https://api.openai.com/v1"
    settings_mock.azure_openai_tts_endpoint = ""
    settings_mock.azure_openai_tts_api_key = ""
    settings_mock.tts_cache_dir = tempfile.mkdtemp()
    settings_mock.openai_tts_model = "tts-1"
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
class TestStreamAndSaveCacheKey:
    """测试 stream_and_save 的缓存 key 一致性"""

    def test_cache_key_consistency(self, speech_service):
        """验证相同输入生成相同的缓存 key"""
        text = "测试文本内容"
        voice = "alloy"
        article_id = "12345"

        key1 = speech_service._get_cache_key(text, voice, article_id)
        key2 = speech_service._get_cache_key(text, voice, article_id)

        assert key1 == key2, "相同输入应生成相同的缓存 key"
        # 当提供 article_id 时，key 格式为 "{model}|{voice}|article_{id}"
        assert "article_12345" in key1, "key 应包含 article_id"
        assert voice in key1, "key 应包含 voice"

    def test_cache_key_with_different_voices(self, speech_service):
        """验证不同声线生成不同的 key"""
        text = "测试文本内容"
        article_id = "12345"

        key_alloy = speech_service._get_cache_key(text, "alloy", article_id)
        key_nova = speech_service._get_cache_key(text, "nova", article_id)

        assert key_alloy != key_nova, "不同声线应生成不同的缓存 key"

    def test_cache_key_with_different_articles(self, speech_service):
        """验证不同文章 ID 生成不同的 key"""
        text = "测试文本内容"
        voice = "alloy"

        key1 = speech_service._get_cache_key(text, voice, "123")
        key2 = speech_service._get_cache_key(text, voice, "456")

        assert key1 != key2, "不同文章 ID 应生成不同的缓存 key"

    def test_cache_key_without_article_id_uses_md5(self, speech_service):
        """验证无 article_id 时使用 MD5 哈希"""
        text = "测试文本内容"
        voice = "alloy"

        key = speech_service._get_cache_key(text, voice, article_id=None)

        # 无 article_id 时应使用 MD5 哈希（32 位十六进制）
        assert len(key) == 32, "MD5 哈希应该是 32 位"
        assert all(c in '0123456789abcdef' for c in key), "应该是十六进制字符串"


@pytest.mark.unit
class TestAtomicCacheWrite:
    """测试原子写入逻辑（并发安全）"""

    def test_atomic_write_uses_temp_file(self, speech_service, mock_settings):
        """验证缓存写入使用临时文件 + rename 模式"""
        cache_key = "test_cache_key_12345678"
        audio_data = b"fake_mp3_data"

        # Mock open 和 Path.rename
        with patch('builtins.open', mock_open()) as mock_file, \
             patch('pathlib.Path.rename') as mock_rename, \
             patch('pathlib.Path.with_suffix') as mock_suffix:

            # 配置 mock
            temp_path_mock = MagicMock()
            mock_suffix.return_value = temp_path_mock

            # 执行写入
            speech_service._save_to_cache(cache_key, audio_data, "mp3")

            # 验证：先写入临时文件
            mock_file.assert_called_once()
            # 验证：使用 .tmp.{pid} 后缀
            mock_suffix.assert_called_once()
            assert '.tmp.' in str(mock_suffix.call_args)

            # 验证：最后 rename（原子操作）
            temp_path_mock.rename.assert_called_once()

    def test_atomic_write_cleanup_on_failure(self, speech_service, mock_settings):
        """验证写入失败时清理临时文件"""
        cache_key = "test_fail_key"
        audio_data = b"fake_data"

        with patch('builtins.open', side_effect=IOError("Disk full")), \
             patch('pathlib.Path.unlink') as mock_unlink, \
             patch('pathlib.Path.with_suffix') as mock_suffix:

            temp_path_mock = MagicMock()
            mock_suffix.return_value = temp_path_mock

            # 执行写入（应该失败但不抛出异常）
            speech_service._save_to_cache(cache_key, audio_data, "mp3")

            # 验证：清理临时文件
            temp_path_mock.unlink.assert_called_once_with(missing_ok=True)


@pytest.mark.asyncio
class TestStreamAndSaveIntegration:
    """测试 stream_and_save 方法的集成逻辑"""

    async def test_stream_and_save_yields_chunks(self, speech_service, mock_settings):
        """验证流式响应立即 yield 每个 chunk"""
        article_id = "123"
        text = "测试文本"
        fake_chunks = [b"chunk1", b"chunk2", b"chunk3"]

        async def async_iter(items):
            for item in items:
                yield item

        # Mock OpenAI 流式响应
        mock_response = MagicMock()
        mock_response.iter_bytes.side_effect = lambda chunk_size=None: async_iter(fake_chunks)

        mock_stream_context = AsyncMock()
        mock_stream_context.__aenter__.return_value = mock_response
        mock_stream_context.__aexit__.return_value = None

        mock_client = MagicMock()
        mock_client.audio.speech.with_streaming_response.create.return_value = mock_stream_context
        speech_service.client = mock_client

        # 执行流式生成
        received_chunks = []
        async for chunk in speech_service.stream_and_save(article_id, text):
            received_chunks.append(chunk)

        # 验证：所有 chunk 都被 yield
        assert b"".join(received_chunks) == b"".join(fake_chunks)

    async def test_stream_and_save_writes_cache_after_completion(self, speech_service, mock_settings):
        """验证流结束后保存缓存"""
        article_id = "456"
        text = "测试缓存保存"
        fake_chunks = [b"part1", b"part2"]

        async def async_iter(items):
            for item in items:
                yield item

        # Mock OpenAI 流式响应
        mock_response = MagicMock()
        mock_response.iter_bytes.side_effect = lambda chunk_size=None: async_iter(fake_chunks)

        mock_stream_context = AsyncMock()
        mock_stream_context.__aenter__.return_value = mock_response
        mock_stream_context.__aexit__.return_value = None

        mock_client = MagicMock()
        mock_client.audio.speech.with_streaming_response.create.return_value = mock_stream_context
        speech_service.client = mock_client

        # 执行流式生成
        chunks = []
        async for chunk in speech_service.stream_and_save(article_id, text):
            chunks.append(chunk)
        
        # 验证缓存文件存在
        cache_key = speech_service._get_cache_key(text, "alloy", article_id)
        final_path = speech_service._get_cache_file_path(cache_key, "mp3")
        
        # 等待后台任务完成（因为 stream_and_save 可能在后台任务写完文件前就返回了最后的数据）
        # 实际上 stream_and_save 的 _file_tailer 会等到文件被重命名（即任务完成）才退出
        # 所以这里文件应该已经存在
        assert final_path.exists()
        assert final_path.read_bytes() == b"part1part2"

    async def test_stream_and_save_handles_long_text_truncation(self, speech_service, mock_settings):
        """验证超长文本按策略处理"""
        mock_settings.tts_max_article_length = 100
        mock_settings.tts_long_article_strategy = "truncate"
        speech_service.max_article_length = 100
        speech_service.long_article_strategy = "truncate"

        article_id = "789"
        long_text = "a" * 200  # 超过限制

        async def async_iter(items):
            for item in items:
                yield item

        # Mock OpenAI 响应
        mock_response = MagicMock()
        mock_response.iter_bytes.side_effect = lambda chunk_size=None: async_iter([b"truncated_audio"])

        mock_stream_context = AsyncMock()
        mock_stream_context.__aenter__.return_value = mock_response
        mock_stream_context.__aexit__.return_value = None

        mock_client = MagicMock()
        mock_client.audio.speech.with_streaming_response.create.return_value = mock_stream_context
        speech_service.client = mock_client

        # 执行（应该截断文本）
        chunks = []
        async for chunk in speech_service.stream_and_save(article_id, long_text):
            chunks.append(chunk)

        # 验证：API 调用使用了截断后的文本
        call_args = mock_client.audio.speech.with_streaming_response.create.call_args
        assert len(call_args.kwargs['input']) <= 100

    async def test_stream_and_save_rejects_empty_text(self, speech_service):
        """验证空文本被拒绝"""
        article_id = "999"
        empty_text = "   "

        # 应该在预处理阶段抛出 ValueError
        with pytest.raises(ValueError):
            async for _ in speech_service.stream_and_save(article_id, empty_text):
                pass


@pytest.mark.integration
@pytest.mark.skipif(
    not os.getenv('OPENAI_API_KEY'),
    reason="需要 OPENAI_API_KEY 环境变量才能运行集成测试"
)
class TestTtsPlayEndpoint:
    """测试 /api/v1/tts/play/{article_id} 端点（需要真实环境）"""

    def test_play_endpoint_cache_miss_returns_streaming_response(self):
        """测试缓存未命中时返回流式响应"""
        # 需要真实 API 和数据库环境
        # 这里仅作示例，实际测试需要在 E2E 环境运行
        pass

    def test_play_endpoint_cache_hit_returns_file_response(self):
        """测试缓存命中时返回文件响应"""
        # 需要真实 API 和数据库环境
        pass


@pytest.mark.unit
class TestAwaitConsistency:
    """AST 静态分析：验证所有 async 函数调用都有 await

    回归测试，防止类似 f57b956 的 await 遗漏。
    """

    def test_resolve_tts_prepare_status_calls_are_awaited(self):
        """验证 backend/api/main.py 中所有 _resolve_tts_prepare_status 调用都有 await"""
        import ast

        main_py = Path(__file__).parent.parent.parent / "backend" / "api" / "main.py"
        assert main_py.exists(), f"{main_py} not found"

        source = main_py.read_text(encoding="utf-8")
        tree = ast.parse(source)

        failures = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Name) and func.id == "_resolve_tts_prepare_status":
                    # 检查调用是否被 Await 包裹
                    # 向上查找父节点
                    for parent in ast.walk(tree):
                        # 找到包含此 Call 的节点
                        if hasattr(parent, "body"):
                            for child in ast.iter_child_nodes(parent):
                                if child is node:
                                    failures.append(
                                        f"_resolve_tts_prepare_status call at line {node.lineno} "
                                        f"is not awaited (parent type: {type(parent).__name__})"
                                    )
                        # 如果 Call 在 Await 节点中，则正确
                        if isinstance(parent, ast.Await) and parent.value is node:
                            # 从 failures 中移除（如果之前添加了）
                            failures = [f for f in failures
                                        if f"line {node.lineno}" not in f]
                            break
                        # 如果 Call 在 Assign 的 value 中，检查 Assign 是否在 Await 中
                        if isinstance(parent, ast.Assign):
                            for grandparent in ast.walk(tree):
                                if isinstance(grandparent, ast.Await) and grandparent.value is parent:
                                    failures = [f for f in failures
                                                if f"line {node.lineno}" not in f]
                                    break

        if failures:
            pytest.fail("\n".join(failures))

    def test_stable_tts_manager_async_calls_are_awaited(self):
        """验证 backend/api/main.py 中 stable_tts_manager 的 async 方法调用都有 await"""
        import ast

        main_py = Path(__file__).parent.parent.parent / "backend" / "api" / "main.py"
        source = main_py.read_text(encoding="utf-8")
        tree = ast.parse(source)

        tts_async_methods = {
            "get_status",
            "ensure_generation_started",
            "mark_usage_recorded",
            "usage_already_recorded",
        }

        failures = []

        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                # 只检查 stable_tts_manager.xxx() 或 _resolve_tts_prepare_status()
                method_name = None
                if isinstance(func, ast.Attribute) and func.attr in tts_async_methods:
                    # 检查是否是 stable_tts_manager 的调用
                    value = func.value
                    if isinstance(value, ast.Name) and value.id == "stable_tts_manager":
                        method_name = func.attr
                elif isinstance(func, ast.Name) and func.id == "_resolve_tts_prepare_status":
                    method_name = func.id

                if method_name:
                    is_awaited = False
                    for parent in ast.walk(tree):
                        if isinstance(parent, ast.Await):
                            awaited_node = parent.value
                            if awaited_node is node:
                                is_awaited = True
                                break
                            if isinstance(awaited_node, ast.Assign) and awaited_node.value is node:
                                is_awaited = True
                                break
                            if isinstance(awaited_node, ast.Expr) and awaited_node.value is node:
                                is_awaited = True
                                break
                            if isinstance(awaited_node, ast.Tuple):
                                for elt in awaited_node.elts:
                                    if elt is node:
                                        is_awaited = True
                                        break

                    if not is_awaited:
                        failures.append(
                            f"{method_name}() call at line {node.lineno} is not awaited"
                        )

        if failures:
            pytest.fail("\n".join(failures))


# pytest 标记说明：
# @pytest.mark.unit - 单元测试，不依赖外部服务
# @pytest.mark.asyncio - 异步测试
# @pytest.mark.integration - 集成测试，需要真实 API key
