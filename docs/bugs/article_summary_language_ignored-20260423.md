# Article Summary Language Ignored - Chinese Summaries Generated for English Preference

## 问题描述

test-user 账户在数据库中设置了英文偏好（`preferred_language = 'en'`），但最近一天（2026-04-23）抓取的文章摘要仍然是中文的。

### 用户操作步骤
1. 以 test-user 身份登录（安卓客户端）
2. 进入 Profile -> Settings（MeView）
3. 选择语言为 English
4. 查看文章列表中的摘要内容

### 实际表现 vs 预期表现
- **实际**: 文章摘要内容为中文（如 "于浩被描绘为一个野心勃勃的创业者..."、"美股纳指涨1.64%..."）
- **预期**: 文章摘要内容应为英文，与用户语言偏好设置一致

## 原因定位

### 根本原因

**GPT 系统提示未强制要求输出语言一致性**

虽然后端代码正确传递了 `language='en'` 参数，并且 `_get_summary_prompt('en')` 返回了英文系统提示：

```
"You are a concise article summarizer. Summarize the following article in 80-120 words..."
```

但该提示**没有明确要求** "无论原文是什么语言，都必须用英文输出摘要"。当 GPT 收到中文文章内容作为输入时，模型倾向于用与输入相同的语言（中文）来生成摘要，导致即使 `language='en'`，输出仍然是中文。

### 数据验证

数据库查询确认：
- `article_summaries` 表中 `language='en'` 的记录生成时间都在用户设置英文偏好之后（2026-04-22 08:16 UTC 之后）
- 但摘要内容绝大多数为中文
- 同一篇文章存在 `zh` 和 `en` 两个缓存版本，说明缓存机制工作正常

### 相关代码位置

- 摘要提示生成: [`backend/nlp/processor.py:94-106`](backend/nlp/processor.py#L94-L106)
- 摘要生成调用: [`backend/utils/feed_refresher.py:167`](backend/utils/feed_refresher.py#L167)
- 用户语言获取: [`backend/storage/database.py:784-793`](backend/storage/database.py#L784-L793)

## 修复方案

**强化系统提示中的语言锁定指令**

在所有非中文语言的系统提示中，明确添加 "Always respond in [language], regardless of the article's original language" 指令，强制 GPT 使用指定语言输出，不因输入语言而切换。

**清除错误缓存**
- 删除 test-user 相关文章在 `language='en'` 下的错误中文缓存
- 下次 RSS 抓取或手动刷新时，系统会重新生成正确的英文摘要

## 修复状态

- [x] 问题定位
- [x] 文档记录
- [x] 代码修复
- [x] 缓存清理
- [x] 测试验证
- [x] 部署上线

## 修复记录

**修复文件**: `backend/nlp/processor.py`

**修复时间**: 2026-04-23

**修改内容**:
- 在 `_get_summary_prompt()` 的所有语言提示中，添加明确的语言锁定指令
- 英文提示添加：`CRITICAL: Always respond in English, regardless of the article's original language.`
- 日语、韩语、法语、德语、西班牙语、俄语提示均添加了同等约束
- 确保 GPT 不因输入文章的语言而改变输出语言

**缓存清理**:
- 删除了 test-user 的 13 条错误 `language='en'` 缓存摘要（内容为中文）
- 下次抓取或刷新时会重新生成正确的英文摘要

## 相关提交

- `98f437f` fix(nlp): enforce summary output language regardless of article language
