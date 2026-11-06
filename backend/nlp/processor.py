import spacy
from typing import List, Dict, Any
import logging
import re
import time
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

from backend.utils.language_detect import detect_content_language

class NLPProcessor:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.logger.info("初始化NLP处理器...")
        
        self.logger.info("加载spaCy中文模型...")
        self.nlp = spacy.load("zh_core_web_sm")
        self.logger.info("spaCy中文模型加载完成")
        
        # 导入配置
        from core.config.settings import settings
        from backend.nlp.openai_client import get_chat_llm_with_fallback

        # 初始化ChatGPT（带 OpenRouter fallback）
        self.logger.info("初始化ChatGPT...")
        self.llm = get_chat_llm_with_fallback()
        self.logger.info("ChatGPT初始化完成")
        
        # 初始化提示模板
        self.logger.info("初始化提示模板...")
        self.summary_prompt = ChatPromptTemplate.from_messages([
            ("system", "你是一个专业的文章摘要生成助手。请用简洁的语言总结以下文章的主要内容，突出关键信息。"),
            ("user", "{text}")
        ])
        self.logger.info("提示模板初始化完成")
        
        # 初始化输出解析器
        self.output_parser = StrOutputParser()
        self.logger.info("NLP处理器初始化完成")

    def extract_entities(self, text: str) -> List[Dict[str, Any]]:
        """提取实体"""
        self.logger.info("开始提取实体...")
        start_time = time.time()
        
        doc = self.nlp(text)
        entities = []
        for ent in doc.ents:
            entities.append({
                'text': ent.text,
                'label': ent.label_,
                'start': ent.start_char,
                'end': ent.end_char
            })
            
        end_time = time.time()
        self.logger.info(f"实体提取完成，耗时: {end_time - start_time:.2f}秒")
        self.logger.info(f"共提取到 {len(entities)} 个实体")
        for entity in entities:
            self.logger.info(f"实体: {entity['text']} (类型: {entity['label']})")
            
        return entities
        
    def generate_summary(self, text: str, max_length: int = 150, language: str = 'en') -> str:
        """生成摘要

        摘要使用文章内容的语言生成；传入的 language 参数（通常为 UI 偏好语言）
        仅在内容语言检测失败时作为 fallback。
        """
        # 以文章内容语言为准，UI 偏好语言仅作检测失败时的 fallback
        language = detect_content_language(text, fallback=language)
        self.logger.info(f"开始生成摘要... (language={language})")
        start_time = time.time()

        try:
            # 根据语言选择提示词
            system_prompt = self._get_summary_prompt(language)
            summary_prompt = ChatPromptTemplate.from_messages([
                ("system", system_prompt),
                ("user", "{text}")
            ])

            # 构建摘要链
            summary_chain = summary_prompt | self.llm | self.output_parser

            # 生成摘要
            summary = summary_chain.invoke({"text": text})
            summary = summary.strip()

            # 后处理：如果模型输出过长，做安全截断
            summary = self._truncate_summary_text(summary, language)

            end_time = time.time()
            self.logger.info(f"摘要生成完成，耗时: {end_time - start_time:.2f}秒")
            self.logger.info(f"生成的摘要: {summary}")

            return summary
        except Exception as e:
            self.logger.error(f"生成摘要失败: {str(e)}")
            return self._fallback_summary(text, max_length)

    def _get_summary_prompt(self, language: str) -> str:
        """获取指定语言的摘要提示词"""
        prompts = {
            'zh': "你是一个专业的文章摘要生成助手。请用简洁的语言总结以下文章的主要内容，突出关键信息。严格限制在100-150个汉字。使用2-3个短段落或简洁的要点列表呈现，每个要点不超过一句话。避免大段文字堆砌和详细解释。",
            'en': "You are a concise article summarizer. Summarize the following article in 80-120 words. Use either 2 very short paragraphs OR 2-3 single-sentence bullet points. STRICTLY do not exceed 120 words. Do not include detailed explanations. Be brief and to the point. CRITICAL: Always respond in English, regardless of the article's original language.",
            'ja': "あなたはプロの文章要約アシスタントです。以下の文章の主な内容を100-150字程度で簡潔に要約し、重要な情報を強調してください。2〜3の短い段落または箇条書きを使用して構造化してください。各要点は1文以内にしてください。詳細な説明は不要です。重要：文章の元の言語に関係なく、必ず日本語で回答してください。",
            'ko': "당신은 전문적인 글 요약 어시스턴트입니다. 다음 글의 주요 내용을 80-120단어로 간결하게 요약하고 핵심 정보를 강조해 주세요. 2-3개의 짧은 단락이나 간단한 글머리 기호 목록을 사용하여 구조화해 주세요. 각 항목은 한 문장 이내로 작성하세요. 자세한 설명은 포함하지 마세요. 중요: 원문의 언어와 관계없이 반드시 한국어로 답변해 주세요.",
            'fr': "Vous êtes un assistant professionnel de résumé d'articles. Veuillez résumer brièvement le contenu principal de l'article suivant en 80-120 mots, en soulignant les informations clés. Utilisez 2-3 courts paragraphes ou une liste à puces concise. Chaque point ne doit pas dépasser une phrase. Évitez les explications détaillées. IMPORTANT : Répondez toujours en français, quelle que soit la langue originale de l'article.",
            'de': "Sie sind ein professioneller Artikel-Zusammenfassungsassistent. Bitte fassen Sie den Hauptinhalt des folgenden Artikels in 80-120 Wörtern knapp zusammen und heben Sie die wichtigsten Informationen hervor. Verwenden Sie 2-3 kurze Absätze oder eine kurze Aufzählung. Jeder Punkt sollte höchstens ein Satz sein. Detaillierte Erklärungen sind nicht erforderlich. WICHTIG: Antworten Sie immer auf Deutsch, unabhängig von der Originalsprache des Artikels.",
            'es': "Eres un asistente profesional de resumen de artículos. Resume brevemente el contenido principal del siguiente artículo en 80-120 palabras, destacando la información clave. Usa 2-3 párrafos cortos o una breve lista con viñetas. Cada viñeta debe tener una sola oración. No incluyas explicaciones detalladas. IMPORTANTE: Responde siempre en español, independientemente del idioma original del artículo.",
            'ru': "Вы профессиональный помощник по составлению резюме статей. Пожалуйста, кратко изложите основное содержание следующей статьи в 80-120 словах, выделив ключевую информацию. Используйте 2-3 коротких абзаца или краткий маркированный список. Каждый пункт должен быть не более одного предложения. Детальные объяснения не нужны. ВАЖНО: Всегда отвечайте на русском языке, независимо от языка оригинальной статьи.",
        }
        return prompts.get(language, prompts['en'])

    def _truncate_summary_text(self, text: str, language: str) -> str:
        """对过长的摘要做安全截断，保留完整句子"""
        limits = {
            'zh': 400,
            'en': 900,
            'ja': 450,
            'ko': 900,
            'fr': 900,
            'de': 900,
            'es': 900,
            'ru': 900,
        }
        limit = limits.get(language, 900)
        if len(text) <= limit:
            return text

        truncated = text[:limit]
        # 寻找最后一个句末边界
        last_boundary = max(
            truncated.rfind('. '),
            truncated.rfind('? '),
            truncated.rfind('! '),
            truncated.rfind('。'),
            truncated.rfind('！'),
            truncated.rfind('？'),
            truncated.rfind('\n'),
        )
        if last_boundary > limit * 0.7:
            return truncated[:last_boundary + 1].rstrip() + '...'
        return truncated.rstrip() + '...'

    def _fallback_summary(self, text: str, max_length: int = 150) -> str:
        plain = re.sub(r"<[^>]+>", "", text)
        plain = re.sub(r"!\[[^\]]*\]\([^)]+\)", "", plain)
        plain = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", plain)
        plain = plain.strip()
        sentences = re.split(r"[。．.!?！？]+", plain)
        for s in sentences:
            s = s.strip()
            if len(s) >= 20:
                return s[:max_length - 3].rstrip() + "..." if len(s) > max_length else s
        return plain[:max_length - 3].rstrip() + "..." if len(plain) > max_length else plain
            
    def process_article(self, article: Dict[str, Any], language: str = 'en') -> Dict[str, Any]:
        """处理文章"""
        self.logger.info(f"开始处理文章: {article['title']} (language={language})")
        start_time = time.time()

        content = article.get('content', '')

        # 确保必要的字段存在
        if 'author' not in article:
            article['author'] = 'Unknown'
            self.logger.info("文章作者未知，设置为'Unknown'")
        if 'source' not in article:
            article['source'] = 'Unknown'
            self.logger.info("文章来源未知，设置为'Unknown'")

        # 提取实体
        self.logger.info("开始提取实体...")
        entities = self.extract_entities(content)

        # 生成摘要
        self.logger.info("开始生成摘要...")
        summary = self.generate_summary(content, language=language)

        # 更新文章信息（仅保留实体和摘要，不再执行翻译）
        article.update({
            'entities': entities,
            'summary': summary
        })

        end_time = time.time()
        self.logger.info(f"文章处理完成，总耗时: {end_time - start_time:.2f}秒")
        self.logger.info(f"处理结果: 实体数={len(entities)}, 摘要长度={len(summary)}")

        return article
