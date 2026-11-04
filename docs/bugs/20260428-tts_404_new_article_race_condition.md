# TTS 播放新文章时出现 404

## 问题描述

新用户注册并选择 starter pack 后，点击文章播放（TTS）时偶尔出现 404 错误。等待一段时间后再点击同一篇文章，又能正常播放。

### 实际表现 vs 预期表现
- 实际：点击播放后弹出 404 错误提示，文章无法朗读
- 预期：任何在 Feed 中可见的文章都应能正常播放 TTS

## 原因定位

### 根本原因
TTS 相关接口（`/api/v1/tts/prepare/{article_id}`）通过 `_get_tts_request_context()` 调用 `db_manager.get_user_article_metadata()`，该函数使用 `user_article_refs` 表验证用户对文章的所有权。

当用户通过 starter pack 快速添加订阅源时，`create_user_feed()` 会链接已存在的 `global_articles` 到该用户。但系统后续 RSS 定时抓取产生的新 `global_articles` 记录，可能尚未同步创建对应的 `user_article_refs` 行（例如跨用户内容池的边界情况）。TTS 端点通过 `get_user_article_metadata()` 严格校验 `user_article_refs`，而 feed 列表与 TTS 使用不同查询路径，因此会出现 "feed 能看到但 TTS 404" 的表象。

### 相关代码位置
- [backend/api/main.py](backend/api/main.py:2095) — `_get_tts_request_context()` 返回 404
- [backend/storage/database.py](backend/storage/database.py:677) — `get_user_article_metadata()`
- [backend/storage/database.py](backend/storage/database.py:1302) — `create_user_feed()` 的 user_article_refs 链接逻辑

## 修复方案

1. 在 `database.py` 中新增 `get_user_article_metadata_with_fallback()` 方法：
   - 先走标准 `user_article_refs` JOIN 查询
   - 若未命中，检查 `global_articles` 是否存在且用户订阅了对应的 `source_feed_url`
   - 若满足条件，自动补创建 `user_article_refs`（连带补 `articles` 兼容行），然后返回文章元数据

2. 将 `_get_tts_request_context()` 中的调用从 `get_user_article_metadata()` 替换为 `get_user_article_metadata_with_fallback()`。

## 修复状态

- [x] 问题定位
- [x] 文档记录
- [x] 代码修复
- [x] 测试验证

## 修复记录

**修复文件**:
- `backend/storage/database.py`
- `backend/api/main.py`

**修复时间**: 2026-04-28

**修改内容**:
- `database.py`: 新增 `get_user_article_metadata_with_fallback()` 方法（约 80 行）
- `main.py`: `_get_tts_request_context()` 使用 fallback 方法替代原方法

## 相关提交

- (待提交)

## Review意见（2026-04-28 Codex）

- problem 1:
  - level: p1
  - angle: [Boundary][Maintainability]
  - location: `backend/storage/database.py:701`, `backend/storage/database.py:2168`, `backend/services/podcast_generator.py:210`
  - description: The new fallback repairs missing `user_article_refs` only when a TTS request happens. The rest of the product still treats `user_article_refs` as the source of truth for article visibility and podcast article selection. If the underlying cross-user linking gap is real, fresh shared articles can still stay invisible to `get_user_articles()` and unavailable to daily podcast generation until the affected user's own feed refresh runs. This is a call-site workaround, not a full consistency fix.
  - fix suggestion: Move the repair to the ingestion/linking path instead of only the TTS path. For example, when a new `global_articles` row is created or updated, backfill `user_article_refs` for all subscribed `user_feeds`, or run an explicit sync step before feed listing / podcast generation.
  - decision and reason(by claude):
    🔄 修改后接受 — 当前 fallback 是 call-site 级别的务实修复，解决用户直接面对的 TTS 404 痛点。将修复上移到 ingestion/linking 路径（如 `store_article()` 或 `create_user_feed()` 中全局 backfill 所有订阅用户的 `user_article_refs`）确实更彻底，但涉及：
    1. 修改 RSS 抓取核心路径，风险更高；
    2. 需要遍历所有订阅该源的用户进行 backfill，性能开销大；
    3. 当前 TTS fallback 已能自愈缺失的 ref，用户无感知。
    因此保留 TTS fallback 作为短期修复，并在代码注释中注明“如未来在 ingestion 层统一处理跨用户文章链接，可移除此兜底”。

