# Android 播放路透日报 TTS 报错：OpenAI API 配额不足错误暴露给用户

## 问题描述

在 Android 设备上播放"路透日报"文章时，TTS 语音生成失败，弹出一个包含原始 OpenAI API 错误信息的提示框：

```
segment_0_failed: Error code: 429 - {'error': {'message':
'You exceeded your current quota, please check your plan and billing
details. For more information on this error, read the docs:
https://platform.openai.com/docs/guides/error-codes/api-errors.',
'type': 'insufficient_quota', 'param': None, 'code': 'insufficient_quota'}}
```

### 用户操作步骤
1. 打开 Jasmine App（Android）
2. 进入 Feed 页面
3. 找到"路透早报：4月20日"文章
4. 点击播放按钮（▶️）
5. 弹出错误提示框，显示原始 API 错误信息

### 实际表现 vs 预期表现
- **实际**：用户看到 raw 的技术错误信息，包含 OpenAI API 内部错误细节，体验极差
- **预期**：显示友好的用户提示，如"语音服务暂时不可用，请稍后重试"或"服务端语音额度不足，请联系管理员"

## 原因定位

### 根本原因
OpenAI API Key 配额不足（HTTP 429 insufficient_quota），导致 TTS 分段生成时第一段（segment_0）生成失败。

### 具体流程问题
1. `openai_speech.py:_synthesize_single()` 调用 OpenAI API 生成音频
2. OpenAI 返回 429 insufficient_quota 错误
3. 异常被抛出，包含完整的原始错误信息
4. `tts_stable_playback.py:_generate_article_audio()` 捕获异常，将原始错误直接写入 manifest：
   ```python
   manifest["error_info"] = f"segment_{index}_failed: {last_error}"
   ```
5. 前端通过 `getTtsPrepareStatus` 轮询获取 manifest 状态
6. `useTTS.js:waitForCloudPlayable()` 检查到 `status.status === 'failed'`，抛出错误：
   ```javascript
   throw new Error(status.error_info || t('tts.audioGenerationFailed'))
   ```
7. 原始错误信息被显示给用户

### 相关代码位置
- **后端异常抛出**：`backend/nlp/openai_speech.py:270-272`
- **后端异常记录**：`backend/services/tts_stable_playback.py:562-584`
- **前端错误使用**：`frontend/src/composables/useTTS.js:658, 689`

## 修复方案

### 架构：后端返回错误码 + 前端 i18n 翻译

**核心设计**：后端将原始 API 错误映射为标准化英文错误码（如 `quota_exhausted`、`rate_limited`），前端通过 i18n key 渲染对应语言的用户提示。这样无论用户界面是中文还是英文，都能看到对应语言的友好提示。

### 1. 后端：`tts_stable_playback.py`
新增 `_get_error_code()` 函数，将各类原始错误映射为标准化英文错误码：
- `insufficient_quota` → `quota_exhausted`
- `rate_limit` / `429` → `rate_limited`
- `invalid_api_key` / `401` / `403` → `service_misconfigured`
- `timeout` → `generation_timeout`
- `connection` / `network` → `network_error`
- `content_filter` / `moderation` → `content_not_allowed`
- 其他 → `generation_failed`

manifest 的 `error_info` 字段存储 `"segment_0_failed: quota_exhausted"` 格式，前端可解析错误码。

### 2. 后端：`openai_speech.py`
在 `_synthesize_single()` 中对 OpenAI 429/402/401/403 错误进行包装，返回标准化错误码（如 `RuntimeError("quota_exhausted")`），原始错误保留在服务端日志中。

### 3. 前端：`useTTS.js`
新增 `_resolveTtsError()` 辅助函数：
- 从 `error_info` 中解析错误码（支持 `"segment_0_failed: quota_exhausted"` 或 `"quota_exhausted"` 格式）
- 通过错误码映射表查找对应的 i18n key（如 `quota_exhausted` → `tts.quotaExhausted`）
- 向后兼容：如果 `error_info` 包含中文字符（旧格式），直接显示原文
- 未知错误使用兜底提示 `tts.serviceUnavailable`

### 4. 前端：i18n 翻译
新增以下翻译 key，覆盖中英文：

| i18n Key | 中文 | 英文 |
|---|---|---|
| `tts.serviceUnavailable` | 语音服务暂时不可用，请稍后重试 | Voice service temporarily unavailable, please try again later |
| `tts.quotaExhausted` | 语音服务额度不足，请稍后重试或联系管理员 | Voice service quota exhausted, please try again later or contact admin |
| `tts.rateLimited` | 语音服务繁忙，请稍后重试 | Voice service is busy, please try again later |
| `tts.serviceMisconfigured` | 语音服务配置异常，请联系管理员 | Voice service is misconfigured, please contact admin |
| `tts.generationTimeout` | 语音生成超时，请稍后重试 | Voice generation timed out, please try again later |
| `tts.contentNotAllowed` | 该内容无法生成语音 | This content cannot be converted to speech |

## 修复状态

- [x] 问题定位
- [x] 文档记录
- [x] 代码修复
- [x] 测试验证

## 修复记录

**修复文件**:
- `backend/services/tts_stable_playback.py`
- `backend/nlp/openai_speech.py`
- `frontend/src/composables/useTTS.js`
- `frontend/src/i18n/zh.json`
- `frontend/src/i18n/en.json`
- `tests/api/test_tts_stable_playback_manager.py`

**修复时间**: 2026-04-20

**修改内容**:
1. 后端 `tts_stable_playback.py`：添加 `_get_error_code()` 函数，将原始 API 错误映射为标准化英文错误码（`quota_exhausted`、`rate_limited`、`service_misconfigured`、`generation_timeout`、`network_error`、`content_not_allowed`、`generation_failed`）。manifest 的 `error_info` 存储 `"segment_0_failed: quota_exhausted"` 格式
2. 后端 `openai_speech.py`：在 `_synthesize_single()` 中对 OpenAI 429/402/401/403 错误进行包装，返回标准化错误码（如 `RuntimeError("quota_exhausted")`），原始错误保留在服务端日志
3. 前端 `useTTS.js`：新增 `_resolveTtsError()` 辅助函数，从 `error_info` 解析错误码，通过映射表查找 i18n key。支持三种情况：
   - 新格式（英文错误码）→ 映射到对应 i18n 翻译
   - 旧格式（中文错误信息）→ 直接显示（向后兼容）
   - 未知格式 → 兜底提示 `tts.serviceUnavailable`
4. 前端 i18n：新增 6 个 TTS 错误翻译 key（`quotaExhausted`、`rateLimited`、`serviceMisconfigured`、`generationTimeout`、`contentNotAllowed`、`serviceUnavailable`），覆盖中英文
5. 测试：更新 `test_tts_stable_playback_manager.py` 超时测试断言，匹配新的错误码格式

## 测试验证

- [x] Python 语法检查通过 (`python3 -m py_compile`)
- [x] JavaScript 语法检查通过 (`node --check`)
- [x] TTS stable playback 单元测试通过 (3/3)
- [x] 快速测试套件通过 (35/35)

## 相关提交

- [99b3d6a] fix(tts): sanitize OpenAI API errors with i18n-friendly error codes
