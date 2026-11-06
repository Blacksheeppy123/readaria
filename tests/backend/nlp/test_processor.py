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


ZH_CONTENT = (
    "当地时间周二，美国财政部宣布将对中国商品加征关税，"
    "中方表示坚决反对并采取必要措施维护自身合法权益。"
    "多家机构分析认为，此举将对全球供应链产生深远影响，"
    "相关企业正在评估风险并调整生产布局，市场反应强烈。"
)


def test_generate_summary_uses_detected_content_language(processor, monkeypatch):
    """中文文章即使传入 language='en'（UI 偏好），prompt 也应使用内容语言 zh"""
    used_languages = []
    original_get_prompt = processor._get_summary_prompt

    def _spy_get_prompt(language):
        used_languages.append(language)
        return original_get_prompt(language)

    monkeypatch.setattr(processor, "_get_summary_prompt", _spy_get_prompt)

    processor.generate_summary(ZH_CONTENT, language='en')

    assert used_languages == ['zh']


def test_generate_summary_keeps_detected_en(processor, monkeypatch):
    used_languages = []
    original_get_prompt = processor._get_summary_prompt

    def _spy_get_prompt(language):
        used_languages.append(language)
        return original_get_prompt(language)

    monkeypatch.setattr(processor, "_get_summary_prompt", _spy_get_prompt)

    en_content = (
        "The Treasury Department announced new tariffs on Tuesday, "
        "sparking broad concern among economists. Analysts say the move "
        "could disrupt global supply chains and raise costs for consumers. "
        "Several major companies are now reassessing their production plans."
    )
    processor.generate_summary(en_content, language='zh')

    assert used_languages == ['en']
