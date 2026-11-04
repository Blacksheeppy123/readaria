import sys
from unittest.mock import MagicMock

# Mock heavy dependencies before importing processor
for _mod_name in (
    "spacy",
    "langchain_core",
    "langchain_core.prompts",
    "langchain_core.output_parsers",
    "langchain_openai",
):
    sys.modules.setdefault(_mod_name, MagicMock())

# Provide a minimal ChatPromptTemplate mock
_chat_prompt_mock = MagicMock()
_chat_prompt_mock.from_messages = MagicMock(return_value=MagicMock())
sys.modules["langchain_core.prompts"].ChatPromptTemplate = _chat_prompt_mock

# Provide a minimal StrOutputParser mock
_str_parser_mock = MagicMock()
sys.modules["langchain_core.output_parsers"].StrOutputParser = _str_parser_mock

import pytest
from backend.nlp.processor import NLPProcessor


@pytest.fixture
def processor(monkeypatch):
    import os
    os.environ.setdefault("OPENAI_API_KEY", "sk-test-key-for-init")
    os.environ.setdefault("POSTGRES_PASSWORD", "test")
    os.environ.setdefault("SECRET_KEY", "a" * 32)
    os.environ.setdefault("JWT_SECRET_KEY", "b" * 32)

    # Patch __init__ so we don't need real LLM / spacy / settings
    def _patched_init(self):
        self.logger = MagicMock()
        self.llm = MagicMock()
        self.summary_prompt = MagicMock()
        self.output_parser = MagicMock()

    monkeypatch.setattr(NLPProcessor, "__init__", _patched_init)
    return NLPProcessor()


def test_fallback_summary_strips_html(processor):
    text = "<p>Hello world. This is a test.</p>"
    result = processor._fallback_summary(text, max_length=150)
    assert "<p>" not in result
    assert "Hello world." in result


def test_fallback_summary_removes_markdown_images(processor):
    text = "![alt](http://example.com/img.png) First meaningful sentence here."
    result = processor._fallback_summary(text, max_length=150)
    assert "![alt]" not in result
    assert "First meaningful sentence here" in result


def test_fallback_summary_converts_markdown_links(processor):
    text = "[click here](http://example.com) is the link text."
    result = processor._fallback_summary(text, max_length=150)
    assert "click here" in result
    assert "[click here]" not in result


def test_fallback_summary_truncates_long_sentence(processor):
    text = "A" * 200 + ". Another sentence."
    result = processor._fallback_summary(text, max_length=150)
    assert len(result) <= 150
    assert result.endswith("...")


def test_fallback_summary_empty_string(processor):
    result = processor._fallback_summary("", max_length=150)
    assert result == ""


def test_fallback_summary_short_input(processor):
    result = processor._fallback_summary("Hi", max_length=150)
    assert result == "Hi"


def test_fallback_summary_no_space_after_punctuation(processor):
    text = "First sentence.Second sentence here."
    result = processor._fallback_summary(text, max_length=150)
    assert "Second sentence here" in result
