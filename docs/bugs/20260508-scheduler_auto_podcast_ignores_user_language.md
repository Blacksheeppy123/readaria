# Auto-Podcast Scheduler Ignores User's Preferred Language

## 问题描述

test-user 账户的 `preferred_language` 在数据库中为 `'en'`，但每天 00:00 由调度器自动生成的「每日播客」（Daily Podcast）内容是中文的，与用户语言偏好不一致。

### 用户操作步骤
1. test-user 登录，语言偏好设置为 English（数据库 `users.preferred_language = 'en'`）
2. `auto_podcast_enabled = TRUE`，无需手动操作
3. 等待第二天 00:00 调度器自动生成每日播客
4. 早上打开 App 查看新播客

### 实际表现 vs 预期表现
- **实际**：标题为中文（如 "每日播客（5月8日）- 深度分析：DeFi安全..."），播客脚本/音频也是中文
- **预期**：英文偏好用户应得到英文播客（如 "Daily Podcast (May 8) - ..."）

### 数据库证据（podcasts 表，test-user）

| ID  | 创建时间             | 标题语言 | 备注                     |
|-----|----------------------|----------|--------------------------|
| 393 | 2026-05-08 00:08:09  | 中文     | 调度器自动生成（midnight）|
| 390 | 2026-05-07 03:54:14  | 英文     | 手动 API 重新生成        |
| 389 | 2026-05-07 01:39:20  | 英文     | 手动重试（失败）         |
| 388 | 2026-05-07 00:06:42  | 中文     | 调度器自动生成（midnight）|
| 377 | 2026-05-06 00:14:37  | 中文     | 调度器自动生成（midnight）|
| 350 | 2026-05-05 00:19:07  | 中文     | 调度器自动生成（midnight）|
| 307 | 2026-05-03 21:32:41  | 英文     | 手动 API 生成            |
| 227 | 2026-04-29 00:00:00  | 中文     | 调度器自动生成（midnight）|

**规律一目了然**：所有 `00:xx` 由调度器触发的播客都是中文，所有用户手动通过 API 触发的播客都是英文。

## 原因定位

### 根本原因

