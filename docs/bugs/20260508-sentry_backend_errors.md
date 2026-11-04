# Sentry 后端错误修复汇总（2026-05-08）

## 问题描述

Sentry 后端项目 (`readaria-backend`) 报告多个未解决的错误，需要排查并修复明显有问题的项。

## 原因定位与修复

### 1. READARIA-BACKEND-6 / READARIA-BACKEND-5: slowapi limiter 缺少 request 参数

**问题**：`get_tts_play_url` 和 `get_google_client_id` 等 endpoint 使用了 `@limiter.limit()` 装饰器，但函数签名缺少 `request: Request` 参数，导致 slowapi 在应用启动时抛出异常：
```
Exception: No "request" or "websocket" argument on function "<function get_tts_play_url at 0x...>"
```

**根因**：slowapi 的 `@limiter.limit()` 要求被装饰函数必须接受一个 `request` 参数（FastAPI `Request` 类型），否则装饰器在注册时会直接抛异常。

**修复状态**：已在以下 commit 中修复：
- `896563a` fix(deploy): add missing Request param to rate-limited endpoints
- `8b5421e` fix(deploy): add missing Request param to TTS signed-URL endpoints

**Sentry 状态**：READARIA-BACKEND-5 已标记为 resolved；READARIA-BACKEND-6 需要手动标记 resolved。

### 2. READARIA-BACKEND-3: feed 日期解析 `year 0 is out of range`

**问题**：feed 验证服务解析某些 RSS 源的发布时间时，`time.mktime()` 遇到年份为 0 的异常日期，抛出 `OverflowError: year 0 is out of range`。

**影响 feed**：
- `https://refactoringenglish.com/index.xml`

**根因代码**：`backend/services/feed_validation.py:145-150`
```python
def _parse_published_at(entry: Any) -> datetime:
    published_parsed = getattr(entry, 'published_parsed', None)
    if published_parsed:
        return datetime.fromtimestamp(time.mktime(published_parsed))  # <- 异常点
    return None
```

**修复方案**：捕获 `ValueError` 和 `OverflowError`，异常时返回 `None`：
```python
def _parse_published_at(entry: Any) -> datetime:
    published_parsed = getattr(entry, 'published_parsed', None)
    if published_parsed:
        try:
            return datetime.fromtimestamp(time.mktime(published_parsed))
        except (ValueError, OverflowError):
            return None
    return None
```

**修复文件**：`backend/services/feed_validation.py`

### 3. RSSHub / Feed 外部服务错误（无需代码修复）

以下错误均为外部服务不稳定导致，无需代码修复：
- READARIA-BACKEND-2: RSSHub 503 (bilibili feed)
- READARIA-BACKEND-1: RSSHub 503
- READARIA-BACKEND-4: `Remote end closed connection without response`
- READARIA-BACKEND-8: `IncompleteRead(0 bytes read)`
- READARIA-BACKEND-7: `IncompleteRead(0 bytes read, 97 more expected)`

## 修复状态

- [x] 问题定位
- [x] 代码修复
- [x] Sentry 状态更新
- [ ] 部署到生产环境

## 修复记录

**修复文件**:
- `backend/services/feed_validation.py`

**修复时间**: 2026-05-08

**修改内容**:
- `_parse_published_at()`: 增加 try/except 捕获 `ValueError` 和 `OverflowError`，避免异常日期导致验证任务中断

### 4. READARIA-BACKEND-E / READARIA-BACKEND-D: TTS play_tts 缺少 token 参数

**问题**：`play_tts` 在 `sig` 和 `exp` 都不存在时调用 `_get_tts_request_context(article_id, request)`，但函数签名需要 3 个参数（缺少 `token`），导致 `TypeError`。

**根因代码**（修复前）：`backend/api/main.py:2400`
```python
_, article, speech_service, global_article_id = _get_tts_request_context(article_id, request)
```

**修复状态**：已在 commit `a7ed2b2` 修复：
```python
_, article, speech_service, global_article_id = _get_tts_request_context(article_id, request, token)
```

### 5. 前端日志噪音（READARIA-BACKEND-9, M, J, N, G, K, H, A, F, C, B）

**问题**：前端通过 `/api/v1/frontend-logs` 上报的 ERROR 级别日志被 Sentry 的 LoggingIntegration 捕获，产生大量非后端问题的噪音事件。

**根因**：Sentry 默认 LoggingIntegration 会捕获所有 `logging.error()` 调用。前端日志 endpoint 使用 `frontend_logger.error()` 写入日志时，这些事件被当作后端错误上报到 Sentry。

**修复方案**：
1. 在 `sentry_sdk.init()` 中添加 `before_send` 回调，过滤 `/api/v1/frontend-logs` 交易和 `frontend` logger 的事件
2. 将 `LoggingIntegration` 的 `event_level` 设为 `logging.CRITICAL`，避免 ERROR 级别日志触发 Sentry 事件

**修复文件**：`backend/api/main.py`

## 修复状态

- [x] 问题定位
- [x] 代码修复
- [x] Sentry 状态更新
- [x] 部署到生产环境（READARIA-BACKEND-3, E, D 已部署）
- [ ] 部署前端日志过滤修复

## 修复记录

**修复文件**:
- `backend/services/feed_validation.py`
- `backend/api/main.py`（Sentry 配置）

**修复时间**: 2026-05-08 / 2026-05-11

**修改内容**:
- `_parse_published_at()`: 增加 try/except 捕获 `ValueError` 和 `OverflowError`
- `sentry_sdk.init()`: 添加 `before_send` 过滤前端日志噪音；配置 `LoggingIntegration(event_level=logging.CRITICAL)`

## 相关提交

- `896563a` fix(deploy): add missing Request param to rate-limited endpoints
- `8b5421e` fix(deploy): add missing Request param to TTS signed-URL endpoints
- `d6af443` fix(feed-validation): handle invalid dates (year 0) in _parse_published_at
- `a7ed2b2` fix(tts): add missing token param to play_tts, increase audio ready timeout
- 待提交: Sentry 前端日志过滤修复