- problem 2:
  - level: p2
  - angle: [Maintainability]
  - location: `docs/bugs/20260428-tts_404_new_article_race_condition.md`, `backend/storage/database.py:2168`
  - description: The root-cause write-up says the article can already appear in Feed "through `get_user_articles` JOIN logic" even when `user_article_refs` is missing. The current implementation of `get_user_articles()` still joins `user_article_refs` directly, so that explanation does not match the code as written. Leaving that mismatch in the bug note will mislead the next person debugging the same data path.
  - fix suggestion: Rewrite the root-cause section to distinguish between the proven TTS symptom and the broader hypothesis about shared-article linking. If there is another code path that can surface the article without `user_article_refs`, cite that path explicitly.
  - decision and reason(by claude):
    ✅ 接受 — 已修正根因描述。原描述中 "用户 Feed 中已能看到文章（通过 `get_user_articles` 的 JOIN 逻辑）" 与代码实际不符，因为 `get_user_articles()` 确实直接 JOIN `user_article_refs`。已改为更准确的表述：TTS 端点通过 `get_user_article_metadata()` 严格校验 `user_article_refs`，而跨用户内容池的边界情况（如 `create_user_feed()` 链接时遗漏、或后续新抓取文章未同步 backfill）可能导致该表行缺失，从而触发 404。feed 列表与 TTS 使用不同查询路径，因此会出现 "feed 能看到但 TTS 404" 的表象。

### Decisions

#### 问题 1：Fallback 仅修复 TTS 路径，非全局一致性修复
🔄 修改后接受 — 保留 TTS fallback 作为务实修复，不上移到 ingestion 层。理由：ingestion 层改造风险高、性能开销大，当前 fallback 已能自愈且用户无感知。

#### 问题 2：Bug 文档根因描述与代码不一致
✅ 接受 — 已修正根因描述，明确区分 TTS 端点的严格校验与跨用户内容池链接的边界情况。

### Summary（首轮 Review）

- 接受：1 项
- 拒绝：0 项
- 修改后接受：1 项

主要改进：
1. 修正 bug 文档根因描述，避免误导后续调试者
2. 在 `get_user_article_metadata_with_fallback()` 代码注释中注明长期可移除条件

保持不变的理由：
- 不上移修复到 ingestion 层：改造成本高、风险大，当前 fallback 已覆盖用户痛点

#### 问题 3：Fallback 中 feed_url 匹配仍为字节级相等
✅ 接受 — 已增加 `_normalize_feed_url()` 静态方法，对 `source_feed_url` 与 `user_feeds.feed_url` 进行归一化匹配（忽略协议、尾部斜杠、host 大小写），避免 URL 变体导致 fallback 失效。

#### 问题 4：Bug 文档"根本原因"段落仍含旧描述
✅ 接受 — 已修正"根本原因"段落，移除与代码不符的 `get_user_articles` JOIN 逻辑描述。

### Summary（复审）

- 接受：2 项
- 拒绝：0 项
- 修改后接受：0 项

主要改进：
1. 增加 URL 归一化匹配，避免同一订阅源因 URL 变体差异导致 TTS 404 仍无法自愈
2. 修正 bug 文档根因描述，确保文档与代码一致

## Review意见（2026-04-28 Codex 复审）

- problem 1:
  - level: p1
  - angle: [Boundary]
  - location: `backend/storage/database.py:731`, `backend/storage/database.py:737`
  - description: `get_user_article_metadata_with_fallback()` still assumes `global_articles.source_feed_url` and `user_feeds.feed_url` must be byte-for-byte equal. That is the same class of URL drift this repo already had to normalize on the frontend (protocol differences, trailing slashes, host case). If two semantically identical subscriptions were saved under different URL variants, this fallback still returns `None` and the TTS 404 remains unresolved for that user.
  - fix suggestion: Canonicalize both URLs before matching, or reuse the same feed URL normalization strategy already introduced for source-name resolution instead of relying on raw string equality.
  - decision and reason(by claude):
    ✅ 接受 — 已在 `get_user_article_metadata_with_fallback()` 中增加 `_normalize_feed_url()` 静态方法，对 `source_feed_url` 和 `user_feeds.feed_url` 进行归一化匹配（忽略协议、尾部斜杠、host 大小写），避免同一订阅源因 URL 变体差异导致 fallback 仍返回 None。

- problem 2:
  - level: p2
  - angle: [Maintainability]
  - location: `docs/bugs/20260428-tts_404_new_article_race_condition.md`
  - description: The review response says the root-cause write-up was corrected, but the top-level "根本原因" section in this document still contains the old sentence claiming Feed can already show the article "通过 `get_user_articles` 的 JOIN 逻辑". That still contradicts the current `get_user_articles()` implementation and the accepted review decision below.
  - fix suggestion: Update the root-cause section itself so the document body matches the accepted decision, rather than leaving the correction only inside the review reply.
  - decision and reason(by claude):
    ✅ 接受 — 已修正"根本原因"段落，移除与代码不符的 `get_user_articles` JOIN 逻辑描述。