之前 [`podcast_language_preference_ignored-20260422.md`](podcast_language_preference_ignored-20260422.md) 修复了**手动**触发的 `/api/v1/podcasts/generate` 路径——使用 `current_user['preferred_language']` 决定语言（[`backend/api/main.py:2647-2660`](../backend/api/main.py#L2647-L2660))。

但是**自动调度器路径未一并修复**：

[`backend/scheduler/feed_scheduler.py:210-215`](../backend/scheduler/feed_scheduler.py#L210-L215)：

```python
podcast_id = await podcast_generator.generate_daily_podcast(
    user_id=user_id,
    style=settings.podcast_style_default,
    time_range_hours=24,
    max_articles=settings.podcast_max_articles
    # ❌ 缺少 language 参数！
)
```

`generate_daily_podcast()` 的签名（[`backend/services/podcast_generator.py:40-47`](../backend/services/podcast_generator.py#L40-L47))：

```python
async def generate_daily_podcast(
    self,
    user_id: str,
    style: str = "deep_dive",
    time_range_hours: int = 24,
    max_articles: int = 10,
    language: str = "zh"   # ⚠️ 默认 zh
) -> int:
```

**调度器没传 `language`** → 落到默认值 `"zh"` → 不论用户偏好都生成中文播客。

### 具体流程问题

1. APScheduler 定时任务每天 00:00 触发 `_run_podcast_generation()`
2. `generate_daily_podcasts()` → `_generate_daily_podcasts_impl()`
3. `db_manager.get_podcast_enabled_user_ids()` 只查询用户 ID（[`backend/storage/database.py:1813-1832`](../backend/storage/database.py#L1813-L1832))，**未返回 `preferred_language`**
4. for 循环中调用 `generate_daily_podcast(user_id=...)`，**未传 `language`**
5. `generate_daily_podcast()` 使用默认 `language="zh"` → 中文 prompt → 中文脚本 → 中文 TTS

### 影响范围

数据库中所有 `auto_podcast_enabled = TRUE` 且 `preferred_language = 'en'` 的用户：

```
test-user                  | en | t  ← 受影响
onboarding-experience-en   | en | t  ← 受影响（英文体验账户每天拿到中文播客）
onboarding-experience-zh   | zh | t  ← 不受影响（恰好与默认值一致）
```

`onboarding-experience-en` 同样会拿到中文播客，破坏了体验账户的可信度（之前的 bug doc `2026-04-30-onboarding-zh-starter-pack-and-podcast-language.md` 已修过 `scripts/generate_experience_podcasts.py` 离线脚本，但调度器实时路径仍是漏的）。

### 相关代码位置

- `backend/scheduler/feed_scheduler.py:210-215` — 调度器调用 `generate_daily_podcast()` 时缺少 `language` 参数
- `backend/storage/database.py:1813-1832` — `get_podcast_enabled_user_ids()` 只返回 ID，未返回语言
- `backend/services/podcast_generator.py:40-47` — `generate_daily_podcast()` 默认 `language="zh"`（默认值偏中文，与产品最新方向不一致，但保留以防调用方依赖）

## 修复方案

### 方案：调度器从用户表读取语言并显式传递（推荐）

1. **扩展 `get_podcast_enabled_user_ids()`**：改为返回 `(user_id, preferred_language)` 元组，避免在循环里逐个二次查询。也可以新增一个 `get_podcast_enabled_users()` 方法，保持原方法兼容。

2. **更新调度器 `_generate_daily_podcasts_impl()`**：
   ```python
   for user_id, preferred_language in users:
       ...
       language = 'en' if (preferred_language or '').lower() == 'en' else 'zh'
       podcast_id = await podcast_generator.generate_daily_podcast(
           user_id=user_id,
           style=settings.podcast_style_default,
           time_range_hours=24,
           max_articles=settings.podcast_max_articles,
           language=language,  # ✅ 显式传递
       )
   ```

3. **语言归一化**：与手动路径 `backend/api/main.py:2647-2648` 保持一致 —— 仅当 `preferred_language == 'en'` 才使用 `en`，其他（包括 `NULL`/空字符串/其它语言代码）统一回落到 `zh`。这与现有缓存逻辑（`article_summaries(language)` 仅有 `zh`/`en`）契合。

### 可选：调整 `generate_daily_podcast()` 默认值（解耦风险）

把 `language: str = "zh"` 改为 `language: str = "en"` 与产品默认值对齐，避免类似的"忘记传参"再次踩坑。但这会影响仍依赖默认值的旧调用点，需要全局 grep 确认无遗漏后再动。建议本次先聚焦修复调度器路径，默认值调整放到下一次集中清理（可在文档中留 follow-up）。

### 测试验证策略

1. 单元测试：
   - 给 `_generate_daily_podcasts_impl` mock 一个 `(user_id, 'en')` 用户，断言调用 `generate_daily_podcast` 时 `language='en'`。
   - 同样 mock 一个 `(user_id, 'zh')` 用户，断言 `language='zh'`。
   - mock `(user_id, None)` / `(user_id, '')` 等边界，断言落到 `'zh'`。

2. 线上回归：
   - 修复部署后，第二天检查 test-user `id=394+` 的播客标题是否变成 `Daily Podcast (May 9) - ...`
   - 同步检查 `onboarding-experience-en` 是否也恢复英文

## 修复状态

- [x] 问题定位
- [x] 文档记录
- [x] 代码修复
- [x] 测试验证

## 修复记录

**修复文件**:
- `backend/scheduler/feed_scheduler.py`
- `backend/storage/database.py`（新增 `get_podcast_enabled_users()`）
- 单元测试：`tests/backend/scheduler/test_feed_scheduler_podcast_language.py`（新增）

**修复时间**: 2026-05-08

**修改内容**:
1. `backend/storage/database.py`：新增 `get_podcast_enabled_users()` 方法，返回 `(user_id, preferred_language)` 元组列表，避免循环内二次查询。
2. `backend/scheduler/feed_scheduler.py`：
   - 调度器播客生成改用 `get_podcast_enabled_users()`
   - 循环中根据 `preferred_language` 做归一化：`en`（不区分大小写）→ `language='en'`，其他（含 `None`/空串/其他语言）→ `language='zh'`
   - 显式将 `language` 参数传入 `generate_daily_podcast()`
3. `tests/backend/scheduler/test_feed_scheduler_podcast_language.py`：新增 10 个测试用例
   - 8 组参数化语言归一化测试（en/EN/En/zh/空串/None/fr/ja）
   - 多用户不同语言场景测试
   - podcast_enabled=False 跳过测试

## 相关提交

- 待提交

## 关联 Bug 记录

- `docs/bugs/podcast_language_preference_ignored-20260422.md` — 修复了手动 API 路径，但漏掉调度器路径
- `docs/bugs/2026-04-30-onboarding-zh-starter-pack-and-podcast-language.md` — 修复了 `scripts/generate_experience_podcasts.py` 离线生成脚本，但调度器实时路径同样漏掉
- `docs/bugs/[fix]newuser_language_preference.md` — 用户级语言偏好的整体设计与 backfill
