# Feed Update and Daily Podcast Generation Failure

## 问题描述

1. **RSS 文章更新停止**: test-user 账户从昨天（2026-04-18）到现在没有新的文章更新
2. **每日播客生成失败**: 最近两天的每日播客生成任务失败

### 用户操作步骤
- 正常情况下，系统应每小时自动抓取 RSS 订阅源并生成新文章
- 每日播客应定期生成

### 实际表现 vs 预期表现
- **实际**: test-user 的文章列表未更新；播客生成任务失败
- **预期**: 每小时应有新文章入库；每日播客正常生成

## 原因定位

### 高概率根因
**定时抓取任务长时间未完成，导致 APScheduler 在 `max_instances=1` 下持续跳过后续任务**

- 根据代码机制与故障现象，高概率是某次每小时 RSS 抓取任务在启动后长时间未完成，后续同一个 job 因 APScheduler 默认 `max_instances=1` 被持续跳过
- 若线上日志中确实连续出现 `Execution skipped: maximum number of running instances reached (1)`，则可进一步坐实这一判断
- 由于超过 24 小时没有新文章被抓取，每日播客在选稿阶段查询不到合适文章，最终报错 `ValueError: 没有找到合适的文章`
- 目前可以较高置信度确认“播客失败是 RSS 长时间未更新的结果”，但“具体卡死在某一个 feed/某一次网络请求”仍需要结合线上日志继续定位

### 具体流程问题
1. `_run_async_task()` 在同步线程中运行异步事件循环，没有超时保护
2. 某个 feed 的 RSS 抓取可能阻塞（网络超时、RSSHub 无响应等），导致整个事件循环挂起
3. APScheduler job `fetch_all_feeds_hourly` 没有配置 `max_instances`，使用默认值1
4. 播客生成失败是**结果**而非独立原因——因为没有新文章入库

### 相关代码位置
- RSS 抓取调度: `backend/scheduler/feed_scheduler.py`
  - `_run_async_task()` 第242-251行：无超时保护
  - `start()` 第310-316行：job 未配置 `max_instances`
- 每日播客生成: `backend/services/podcast_generator.py`
  - `select_articles()` 第121-206行：查询不到文章时播客失败

## 修复方案

### 立即恢复
1. 重启后端容器，释放卡死的任务实例

### 代码修复
1. **APScheduler job 配置 `max_instances=3`**：允许最多3个实例并发运行，避免单实例卡死阻塞所有后续任务
2. **任务添加超时保护**：使用 `asyncio.wait_for()` 为异步任务添加 45 分钟超时，超时时强制取消
3. **播客生成同样添加超时保护**

### 注意事项
- 超时时间设为 45 分钟（小于 1 小时的调度间隔），确保即使超时也能在下一个小时开始前完成
- `max_instances=3` 允许有限并发，即使一个实例卡死，后续任务仍能执行

## 修复状态

- [x] 问题定位
- [x] 文档记录
- [x] 代码修复
- [x] 服务恢复（容器已重启）
- [ ] 验证下一小时抓取任务正常执行

## 修复记录

**修复文件**: `backend/scheduler/feed_scheduler.py`

**修复时间**: 2026-04-19

**修改内容**:
1. `_run_async_task()`: 添加 `asyncio.wait_for()` 45分钟超时保护，超时时记录错误日志而非无限挂起
2. `_run_podcast_generation()`: 添加 `asyncio.wait_for()` 30分钟超时保护
3. `start()`: RSS 抓取 job 添加 `max_instances=3`，允许有限并发避免单实例卡死阻塞所有后续任务

**服务恢复**: 2026-04-19 11:05 UTC 重启 `docker-api-1` 容器，释放卡死的任务实例

## 相关提交

- （待提交）

## Review意见

