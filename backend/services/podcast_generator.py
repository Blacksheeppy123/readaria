"""
AI 播客生成器
负责生成每日播客，包括文章筛选、脚本生成、音频合成
"""

import io
import json
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from pathlib import Path

from core.config.settings import settings
from backend.nlp.openai_client import chat_completion_with_fallback


class PodcastRateLimitError(Exception):
    """播客生成频控限制"""
    pass
from backend.storage.database import DatabaseManager
from backend.nlp.speech_service import get_speech_service

logger = logging.getLogger(__name__)


class PodcastGenerator:
    """播客生成器"""

    def __init__(self):
        # 使用 DatabaseManager（与 main.py 一致）
        self.db_manager = DatabaseManager(pg_config=settings.postgres_config)
        self.speech_service = get_speech_service(settings)
        self.podcast_cache_dir = Path(settings.podcast_audio_cache_dir)
        self.podcast_cache_dir.mkdir(parents=True, exist_ok=True)

    async def generate_daily_podcast(
        self,
        user_id: str,
        style: str = "deep_dive",
        time_range_hours: int = 24,
        max_articles: int = 10,
        language: str = "zh"
    ) -> int:
        """
        生成每日播客

        Args:
            user_id: 用户 ID
            style: 播客样式（deep_dive/quick_brief/debate）
            time_range_hours: 时间范围（小时）
            max_articles: 最大文章数

        Returns:
            podcast_id: 播客 ID
        """
        logger.info(f"开始为用户 {user_id} 生成播客，样式: {style}")

        # 1. 创建播客记录
        podcast_id = self._create_podcast_record(user_id, style, language)

        try:
            # 2. 更新状态为生成中
            self._update_podcast_status(podcast_id, "generating")

            # 3. 智能筛选文章
            article_refs = await self.select_articles(
                user_id, time_range_hours, max_articles
            )

            if not article_refs:
                raise ValueError("没有找到合适的文章")

            logger.info(f"筛选出 {len(article_refs)} 篇文章")

            # 4. 获取文章详情
            article_ids = [gid for gid, lid in article_refs]
            articles = self._get_articles_detail(article_ids, user_id)

            # 5. 生成播客脚本
            script_data = await self.generate_script(articles, style, language)

            # 6. 保存脚本
            script_id = self._save_script(podcast_id, script_data, language)

            # 7. 合成音频
            audio_path, duration = await self.synthesize_audio(
                podcast_id, script_data
            )

            # 8. 保存文章关联
            self._save_podcast_articles(podcast_id, article_refs, script_data)

            # 9. 更新播客信息
            if language == "en":
                today_str = datetime.now().strftime("%B %-d")
                default_title = f"Daily Podcast ({today_str})"
            else:
                today_str = datetime.now().strftime("%-m月%-d日")
                default_title = f"每日播客（{today_str}）"
            self._update_podcast_completed(
                podcast_id,
                audio_path,
                duration,
                script_data.get("metadata", {}).get("title", default_title)
            )

            logger.info(f"播客 {podcast_id} 生成成功")
            return podcast_id

        except Exception as e:
            logger.error(f"播客生成失败: {str(e)}", exc_info=True)
            self._update_podcast_status(
                podcast_id, "failed", error=str(e)
            )
            raise

    async def generate_podcast_content(
        self,
        podcast_id: int,
        user_id: str,
        style: str = "deep_dive",
        time_range_hours: int = 24,
        max_articles: int = 10,
        language: str = "zh"
    ):
        """
        为已创建的播客记录生成内容（用于后台异步执行）

        Args:
            podcast_id: 已创建的播客记录 ID
            user_id: 用户 ID
            style: 播客样式
            time_range_hours: 时间范围（小时）
            max_articles: 最大文章数
            language: 语言
        """
        logger.info(f"开始为播客 {podcast_id} 生成内容，用户: {user_id}")

        try:
            self._update_podcast_status(podcast_id, "generating")

            article_refs = await self.select_articles(
                user_id, time_range_hours, max_articles
            )

            if not article_refs:
                raise ValueError("没有找到合适的文章")

            logger.info(f"筛选出 {len(article_refs)} 篇文章")

            article_ids = [gid for gid, lid in article_refs]
            articles = self._get_articles_detail(article_ids, user_id)

            script_data = await self.generate_script(articles, style, language)

            script_id = self._save_script(podcast_id, script_data, language)

            audio_path, duration = await self.synthesize_audio(
                podcast_id, script_data
            )

            self._save_podcast_articles(podcast_id, article_refs, script_data)

            if language == "en":
                today_str = datetime.now().strftime("%B %-d")
                default_title = f"Daily Podcast ({today_str})"
            else:
                today_str = datetime.now().strftime("%-m月%-d日")
                default_title = f"每日播客（{today_str}）"
            self._update_podcast_completed(
                podcast_id,
                audio_path,
                duration,
                script_data.get("metadata", {}).get("title", default_title)
            )

            logger.info(f"播客 {podcast_id} 生成成功")

        except Exception as e:
            logger.error(f"播客 {podcast_id} 生成失败: {str(e)}", exc_info=True)
            self._update_podcast_status(
                podcast_id, "failed", error=str(e)
            )

    async def select_articles(
        self,
        user_id: str,
        time_range_hours: int,
        max_articles: int
    ) -> List[Tuple[int, int]]:
        """
        智能筛选文章

        评分因素：
        - 是否收藏（+2.0）
        - 阅读时长（+0.5 ~ +1.5）
        - 文章长度（500-5000 字最佳）
        - 来源热度（用户常读的来源）
        - 时间新鲜度（越新越好）
        """
        logger.info(f"开始筛选文章，用户: {user_id}, 时间范围: {time_range_hours}h")

        # 计算时间范围
        start_time = datetime.now() - timedelta(hours=time_range_hours)

        # 查询文章（Phase 2：从 global_articles + user_article_refs 中选择）
        query = """
        WITH article_scores AS (
            SELECT
                ga.id,
                uar.legacy_article_id,
                ga.title,
                ga.content,
                ga.published_at,
                uar.feed_id,
                LENGTH(ga.content) as content_length,
                -- 基础分数
                1.0 as base_score,
                -- 收藏加分
                CASE WHEN f.id IS NOT NULL THEN 2.0 ELSE 0.0 END as favorite_score,
                -- 阅读时长加分
                CASE
                    WHEN arh.read_duration >= 180 THEN 1.5
                    WHEN arh.read_duration >= 60 THEN 1.0
                    WHEN arh.read_duration >= 30 THEN 0.5
                    ELSE 0.0
                END as read_score,
                -- 文章长度加分（500-5000 字最佳）
                CASE
                    WHEN LENGTH(ga.content) BETWEEN 500 AND 5000 THEN 1.0
                    WHEN LENGTH(ga.content) BETWEEN 300 AND 500 THEN 0.5
                    WHEN LENGTH(ga.content) > 5000 THEN 0.3
                    ELSE 0.0
                END as length_score,
                -- 时间新鲜度加分
                CASE
                    WHEN ga.published_at > NOW() - INTERVAL '6 hours' THEN 1.0
                    WHEN ga.published_at > NOW() - INTERVAL '12 hours' THEN 0.7
                    WHEN ga.published_at > NOW() - INTERVAL '18 hours' THEN 0.4
                    ELSE 0.2
                END as freshness_score
            FROM global_articles ga
            INNER JOIN user_article_refs uar ON uar.global_article_id = ga.id
            INNER JOIN user_feeds uf ON uf.id = uar.feed_id AND uf.user_id = %s AND uf.is_active = true
            LEFT JOIN user_saved_articles f ON f.global_article_id = ga.id AND f.user_id = %s
            LEFT JOIN user_reading_history arh ON arh.global_article_id = ga.id AND arh.user_id = %s
            WHERE ga.published_at >= %s
            AND LENGTH(ga.content) >= 200  -- 至少 200 字
        )
        SELECT
            id,
            legacy_article_id,
            title,
            (base_score + favorite_score + read_score + length_score + freshness_score) as total_score
        FROM article_scores
        ORDER BY total_score DESC, published_at DESC
        LIMIT %s
        """

        with self.db_manager.pg_conn.cursor() as cur:
            cur.execute(
                query,
                (user_id, user_id, user_id, start_time, max_articles)
            )
            result = cur.fetchall()

        article_refs = [(row[0], row[1]) for row in result]

        logger.info(f"筛选出 {len(article_refs)} 篇文章")
        return article_refs

    async def generate_script(
        self,
        articles: List[Dict],
        style: str,
        language: str = "zh"
    ) -> Dict:
        """
        生成播客脚本

        Args:
            articles: 文章列表
            style: 播客样式
            language: 语言（zh/en）

        Returns:
            脚本数据（JSON 格式）
        """
        logger.info(f"开始生成播客脚本，文章数: {len(articles)}, 样式: {style}, 语言: {language}")

        # 构建文章摘要
        articles_summary = []
        for idx, article in enumerate(articles, 1):
            summary = {
                "id": article["id"],
                "title": article["title"],
                "content": article["content"][:4000],  # 取前 4000 字，提供充足素材
                "source": article.get("feed_title", "未知来源" if language == "zh" else "Unknown Source"),
                "author": article.get("author") or ""
            }
            articles_summary.append(f"{idx}. {json.dumps(summary, ensure_ascii=False)}")

        articles_text = "\n\n".join(articles_summary)

        # 构建 prompt
        prompt = self._build_script_prompt(articles_text, style, language)

        # 根据语言切换系统提示
        if language == "en":
            system_content = (
                "You are a professional podcast scriptwriter, skilled at turning articles into "
                "natural and fluent two-person conversations. The podcast is hosted by two hosts: "
                "Catherine (female voice) and Michael (male voice)."
            )
        else:
            system_content = (
                "你是一个专业的播客脚本编剧，擅长将文章转换为自然流畅的双人对话。"
                "播客由两位主播主持：Catherine（女声）和 Alex（男声）。"
            )

        # 调用 GPT 生成脚本（1M context, 128k output）
        # Cost: $0.10/1M input, $0.50/1M output
        try:
            response = chat_completion_with_fallback(
                model="gpt-6-luna",
                messages=[
                    {
                        "role": "system",
                        "content": system_content
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.7,
                max_tokens=16000
            )

            script_text = response.choices[0].message.content

            # 记录原始响应用于调试
            logger.info(f"GPT 响应长度: {len(script_text) if script_text else 0} 字符")
            if not script_text or script_text.strip() == "":
                logger.error("GPT 返回空响应")
                raise ValueError("GPT 返回空响应，请检查 prompt 或模型配置")

            # 解析 Markdown 格式的脚本
            script_data = self._parse_markdown_script(script_text)

            logger.info(f"脚本生成成功，段落数: {len(script_data.get('segments', []))}")
            return script_data

        except Exception as e:
            logger.error(f"脚本生成失败: {str(e)}", exc_info=True)
            raise

    def _parse_markdown_script(self, markdown_text: str) -> Dict:
        """
        解析 Markdown 格式的播客脚本

        格式示例：
        # 播客标题
        ## 元数据
        - 简介：...
        - 预计时长：15分钟
        ## 对话脚本
        ### [开场] host_female
        对话内容...
        ### [文章123] host_male
        对话内容...
        """
        lines = markdown_text.strip().split('\n')

        title = ""
        description = ""
        estimated_duration = 600  # 默认 10 分钟
        segments = []
        current_speaker = None
        current_text = []
        current_article_id = None

        for line in lines:
            line = line.strip()

            # 解析标题
            if line.startswith('# ') and not title:
                title = line[2:].strip()

            # 解析元数据（支持中英文）
            elif line.lower().startswith('- 简介') or line.lower().startswith('- description'):
                description = line.split('：', 1)[-1].split(':', 1)[-1].strip()

            elif line.lower().startswith('- 预计时长') or line.lower().startswith('- estimated duration'):
                duration_str = line.split('：', 1)[-1].split(':', 1)[-1].strip()
                # 提取数字（如 "15分钟" -> 15）
                import re
                match = re.search(r'(\d+)', duration_str)
                if match:
                    estimated_duration = int(match.group(1)) * 60

            # 解析对话段落
            elif line.startswith('### '):
                # 保存上一个段落
                if current_speaker and current_text:
                    segments.append({
                        "speaker": current_speaker,
                        "text": '\n'.join(current_text).strip(),
                        "article_id": current_article_id,
                        "timestamp": len(segments) * 15  # 简单估算
                    })
                    current_text = []

                # 解析新段落：### [开场] host_female 或 ### [文章123] host_male
                # GPT 也可能输出 ### [话题一] 美国搁置对华科技限制 host_male
                header = line[4:].strip()
                import re
                # 优先匹配末尾的 host_female/host_male
                speaker_match = re.search(
                    r'(host_female|host_male)\s*$', header
                )
                if speaker_match:
                    current_speaker = speaker_match.group(1)
                    # 去掉 speaker 部分，解析剩余的标签
                    tag_part = header[:speaker_match.start()].strip()
                else:
                    # 没有有效 speaker，保持上一个 speaker 不变
                    # 尝试从文本内容推断（下一行是否以 Catherine/Alex 开头）
                    tag_part = header
                    logger.warning(
                        f"段落缺少有效 speaker: {header[:50]}"
                    )

                # 解析方括号标签（如 [开场]、[文章123] 或 [Intro]、[Article123]）
                tag_match = re.match(r'\[([^\]]+)\]', tag_part)
                if tag_match:
                    article_ref = tag_match.group(1)
                    article_ref_lower = article_ref.lower()
                    if article_ref in ("开场", "结束", "概览", "结尾") or article_ref_lower in ("intro", "outro", "overview"):
                        current_article_id = None
                    elif article_ref.startswith("文章") or article_ref_lower.startswith("article"):
                        article_id_match = re.search(
                            r'\d+', article_ref
                        )
                        if article_id_match:
                            current_article_id = int(
                                article_id_match.group()
                            )
                        else:
                            current_article_id = None
                    else:
                        current_article_id = None
                else:
                    current_article_id = None

            # 收集对话内容
            elif line and not line.startswith('#') and current_speaker:
                current_text.append(line)

        # 保存最后一个段落
        if current_speaker and current_text:
            segments.append({
                "speaker": current_speaker,
                "text": '\n'.join(current_text).strip(),
                "article_id": current_article_id,
                "timestamp": len(segments) * 15
            })

        # 后处理：确保主播交替发言（GPT 有时会连续输出同一 speaker）
        segments = self._enforce_speaker_alternation(segments)

        return {
            "metadata": {
                "title": title,
                "description": description,
                "total_words": sum(len(seg["text"]) for seg in segments),
                "estimated_duration": estimated_duration
            },
            "segments": segments
        }

    def _enforce_speaker_alternation(self, segments: list) -> list:
        """柔性修正：先规范化无效 speaker，再修正连续 3+ 段同一 speaker"""
        if not segments:
            return segments

        valid_speakers = {"host_female", "host_male"}
        # 名字到 speaker 的映射
        name_map = {
            "catherine": "host_female",
            "alex": "host_male",
            "michael": "host_male",
        }

        # 第一步：规范化无效 speaker 值
        normalized = 0
        for i, seg in enumerate(segments):
            speaker = seg["speaker"]
            if speaker not in valid_speakers:
                # 尝试名字映射
                mapped = name_map.get(speaker.lower())
                if mapped:
                    seg["speaker"] = mapped
                else:
                    # 无法识别，按交替顺序分配
                    if i == 0:
                        seg["speaker"] = "host_female"
                    else:
                        prev = segments[i - 1]["speaker"]
                        other = (valid_speakers - {prev}).pop() \
                            if prev in valid_speakers else "host_male"
                        seg["speaker"] = other
                normalized += 1

        if normalized:
            logger.info(f"规范化了 {normalized} 个无效 speaker 值")

        # 第二步：柔性修正连续 3+ 段同一 speaker
        if len(segments) <= 2:
            return segments

        fixed = 0
        for i in range(2, len(segments)):
            if (segments[i]["speaker"] == segments[i - 1]["speaker"]
                    == segments[i - 2]["speaker"]):
                other = (valid_speakers - {segments[i - 1]["speaker"]}).pop()
                segments[i - 1]["speaker"] = other
                fixed += 1

        if fixed:
            logger.info(f"柔性修正了 {fixed} 个连续同 speaker 段落")

        return segments

    async def synthesize_audio(
        self,
        podcast_id: int,
        script_data: Dict
    ) -> Tuple[str, int]:
        """
        合成音频

        Args:
            podcast_id: 播客 ID
            script_data: 脚本数据

        Returns:
            (audio_path, duration): 音频路径和时长（秒）
        """
        logger.info(f"开始合成音频，播客 ID: {podcast_id}")

        from pydub import AudioSegment

        segments = script_data.get("segments", [])
        audio_segments = []

        # 音色映射
        voice_map = {
            "host_female": "nova",  # 女声
            "host_male": "echo",    # 男声
            "Catherine": "nova",    # 女声（名字别名）
            "Alex": "echo",        # 男声（名字别名）
            "Michael": "echo"       # 男声（英文主播名）
        }

        for idx, segment in enumerate(segments):
            speaker = segment.get("speaker", "host_female")
            text = segment.get("text", "")
            voice = voice_map.get(speaker, "nova")

            logger.info(f"合成第 {idx + 1}/{len(segments)} 段，音色: {voice}")

            # 调用 TTS (复用播客缓存，同个 podcast_id 当天内容固定)
            audio_data = await self.speech_service.synthesize(
                text=text,
                article_id=f"podcast_{podcast_id}_{idx}",
                voice=voice,
                audio_format="mp3",
                use_cache=True,
            )

            # 转换为 AudioSegment
            audio_segment = AudioSegment.from_file(
                io.BytesIO(audio_data),
                format="mp3"
            )

            audio_segments.append(audio_segment)

            # 添加段落间静音（300ms）
            if idx < len(segments) - 1:
                silence = AudioSegment.silent(duration=300)
                audio_segments.append(silence)

        # 合并所有音频
        final_audio = sum(audio_segments)

        # 音量归一化
        final_audio = final_audio.normalize()

        # 保存音频
        audio_filename = f"podcast_{podcast_id}.mp3"
        audio_path = self.podcast_cache_dir / audio_filename
        final_audio.export(audio_path, format="mp3", bitrate="128k")

        duration = int(final_audio.duration_seconds)

        logger.info(f"音频合成成功，时长: {duration}s, 路径: {audio_path}")
        return str(audio_path), duration

    def _build_script_prompt(self, articles_text: str, style: str, language: str = "zh") -> str:
        """构建脚本生成 prompt"""

        if language == "en":
            return self._build_english_script_prompt(articles_text, style)
        return self._build_chinese_script_prompt(articles_text, style)

    def _build_chinese_script_prompt(self, articles_text: str, style: str) -> str:
        """中文播客脚本 prompt"""

        if style == "deep_dive":
            style_instruction = """
播客样式：Deep Dive（深度分析）
- 目标时长：3-4 分钟
- 脚本总字数：800-1200 字（中文字符）
- 风格：深入探讨，分析观点，引发思考
- 主播互动：频繁提问和回应，营造对话感
- 每篇文章 2-3 轮对话交替即可
"""
        else:
            style_instruction = """
播客样式：Quick Brief（快速摘要）
- 目标时长：2-3 分钟
- 脚本总字数：600-900 字（中文字符）
- 风格：简洁明快，突出要点
- 主播互动：快速交替，高效传达信息
- 每篇文章 1-2 轮对话交替
"""

        today_str = datetime.now().strftime("%-m月%-d日")
        prompt = f"""
你是一个专业的播客脚本编剧。请将以下文章转换为双人对话播客脚本。
今天的日期是：{today_str}

{style_instruction}

主播设定：
- Catherine（女声，host_female）：好奇、善于提问、引导话题、偶尔分享自己的感受
- Alex（男声，host_male）：知识渊博、善于解答、深入分析、喜欢举例说明

⚠️ 核心规则 — 双人对话：
- 这是一档双人播客，Catherine 和 Alex 必须全程交替发言
- 每个 ### 段落只能是一个人说的话，下一个 ### 段落必须换另一个人
- 绝对不允许连续两个段落是同一个 speaker（如连续两个 host_female）
- 每个话题至少 4-6 轮交替（即 4-6 个 ### 段落，host_female 和 host_male 轮流）

要求：
1. 开场后先总览今天的热点信息或观点，每条用一句话概括（2-3 轮对话）
2. 然后逐一深入讨论每个话题，讨论时提及文章来源（source）或作者（author）
3. 每个话题的讨论要充分展开：先介绍背景，再分析核心观点，然后两位主播各自发表看法，最后做小结
4. 自然对话，包含语气词（嗯、哦、对、是的、确实、没错、有意思）
5. 适当停顿和转折，主播之间要有真实的互动感（追问、补充、反驳、赞同）
6. 突出文章核心观点，用具体例子和数据支撑讨论
7. 结尾总结今天的要点，并展望或留下思考（2-3 轮对话）
8. 【关键】整体脚本控制在 15-20 个对话段落，总字数 800-1200 字

文章列表：
{articles_text}

输出格式（Markdown）：
# 每日播客（{today_str}）- 主题关键词

## 元数据
- 简介：播客简介
- 预计时长：8分钟

## 对话脚本

### [开场] host_female
大家好，欢迎来到今天的深度分析...

### [概览] host_male
今天我们有几个重要话题要聊。第一，...；第二，...；第三，...

### [概览] host_female
嗯，确实都是很值得关注的话题。我们先从第一个开始吧...

### [文章123] host_male
好的，这篇来自XXX的文章提到了一个很有意思的观点...

### [文章123] host_female
哦？具体是什么观点？

### [文章123] host_male
他说的是...我觉得这个分析很到位，因为...

### [文章123] host_female
确实，而且我注意到文章里还提到了一个数据...

### [文章123] host_male
没错，这个数据说明了...

### [文章456] host_female
好，我们来看下一个话题。这篇来自YYY的文章...

### [文章456] host_male
嗯，这个话题我很感兴趣...

### [结尾] host_female
好的，今天聊了不少干货...

### [结尾] host_male
是的，感谢大家收听，我们下期再见！

请直接输出 Markdown 格式的脚本，不要包含任何其他文字。注意：每个段落必须严格交替 host_female 和 host_male。
"""
        return prompt

    def _build_english_script_prompt(self, articles_text: str, style: str) -> str:
        """英文播客脚本 prompt"""

        if style == "deep_dive":
            style_instruction = """
Podcast Style: Deep Dive
- Target duration: 3-4 minutes
- Total script length: 600-900 words (English)
- Tone: in-depth exploration, analyze viewpoints, provoke thought
- Host interaction: frequent questions and responses, create a conversational feel
- 2-3 dialogue turns per article is enough
"""
        else:
            style_instruction = """
Podcast Style: Quick Brief
- Target duration: 2-3 minutes
- Total script length: 400-700 words (English)
- Tone: concise and clear, highlight key points
- Host interaction: rapid alternation, efficiently convey information
- 1-2 dialogue turns per article
"""

        today_str = datetime.now().strftime("%B %-d")
        prompt = f"""
You are a professional podcast scriptwriter. Please convert the following articles into a two-person dialogue podcast script.
Today's date is: {today_str}

{style_instruction}

Host Setup:
- Catherine (female voice, host_female): curious, good at asking questions, guiding topics, occasionally sharing her own feelings
- Michael (male voice, host_male): knowledgeable, good at answering, deep analysis, likes to give examples

⚠️ Core Rule — Two-Person Dialogue:
- This is a two-person podcast. Catherine and Michael must alternate speaking throughout.
- Each ### section can only contain one person's lines; the next ### section must switch to the other person.
- Absolutely no consecutive sections with the same speaker (e.g., two host_female sections in a row).
- Each topic should have at least 4-6 alternating turns (i.e., 4-6 ### sections, host_female and host_male alternating).

Requirements:
1. After the intro, give an overview of today's hot topics or viewpoints, one sentence each (2-3 dialogue turns).
2. Then discuss each topic in depth, mentioning the article source or author during the discussion.
3. Each topic should be fully developed: introduce background, analyze core viewpoints, both hosts share their opinions, and end with a brief summary.
4. Natural dialogue, include filler words (um, oh, yeah, right, exactly, interesting, I see).
5. Appropriate pauses and transitions; hosts should have real interaction (follow-up questions, additions, disagreements, agreements).
6. Highlight the core viewpoints of the articles, support discussion with concrete examples and data.
7. Conclude by summarizing today's key points and leaving a thought or outlook (2-3 dialogue turns).
8. [Key] Keep the overall script concise: 15-20 dialogue segments, 600-900 words total.

Article List:
{articles_text}

Output Format (Markdown):
# Daily Podcast ({today_str}) - Theme Keyword

## Metadata
- Description: Brief podcast description
- Estimated Duration: 8 minutes

## Dialogue Script

### [Intro] host_female
Hello everyone, welcome to today's deep dive...

### [Overview] host_male
Today we have several important topics to discuss. First, ...; second, ...; third, ...

### [Overview] host_female
Yeah, these are all really worth paying attention to. Let's start with the first one...

### [Article123] host_male
Alright, this article from XXX mentions a really interesting point...

### [Article123] host_female
Oh? What point is that?

### [Article123] host_male
What it says is... I think this analysis is spot on, because...

### [Article123] host_female
Exactly, and I noticed the article also mentioned a data point...

### [Article123] host_male
Right, this data shows that...

### [Article456] host_female
Okay, let's move on to the next topic. This article from YYY...

### [Article456] host_male
Um, I'm really interested in this topic...

### [Outro] host_female
Alright, we've covered a lot of solid content today...

### [Outro] host_male
Yes, thanks everyone for listening, and we'll see you next time!

Please output the script in Markdown format directly, without any other text. Note: each section must strictly alternate between host_female and host_male.
"""
        return prompt

    def _create_podcast_record(self, user_id: str, style: str, language: str = "zh") -> int:
        """创建播客记录（含频控检查，原子操作）

        频控规则：同一用户 1 分钟内只能触发 1 次（防刷保护）
        业务配额由 subscription_service 统一管理
        Raises:
            PodcastRateLimitError: 频控限制时抛出，message 可直接展示给用户
        """
        if language == "en":
            today_str = datetime.now().strftime("%B %-d")
            pending_title = f"Daily Podcast ({today_str}) - Generating..."
        else:
            today_str = datetime.now().strftime("%-m月%-d日")
            pending_title = f"每日播客（{today_str}）生成中..."

        with self.db_manager.pg_conn.cursor() as cur:
            # 技术频控：1 分钟内只能触发 1 次（防止重复提交）
            cur.execute("""
                SELECT COUNT(*) FROM podcasts
                WHERE user_id = %s
                  AND generation_started_at > NOW() - INTERVAL '1 minute'
            """, (user_id,))
            if cur.fetchone()[0] > 0:
                raise PodcastRateLimitError("操作太频繁，请 1 分钟后再试")

            cur.execute("""
                INSERT INTO podcasts (user_id, title, style, generation_status, generation_started_at)
                VALUES (%s, %s, %s, 'pending', NOW())
                RETURNING id
            """, (user_id, pending_title, style))
            result = cur.fetchone()
            self.db_manager.pg_conn.commit()
            return result[0]

    def _update_podcast_status(
        self,
        podcast_id: int,
        status: str,
        error: Optional[str] = None
    ):
        """更新播客状态"""
        if error:
            query = """
            UPDATE podcasts
            SET generation_status = %s, generation_error = %s
            WHERE id = %s
            """
            with self.db_manager.pg_conn.cursor() as cur:
                cur.execute(query, (status, error, podcast_id))
                self.db_manager.pg_conn.commit()
        else:
            query = """
            UPDATE podcasts
            SET generation_status = %s
            WHERE id = %s
            """
            with self.db_manager.pg_conn.cursor() as cur:
                cur.execute(query, (status, podcast_id))
                self.db_manager.pg_conn.commit()

    def _get_articles_detail(self, article_ids: List[int], user_id: str) -> List[Dict]:
        """获取文章详情（Phase 2：基于 global_articles + user_article_refs）"""
        if not article_ids:
            return []

        placeholders = ",".join(["%s"] * len(article_ids))
        query = f"""
        SELECT DISTINCT ON (ga.id)
            ga.id,
            ga.title,
            ga.content,
            ga.published_at,
            uf.feed_name as feed_title,
            ga.author
        FROM global_articles ga
        JOIN user_article_refs uar ON uar.global_article_id = ga.id
        LEFT JOIN user_feeds uf ON uf.id = uar.feed_id AND uf.user_id = %s
        WHERE ga.id IN ({placeholders})
        ORDER BY ga.id, ga.published_at DESC
        """

        with self.db_manager.pg_conn.cursor() as cur:
            cur.execute(query, (user_id, *article_ids))
            result = cur.fetchall()

        articles = []
        for row in result:
            articles.append({
                "id": row[0],
                "title": row[1],
                "content": row[2],
                "published_at": row[3],
                "feed_title": row[4],
                "author": row[5]
            })

        return articles

    def _save_script(self, podcast_id: int, script_data: Dict, language: str = "zh") -> int:
        """保存脚本，同时生成推荐问题"""
        # 生成推荐问题
        suggested_questions = self._generate_questions_from_script(script_data, language)

        query = """
        INSERT INTO podcast_scripts (
            podcast_id,
            full_script,
            total_segments,
            estimated_duration,
            generated_by,
            suggested_questions
        )
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING id
        """

        full_script = json.dumps(script_data, ensure_ascii=False)
        total_segments = len(script_data.get("segments", []))
        estimated_duration = script_data.get("metadata", {}).get("estimated_duration", 0)
        questions_json = json.dumps(suggested_questions, ensure_ascii=False)

        with self.db_manager.pg_conn.cursor() as cur:
            cur.execute(
                query,
                (podcast_id, full_script, total_segments, estimated_duration, "gpt-6-luna", questions_json)
            )
            result = cur.fetchone()
            self.db_manager.pg_conn.commit()
            return result[0]

    def _generate_questions_from_script(self, script_data: Dict, language: str = "zh") -> List[str]:
        """基于脚本内容生成 3 个推荐问题"""
        if language == "en":
            defaults = [
                "What are the core insights of this podcast?",
                "What are the key takeaways to pay attention to?",
                "Can you summarize the main content for me?"
            ]
            prompt_template = """Based on the following podcast script, generate 3 specific, in-depth recommended questions.
The questions should:
1. Focus on specific topics, viewpoints, or events discussed in the podcast
2. Guide the user to explore the podcast content more deeply
3. Be concise and clear, each question no more than 20 words

Podcast script excerpt:
{script_text}

Please output 3 questions directly, one per line, without numbering or any other formatting."""
        else:
            defaults = [
                "这期播客的核心观点是什么？",
                "有哪些值得关注的要点？",
                "能帮我总结一下主要内容吗？"
            ]
            prompt_template = """基于以下播客脚本，生成 3 个具体的、有深度的推荐问题。
问题应该：
1. 针对播客中讨论的具体话题、观点或事件
2. 能引导用户深入了解播客内容
3. 简洁明了，每个问题不超过 30 字

播客脚本片段：
{script_text}

请直接输出 3 个问题，每行一个，不要编号或其他格式。"""

        segments = script_data.get("segments", [])
        if not segments:
            return defaults

        script_text = "\n".join([
            f"[{seg['speaker']}] {seg['text'][:150]}"
            for seg in segments[:15]
        ])

        prompt = prompt_template.format(script_text=script_text)

        try:
            from backend.nlp.openai_client import chat_completion_with_fallback
            response = chat_completion_with_fallback(
                model="gpt-5.6-luna",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=200
            )
            text = response.choices[0].message.content.strip()
            questions = [
                q.strip().lstrip("0123456789.、）) ")
                for q in text.split("\n")
                if q.strip()
            ]
            return questions[:3] if len(questions) >= 3 else questions + defaults[:3 - len(questions)]
        except Exception as e:
            logger.warning(f"生成推荐问题失败: {e}")
            return defaults

    def _save_podcast_articles(
        self,
        podcast_id: int,
        article_refs: List[Tuple[int, int]],
        script_data: Dict
    ):
        """保存播客-文章关联（Phase 2：同时写入 global_article_id）"""
        segments = script_data.get("segments", [])

        # 统计每篇文章的出现次数（作为重要性评分）
        article_counts = {}
        for segment in segments:
            article_id = segment.get("article_id")
            if article_id:
                article_counts[article_id] = article_counts.get(article_id, 0) + 1

        # 插入关联记录
        for idx, (global_article_id, legacy_article_id) in enumerate(article_refs):
            importance_score = article_counts.get(global_article_id, 0) / len(segments) if segments else 0

            query = """
            INSERT INTO podcast_articles (
                podcast_id,
                article_id,
                global_article_id,
                sequence_order,
                importance_score
            )
            VALUES (%s, %s, %s, %s, %s)
            """

            with self.db_manager.pg_conn.cursor() as cur:
                cur.execute(
                    query,
                    (podcast_id, legacy_article_id, global_article_id, idx, importance_score)
                )
                self.db_manager.pg_conn.commit()

    def _update_podcast_completed(
        self,
        podcast_id: int,
        audio_path: str,
        duration: int,
        title: str
    ):
        """更新播客完成信息"""
        query = """
        UPDATE podcasts
        SET
            generation_status = 'completed',
            generation_completed_at = NOW(),
            audio_url = %s,
            audio_cache_key = %s,
            duration = %s,
            title = %s
        WHERE id = %s
        """

        cache_key = Path(audio_path).name

        with self.db_manager.pg_conn.cursor() as cur:
            cur.execute(
                query,
                (audio_path, cache_key, duration, title, podcast_id)
            )
            self.db_manager.pg_conn.commit()
