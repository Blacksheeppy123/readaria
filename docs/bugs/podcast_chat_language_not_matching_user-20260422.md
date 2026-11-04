# Podcast Chat Responds in Chinese for English-Language Users

## 问题描述

英文语言用户在播客问答（Chat with Podcast）中用英文提问，但系统用中文回答。

- **用户操作**：将应用语言设为 English，进入 Chat with Podcast，用英文提问
- **实际表现**：AI 助手用中文回复（如截图所示）
- **预期表现**：AI 助手应根据用户的 `preferred_language` 用对应语言回复

## 原因定位

### 根本原因

播客问答 RAG 服务在生成回复时，未考虑用户的语言偏好。System prompt 是硬编码的中文，且 API 端点未将用户的 `preferred_language` 传递给 RAG 服务。

### 相关代码位置

1. **API 端点未传递语言**：[backend/api/main.py:3043](backend/api/main.py#L3043)
   - `chat_with_podcast()` 调用 `rag.generate_response()` 时没有传入 `language` 参数
   - 参考播客生成逻辑（main.py:2533），应从 `current_user.get('preferred_language', 'en')` 获取语言

2. **RAG 服务未接收语言参数**：[backend/services/podcast_rag.py:22](backend/services/podcast_rag.py#L22)
   - `generate_response()` 方法签名没有 `language` 参数

3. **System Prompt 硬编码中文**：[backend/services/podcast_rag.py:182](backend/services/podcast_rag.py#L182)
   - `_build_system_prompt()` 返回纯中文 prompt，没有根据语言切换
   - 参考 `podcast_generator.py` 中已实现的英文/中文 prompt 切换模式

## 修复方案

1. 修改 `PodcastRAG.generate_response()` 添加 `language` 参数（默认 `"zh"`）
2. 修改 `_build_system_prompt()` 根据 `language` 返回英文或中文 prompt
3. 修改 `chat_with_podcast` API 端点：
   - 获取 `user_language = current_user.get('preferred_language', 'en')`
   - 调用 `rag.generate_response(..., language=user_language)`

## 修复状态

- [x] 问题定位
- [x] 文档记录
- [x] 代码修复
- [x] 测试验证

## 修复记录

**修复文件**:
- [backend/services/podcast_rag.py](backend/services/podcast_rag.py)
- [backend/api/main.py](backend/api/main.py)

**修复时间**: 2026-04-22

**修改内容**:
- `PodcastRAG.generate_response()`: 添加 `language` 参数，传递给 `_build_system_prompt(language)`
- `PodcastRAG._build_system_prompt()`: 根据 language 返回英文/中文 system prompt
- `chat_with_podcast` API: 读取用户 `preferred_language` 并传入 RAG

## 相关提交

- [待提交] fix(backend): podcast chat respects user preferred_language
