# 英文摘要长度过长且 Markdown 结构丢失

## 问题描述

语言偏好修复已生效，英文用户现在能看到英文摘要，但存在两个体验问题：

1. **摘要长度过长**：对英文文章生成的摘要篇幅明显偏长，阅读负担较重。
2. **Markdown 结构未保留**：摘要内容没有很好地展示 Markdown 的结构，所有内容都挤在一起，导致阅读体验较差。

## 原因定位

### 根本原因
1. `backend/nlp/processor.py` 中的 `generate_summary()` prompt 对英文摘要的长度控制不足，仅泛泛地要求 "concisely"，没有给出具体的字数/词数限制。
2. prompt 没有明确要求模型以段落或 bullet list 的结构化方式输出摘要。
3. 前端 CSS 默认 `white-space: normal`，会折叠 AI 生成文本中的换行符，导致即使模型输出了列表结构，用户端也显示为一团连续文字。

### 相关代码位置
- `backend/nlp/processor.py` - `generate_summary()` / `_get_summary_prompt()`
- `frontend/src/views/ArticleDetail.vue` - `.summary-content`
- `frontend/src/views/ArticlesView.vue` - `.article-summary`
- `frontend/src/views/FeedView.vue` - `.article-summary`
- `frontend/src/views/SavedView.vue` - `.article-summary`
- `frontend/src/views/SearchView.vue` - `.result-summary`

## 修复方案

1. 优化 `backend/nlp/processor.py` 的 `_get_summary_prompt()`：
   - 对英文 (`en`) 明确限制 80-120 词，使用 2-3 个短段落或简洁 bullet list。
   - 同步优化其他语言（zh/ja/ko/fr/de/es/ru）的 prompt，统一要求结构化输出和字数控制。
2. 前端 CSS 统一添加 `white-space: pre-line`，保留 AI 输出中的换行结构，使 bullet list 和分段在视觉上生效。

## 修复状态

- [x] 问题定位
- [x] 文档记录
- [x] 代码修复
- [x] 测试验证

## 修复记录

### 2026-04-16 第一轮

**修改文件**:
- `backend/nlp/processor.py` — 重构 `_get_summary_prompt()`，为所有支持语言增加明确字数限制和结构化输出要求
- `frontend/src/views/ArticleDetail.vue` — `.summary-content` 增加 `white-space: pre-line`
- `frontend/src/views/ArticlesView.vue` — `.article-summary` 增加 `white-space: pre-line`
- `frontend/src/views/FeedView.vue` — `.article-summary` 增加 `white-space: pre-line`
- `frontend/src/views/SavedView.vue` — `.article-summary` 增加 `white-space: pre-line`
- `frontend/src/views/SearchView.vue` — `.result-summary` 增加 `white-space: pre-line`

### 2026-04-16 第二轮（追加）

**追加根因**:
- 大量英文文章的 `article_summaries` 缓存是在当日 09:30 左右（prompt 修复部署前）生成的，使用的是旧 prompt，摘要长度普遍在 2000–4000 字符。
- mytest1 用户在 12:47 左右刷新 feed 时，系统直接命中了这些旧缓存，导致用户仍然看到超长摘要。
- 即使新 prompt 生效后，模型偶尔仍会突破字数限制。

**追加修复**:
1. `backend/nlp/processor.py` — 进一步强化 prompt，明确要求 "STRICTLY do not exceed 120 words" 和 "每个要点不超过一句话"；新增 `_truncate_summary_text()` 后处理截断作为安全网（英文上限 900 字符）。
2. `scripts/regenerate_long_en_summaries.py` — 新增运维脚本，批量重新生成 `language='en'` 且长度超过 1000 字符的缓存摘要。
3. 在生产环境执行该脚本，成功将 110 条过长英文摘要重新生成，平均长度从 539 字符降至 305 字符，最大长度从 6300 降至 997。

## 相关提交

- `547af4d` fix(nlp,ui): improve English summary length and markdown formatting
- `be7c690` fix(nlp): strengthen summary prompt and add post-processing truncation
