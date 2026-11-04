# TTS 播放长文章时 audio_source_not_ready 超时错误

## 问题描述

用户（test-user）在 Feed 页面点击牧之野文章《恶果显现》的 "Listen" 按钮播放 TTS 语音时，弹出错误提示 `audio_source_not_ready`，无法播放。

**用户操作步骤**:
1. 打开 Feed 页面
2. 找到牧之野的文章《恶果显现》
3. 点击文章卡片上的 "Listen" 按钮
4. 弹出错误弹窗：`audio_source_not_ready`

**实际表现**: 显示错误弹窗，无法播放音频
**预期表现**: 正常开始播放 TTS 语音

## 原因定位

### 根本原因（真正原因）

后端 API `play_tts` 函数中调用 `_get_tts_request_context` 时缺少必需的 `token` 参数，导致后端直接抛出 `TypeError`，HTTP 请求失败。前端拿到请求失败的结果，显示 `audio_source_not_ready` 错误。

### 错误链

1. `_get_tts_request_context` 函数签名最近被修改为需要 3 个参数：`article_id`, `request`, `token`
2. `prepare_tts_generation` 和 `get_tts_prepare_status` 函数已同步更新，正确传入了 `token`
3. 但 `play_tts` 函数中的两处调用（2379 行和 2401 行）仍使用旧的两参数调用方式：`_get_tts_request_context(article_id, request)`
4. 当用户点击 "Listen" 时，前端请求 `/api/v1/tts/play/{article_id}`
5. 后端 `play_tts` 执行到 `_get_tts_request_context(article_id, request)` 时抛出 `TypeError: missing 1 required positional argument: 'token'`
6. 请求返回 500 错误，前端捕获后显示 `audio_source_not_ready`

### 后端日志证据

```
2026-05-09 11:06:33  ERROR  ❌ TTS 播放失败:
  _get_tts_request_context() missing 1 required positional argument: 'token'
  Traceback (most recent call last):
    File "/app/backend/api/main.py", line 2401, in play_tts
      _, article, speech_service, global_article_id = _get_tts_request_context(article_id, request)
                                                      ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    TypeError: _get_tts_request_context() missing 1 required positional argument: 'token'
```

### 相关代码位置

- `backend/api/main.py:2207` - `_get_tts_request_context` 定义（3 个参数）
- `backend/api/main.py:2379` - `play_tts` 中第一处错误调用（缺少 `token`）
- `backend/api/main.py:2401` - `play_tts` 中第二处错误调用（缺少 `token`）
- `backend/api/main.py:2273` - `prepare_tts_generation` 正确调用（有 `token`）
- `backend/api/main.py:2338` - `get_tts_prepare_status` 正确调用（有 `token`）

## 修复方案

1. 在 `play_tts` 函数签名中添加 `token` 参数
2. 在两处 `_get_tts_request_context` 调用中传入 `token`

**修改文件**: `backend/api/main.py`

## 修复状态

- [x] 问题定位
- [x] 文档记录
- [x] 代码修复
- [x] 测试验证（线上 test-user 播放牧之野文章验证通过）
- [x] 流程改进（更新 skill、checklist、CLAUDE.md）

## 修复记录

**修复时间**: 2026-05-09

**修改文件**: `backend/api/main.py`

**修改内容**:
- `play_tts` 函数签名添加 `token: str = Query(default=None, description="备用认证方式（URL query token）")`
- 2379 行：`_get_tts_request_context(article_id, request)` 改为 `_get_tts_request_context(article_id, request, token)`
- 2401 行：`_get_tts_request_context(article_id, request)` 改为 `_get_tts_request_context(article_id, request, token)`

**前端相关修改**（超时优化 + Sentry 监控，作为附带改进保留）：
- `frontend/src/composables/useTTS.js`: `waitForAudioReady` 超时从 8000ms 提升到 15000ms
- `frontend/src/composables/useTTS.js`: 音频就绪耗时超过 10s 时上报 Sentry

## 相关提交

- 待补充