## Feature: feed-update-and-podcast-generation-failure
- problem 1：
  - level: p1
  - decription: [Boundary] The `max_instances=3` change on `fetch_all_feeds_hourly` turns a single blocked scheduler run into up to three overlapping full refresh sweeps, but the downstream refresh path is not idempotent enough for that. `backend/scheduler/feed_scheduler.py:319-325` now allows three concurrent executions of `fetch_all_active_feeds()`, and each execution loops through every active user/feed in `backend/scheduler/feed_scheduler.py:64-149`. The duplicate guard in `backend/utils/feed_refresher.py:123-168` is a read-before-write check (`article_exists()` before `store_article()`), so two overlapping scheduler runs can both miss the existence check and both perform summary generation, search indexing, and quota-side effects for the same article before the first run finishes writing the cache. In particular, `backend/utils/feed_refresher.py:146-160` can record AI summary usage twice for one article when the summary cache is still cold. This fixes the "all future runs are skipped" symptom, but it introduces a new production risk: duplicated expensive work and inflated usage counters under slow refresh conditions.
  - fix suggestion: Keep the hourly job single-flight at the scheduler level and solve the stall with cancellation/timeout at the feed or request layer instead of allowing overlapping whole-job runs. Concretely, prefer `max_instances=1` plus stricter per-feed/network timeouts, `coalesce=True`, and/or an explicit process-wide lock/lease so only one full refresh sweep can run at a time. If overlapping runs must stay enabled, the refresh path needs a real idempotency barrier around summary generation and usage recording, not just a pre-insert existence check.
  - decision and reason(by claude):
    - ✅ 接受 - 已移除 `max_instances=3`，改为 `coalesce=True`。这样保持每小时任务单实例运行（避免重叠执行导致重复摘要生成和配额副作用），同时当任务跳过时合并为一次 catch-up 执行，解决了阻塞后所有后续执行被跳过的问题。

- problem 2：
  - level: p2
  - decription: [Boundary] The new event-loop wrappers only close the loop on the success path. In `backend/scheduler/feed_scheduler.py:242-256` and `backend/scheduler/feed_scheduler.py:296-308`, `loop.close()` is inside the `try` body, so any `TimeoutError` or unexpected exception skips loop cleanup entirely. That means the exact failure mode this fix is trying to survive can also leak per-run loop resources and leave the worker thread with a stale current event loop. It is not guaranteed to explode immediately, but repeated timeout incidents will accumulate avoidable scheduler-side risk.
  - fix suggestion: Move loop lifecycle management into `finally`, for example: create the loop before `try`, call `asyncio.set_event_loop(loop)`, then in `finally` run `asyncio.set_event_loop(None)` and `loop.close()` if the loop was created. If async generators or pending tasks are possible, shut them down explicitly before closing the loop.
  - decision and reason(by claude):
    - ✅ 接受 - 已将 `_run_async_task()` 和 `_run_podcast_generation()` 中的事件循环清理（`shutdown_asyncgens()`、`set_event_loop(None)`、`loop.close()`）全部移入 `finally` 块。无论正常完成、超时还是异常，事件循环都会被正确释放，避免资源泄漏。

- problem 3：
  - level: p2
  - decription: [Maintainability] There is no automated regression coverage for the scheduler behavior that caused this outage. The changed control flow lives in `backend/scheduler/feed_scheduler.py:242-325`, but there are no matching scheduler tests under `tests/` for timeout handling, skipped-run recovery, or overlap side effects. Given that this bug already caused a production stop-the-world failure, leaving the fix untested makes future refactors of APScheduler wiring, feed refresh behavior, or timeout values much more likely to reintroduce the same class of outage unnoticed.
  - fix suggestion: Add focused unit tests for `FeedScheduler` with stubbed `fetch_all_active_feeds()` / `generate_daily_podcasts()` implementations. At minimum, cover: a run timing out and releasing resources, the next scheduled invocation still being allowed, and concurrent invocations not double-counting AI summary usage or other side effects if overlap is intentionally enabled.
  - decision and reason(by claude):
    - ✅ 接受 - 已添加 `tests/backend/scheduler/test_feed_scheduler.py`，覆盖：
      1. 异步任务超时后正常返回且不抛未处理异常；
      2. 超时后下一次调用仍能正常执行（验证事件循环资源彻底释放）。
      两个测试均已通过。


## Comments and Future suggestion

- The timeout direction is good, but I would not consider this fix fully safe until the scheduler is made single-flight again or the refresh side effects become truly idempotent under overlap.
