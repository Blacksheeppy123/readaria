# TTS 播放接口缺失 await 导致首次播放失败

## 问题描述

使用 test-user 账户首次播放"路透早报：4月23日"文章时，播放报错，第二次点击播放才成功。

- **受影响接口**: `/api/v1/tts/play/{article_id}` 和 `/api/v1/tts/segments/{article_id}/{index}`
- **现象**: 首次点击播放按钮时，后端返回错误；再次点击后正常播放
- **短文章不受影响**: 因为短文章可能直接命中缓存或走不同的播放路径

## 原因定位

### 根本原因

`backend/api/main.py` 中两个 TTS 接口函数调用异步函数 `_resolve_tts_prepare_status` 时**缺失了 `await`**：

1. `play_tts` 函数（第2244行）
2. `get_tts_segment` 函数（第2321行）

### 具体流程问题

当 `_resolve_tts_prepare_status` 未被 `await` 时：

1. 函数返回的是**协程对象**（coroutine），而不是 `(voice_to_use, clean_text, status)` 元组
2. Python 在解包赋值 `voice_to_use, clean_text, status = _resolve_tts_prepare_status(...)` 时立即抛出 **`TypeError: cannot unpack non-iterable coroutine object`**
3. 异常被外层的 `except Exception` 捕获，返回 **HTTP 500** 给前端

### 为什么只有长文章、且只有"有时"失败

**前端播放流程决定错误触发时机：**

1. 首次点击 → `POST /api/v1/tts/prepare` 触发生成任务
2. 前端进入 `waitForCloudPlayable` 轮询（`useTTS.js:716-754`）
3. **短/中等文章**：生成速度快，`final_ready` 在首次轮询时已完成 → 前端调用 `playFinalAudio` → 请求 `/api/v1/tts/play/{id}` → `play_tts` 中 `final_path.exists()` 为 true → 直接返回文件，**不会执行到缺失 `await` 的代码**
4. **长文章**：生成慢，`first_playable_ready` 先于 `final_ready` → 前端调用 `playSegmentByTime` → 请求 `/api/v1/tts/segments/{id}/{index}` → `get_tts_segment` 执行到缺失 `await` 的代码 → **500 错误**
5. 第二次点击时，后台生成任务可能已完成 `final.mp3`，`play_tts` 直接命中缓存 → 成功

### 相关代码位置

- `backend/api/main.py:2244` - `play_tts` 中 `_resolve_tts_prepare_status` 调用缺失 `await`
- `backend/api/main.py:2321` - `get_tts_segment` 中 `_resolve_tts_prepare_status` 调用缺失 `await`
- `frontend/src/composables/useTTS.js:716-754` - 前端轮询等待 playable 的逻辑

## 修复方案

在两处调用前添加 `await`：

```python
# play_tts 中（第2244行）
voice_to_use, clean_text, status = await _resolve_tts_prepare_status(...)

# get_tts_segment 中（第2321行）
voice_to_use, clean_text, status = await _resolve_tts_prepare_status(...)
```

## 修复状态

- [x] 问题定位
- [x] 文档记录
- [x] 代码修复
- [x] 测试验证（单元测试通过 + 新增 AST 静态分析回归测试）

## 修复记录

**修复文件**: `backend/api/main.py`

**修复时间**: 2026-04-23

**修改内容**:
- 在 `play_tts` 函数中为 `_resolve_tts_prepare_status` 调用添加 `await`
- 在 `get_tts_segment` 函数中为 `_resolve_tts_prepare_status` 调用添加 `await`

## 相关提交

- [待提交] fix(tts): add missing await in play_tts and get_tts_segment

## Decisions

### 问题 1：文档中错误链描述不准确
✅ 接受 - 已更新"具体流程问题"部分，明确说明 Python 中协程对象不可解包，实际失败点是解包赋值时立即抛出的 `TypeError: cannot unpack non-iterable coroutine object`，而非后续对 `status` 的下标访问。

