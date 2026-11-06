import pytest

from backend.utils.language_detect import (
    _heuristic_detect,
    detect_content_language,
    normalize_detected_language,
    summary_matches_language,
)

ZH_TEXT = (
    "当地时间周二，美国财政部宣布将对中国商品加征关税，"
    "中方表示坚决反对并采取必要措施维护自身合法权益。"
    "多家机构分析认为，此举将对全球供应链产生深远影响，"
    "相关企业正在评估风险并调整生产布局，市场反应强烈。"
)

EN_TEXT = (
    "The Treasury Department announced new tariffs on Tuesday, "
    "sparking broad concern among economists. Analysts say the move "
    "could disrupt global supply chains and raise costs for consumers. "
    "Several major companies are now reassessing their production plans "
    "and weighing alternative sourcing strategies for the coming year."
)

JA_TEXT = (
    "財務省は火曜日、新たな関税措置を発表しました。"
    "経済学者の間で広く懸念が広がっており、複数の専門家は世界の供給網に "
    "混乱をもたらす可能性があると指摘しています。大手企業は生産計画の "
    "見直しを進めており、代替の調達先も検討されています。"
)


class TestNormalizeDetectedLanguage:
    def test_zh_variants_map_to_zh(self):
        assert normalize_detected_language("zh-cn") == "zh"
        assert normalize_detected_language("zh-tw") == "zh"

    def test_supported_languages_pass_through(self):
        assert normalize_detected_language("en") == "en"
        assert normalize_detected_language("ja") == "ja"
        assert normalize_detected_language("ko") == "ko"
        assert normalize_detected_language("fr") == "fr"
        assert normalize_detected_language("de") == "de"
        assert normalize_detected_language("es") == "es"
        assert normalize_detected_language("ru") == "ru"

    def test_unsupported_language_returns_none(self):
        assert normalize_detected_language("pt") is None
        assert normalize_detected_language("") is None


class TestDetectContentLanguage:
    def test_chinese_text_detected_as_zh(self):
        assert detect_content_language(ZH_TEXT) == "zh"

    def test_english_text_detected_as_en(self):
        assert detect_content_language(EN_TEXT) == 'en'

    def test_japanese_text_detected_as_ja(self):
        assert detect_content_language(JA_TEXT) == 'ja'

    def test_html_stripped_before_detection(self):
        html = "<p>" + ZH_TEXT + "</p>"
        assert detect_content_language(html) == 'zh'

    def test_short_text_uses_fallback(self):
        assert detect_content_language("你好", fallback='en') == 'en'
        assert detect_content_language("", fallback='zh') == 'zh'

    def test_unsupported_language_uses_fallback(self):
        # 葡萄牙语不在摘要支持列表内，回退到用户语言
        pt_text = (
            "O ministério das finanças anunciou novas tarifas nesta terça-feira. "
            "Economistas manifestaram grande preocupação com os possíveis impactos "
            "sobre as cadeias de abastecimento globais e os custos para os consumidores. "
            "Várias empresas já reavaliam seus planos de produção para o próximo ano."
        )
        assert detect_content_language(pt_text, fallback='en') == 'en'

    def test_heuristic_detect_cjk(self):
        assert _heuristic_detect(ZH_TEXT) == 'zh'
        assert _heuristic_detect(EN_TEXT) is None


class TestSummaryMatchesLanguage:
    def test_matching_summary_accepted(self):
        zh_summary = "文章分析了关税政策对全球供应链的影响。相关企业正在调整布局，市场反应强烈。专家呼吁各方保持克制。"
        assert summary_matches_language(zh_summary, 'zh')

    def test_mismatched_summary_rejected(self):
        # 模拟存量脏缓存：缓存键为 zh，但实际是英文摘要
        en_summary = (
            "The article analyzes the impact of tariff policies on global supply "
            "chains and explains how companies are adjusting their production "
            "plans in response to the latest economic developments this year."
        )
        assert not summary_matches_language(en_summary, 'zh')

    def test_short_summary_trusted(self):
        assert summary_matches_language("简短摘要。", 'en')

    def test_empty_summary_rejected(self):
        assert not summary_matches_language("", 'zh')
