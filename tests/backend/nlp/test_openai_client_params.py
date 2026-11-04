"""_build_completion_params 参数兼容层单测（2026-10-26，gpt-4.1-nano 下线迁移）"""
import pytest

from backend.nlp.openai_client import _build_completion_params


@pytest.mark.unit
class TestBuildCompletionParams:
    def test_legacy_model_keeps_temperature_and_max_tokens(self):
        params = _build_completion_params("gpt-4o-mini", 0.7, 1000, {})
        assert params == {"model": "gpt-4o-mini", "temperature": 0.7, "max_tokens": 1000}

    @pytest.mark.parametrize("model", ["gpt-5.6-luna", "gpt-6-luna", "gpt-5-mini", "o3"])
    def test_restricted_model_uses_completion_tokens_and_drops_temperature(self, model):
        params = _build_completion_params(model, 0.7, 1000, {})
        assert params == {"model": model, "max_completion_tokens": 1000}
        assert "temperature" not in params
        assert "max_tokens" not in params

    def test_restricted_model_keeps_default_temperature(self):
        # temperature=1 是受限模型唯一支持的值，无需丢弃告警路径
        params = _build_completion_params("gpt-5.6-luna", 1, 1000, {})
        assert params == {"model": "gpt-5.6-luna", "max_completion_tokens": 1000}

    def test_openrouter_prefixed_model_still_detected(self):
        params = _build_completion_params("openai/gpt-6-luna", 0.7, 1000, {})
        assert params == {"model": "openai/gpt-6-luna", "max_completion_tokens": 1000}

    def test_conflicting_token_kwargs_are_normalized(self):
        params = _build_completion_params(
            "gpt-5.6-luna", 0.7, 1000, {"max_tokens": 5, "max_completion_tokens": 5}
        )
        assert params == {"model": "gpt-5.6-luna", "max_completion_tokens": 1000}

    def test_extra_kwargs_passthrough(self):
        params = _build_completion_params("gpt-6-luna", 0.7, 1000, {"response_format": {"type": "json_object"}})
        assert params["response_format"] == {"type": "json_object"}