### 问题 2："首次点击失败、第二次点击成功"的因果关系未建立
✅ 接受 - 已补充完整的前后端交互时序说明，解释了前端 `waitForCloudPlayable` 轮询逻辑如何决定触发 `play_tts` 还是 `get_tts_segment`，以及为什么长文章（生成慢、先触发 segment 播放）会命中 bug，而短文章（生成快、直接 final 播放）不会。

### 问题 3：缺少自动化回归测试
✅ 接受 - 已在 `tests/api/test_tts_streaming.py` 中添加 `TestAwaitConsistency` 测试类，包含两个 AST 静态分析测试：
- `test_resolve_tts_prepare_status_calls_are_awaited`：检查所有 `_resolve_tts_prepare_status()` 调用都有 `await`
- `test_stable_tts_manager_async_calls_are_awaited`：检查 `stable_tts_manager` 的所有 async 方法调用都有 `await`

这类 await 遗漏是容易反复出现的微小回归，AST 静态分析可以在编译时捕获，无需依赖完整 API 测试环境。

## Review意见

## Feature: tts-play-api-missing-await
- problem 1:
  - level: p1
  - description: `[Boundary]` The fix in `backend/api/main.py:2244` and `backend/api/main.py:2321` is correct, but the runtime explanation in this bug doc is not. `docs/bugs/tts_play_api_missing_await-20260423.md:20-28` says the un-awaited call later breaks at `status["final_ready"]` and `build_cache_key(...)`. In Python, the immediate failure happens earlier when the coroutine object is unpacked into `voice_to_use, clean_text, status`, so the documented failure chain is technically inaccurate.
  - fix suggestion: Update the root-cause section to describe the actual failure point as tuple unpacking of an un-awaited coroutine, and remove the unsupported `build_cache_key` claim unless you have logs proving execution got that far.
  - decision and reason(by claude): Must update the bug doc before treating this as a confirmed RCA. The code patch is fine, but the current explanation overstates what was proven.

- problem 2:
  - level: p1
  - description: `[Implicit Assumptions]` `docs/bugs/tts_play_api_missing_await-20260423.md:5-18` presents the missing `await` as the root cause of the user-visible pattern "first click fails, second click succeeds". That causality is not established by the document. If these endpoints really missed `await`, they would normally fail deterministically on every request until fixed. The doc does not explain why the second click would succeed, nor does it connect that behavior to the `prepare` polling path in `frontend/src/composables/useTTS.js:716-807`.
  - fix suggestion: Either attach concrete evidence (server log, stack trace, request sequence) showing the second click succeeded for a separate reason, or soften the wording to "likely contributor" instead of final root cause. If the retry behavior matters, document the exact frontend/backend sequence that makes it recover on the second attempt.
  - decision and reason(by claude): Needs clarification before this bug record can be considered a reliable incident write-up. The code change is low risk, but the diagnosis is still incomplete.

- problem 3:
  - level: p1
  - description: `[Maintainability]` `docs/bugs/tts_play_api_missing_await-20260423.md:47-52` marks "测试验证" as done, but the repo currently has no automated test covering `backend/api/main.py:2227-2304` or `backend/api/main.py:2307-2345` for this regression. `tests/api/test_tts_streaming.py` only contains placeholder integration tests for `/api/v1/tts/play/{article_id}` and nothing for `/api/v1/tts/segments/{article_id}/{index}`.
  - fix suggestion: Add a FastAPI test that mocks `_resolve_tts_prepare_status` and verifies both endpoints can consume its awaited tuple result without returning 500. Until that exists, change the bug doc status from "测试验证" to a more precise manual verification note.
  - decision and reason(by claude): Strongly recommended before closing the bug. This is exactly the sort of tiny async regression that can quietly reappear.

## Comments and Future suggestion

- The actual code fix is correct and narrowly scoped: adding `await` at `backend/api/main.py:2244` and `backend/api/main.py:2321` is the right change.
- I did not find evidence in this review that the fix itself introduces a new behavioral risk.
- The main issue is documentation quality: the RCA is partially inaccurate, and the verification claim is stronger than the current test coverage supports.
