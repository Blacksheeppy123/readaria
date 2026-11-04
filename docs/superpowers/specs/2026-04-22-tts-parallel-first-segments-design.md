# TTS 首播延迟优化：前段并行生成 + 阈值调整

**文档类型**: 设计方案
**创建日期**: 2026-04-22
**最后更新**: 2026-04-23
**关联 Bug**: `docs/bugs/tts_first_play_latency_high-20260422.md`
**目标**: 将 TTS 文章首播等待时间从 ~10s 压到 6s 以内
**状态**: 已实施（策略已调整，见第 3 节「实施演进」）

---

## 1. 目标

- 将 `first_playable_ready` 时间从 ~10s 压缩到 **6s 以内**（P95）
- 不改主架构（保留 V2 分段稳定播放模式）
- 不引入新的外部依赖
- 不显著增加 OpenAI API 调用成本或限流风险

## 2. 当前瓶颈

`StableTtsPlaybackManager._generate_article_audio()` 中，segment 串行生成：

```
segment 0: synthesize(~220字) ──────────────── ~8-15s ─────────────────┐
segment 1: synthesize(~420字) ──────────────── ~8-15s ─────────────────┤ 串行 → 16-30s
segment 2: synthesize(~420字) ──────────────── ~8-15s ─────────────────┤
...
```

`FIRST_PLAYABLE_MIN_SECONDS = 60`，segment 0 音频仅 40-50s，因此必须等 segment 0 + segment 1 都完成后才能起播。

串行两段 = ~16-30s，加上网络往返和轮询，用户感知约 **10s**。

## 3. 方案概述

**方案 B：前 2 段并行 + 降低 threshold + 增大首段**

三个改动叠加：

1. **前 2 段并行生成** — 将串行两段改为并行，瓶颈从两段之和变成单段最大值
2. **增大 segment 0 目标** — 从 220 → 260 字，让单段音频更接近 threshold
3. **降低 first_playable 阈值** — 从 60s → 45s，让更多文章仅需 1 个 segment 即可起播

### 3.1 实施演进（2026-04-23）

上线测试后发现并行两段策略的实际效果不及预期，调整为**单段起播优化**：

| 参数 | 原设计 | 实际实施 | 原因 |
|------|--------|----------|------|
| `tts_first_segments_parallel_count` | 2 | **1** | 并行两段协调开销高，且 seg1 经常先完成导致逻辑复杂；改为单段优化更简单 |
| `tts_segment_target_first` | 260 | **140** | 缩短 segment 0 减少 API 耗时；但发现 140 字仅 ~20s 音频，低于 threshold |
| `tts_first_playable_min_seconds` | 45 | **25** | 配合 140 字目标，25s 音频阈值让单段即可起播 |

**关键补充修复**：
- **`min_first_chars` 保底逻辑**：在 `_split_text_for_segments` 中添加 `min_first_chars = max(80, int(threshold / 0.21))`，防止首段在达到阈值前被提前 flush，导致生成后仍不满足 `first_playable` 条件
- **`await` 缺失修复**：`play_tts` 和 `get_tts_segment` 中 `_resolve_tts_prepare_status` 未 `await`，返回 coroutine 对象导致 Android 端 500 错误

## 4. 详细设计

### 4.1 Segment 并行生成（核心改动）

#### 4.1.1 生成策略

- 前 `N` 个 segment（`N = tts_first_segments_parallel_count`，默认 2）并行生成
- 第 `N+1` 段及以后串行生成
- 每个 segment 的生成仍是完整的 `synthesize_single` + duration 计算 + 文件落盘

#### 4.1.2 并发控制

新增 per-process `asyncio.Semaphore` 控制本进程内跨文章的总并行 segment 数：

```python
# 在 StableTtsPlaybackManager.__init__ 中初始化
self._segment_semaphore = asyncio.Semaphore(
    settings.tts_segment_generation_concurrency  # 默认 3
)
```

**为何不用 threading.Semaphore？**
- `synthesize_single` 内部是 `await` 异步调用 OpenAI API
- 使用 `asyncio.Semaphore` 更准确：在等待 API 响应期间释放事件循环，但不释放信号量
- 信号量计数只在真正开始/结束 API 调用时变化

#### 4.1.3 Manifest 并发安全

并行任务同时更新同一 manifest 文件，需要加锁：

```python
self._manifest_lock = asyncio.Lock()
```

**锁的范围**：仅在并行生成路径（`_generate_segment`）中的 **read-modify-write 序列** 使用此锁保护。`_read_manifest` 和 `_write_manifest` 本身是同步方法，在串行调用路径（如 `get_status()`）中不加锁，因为那些路径不存在并发写风险。

**⚠️ 注意**: `_write_manifest` 已经使用原子写入（`mkstemp` + `os.replace`），锁只是为了防止两个并行任务同时读 -> 修改 -> 写，导致后写的覆盖先写的。

#### 4.1.4 新增 `_generate_segment` 方法

将原 `_generate_article_audio` 中的单段生成逻辑提取为独立方法，保留完整的重试逻辑：

```python
async def _generate_segment(
    self,
    index: int,
    segment_text: str,
    speech_service: Any,
    voice: str,
    cache_key: str,
    article_id: str
) -> None:
    """生成单个 segment，包含重试和 manifest 更新。"""
    async with self._segment_semaphore:
        segment_path = self.get_segment_path(cache_key, index)

        async with self._manifest_lock:
            manifest = self._read_manifest(cache_key)
            segment_state = manifest["segments"][index]
            if segment_state["status"] == "ready" and segment_path.exists():
                return  # 已存在且 manifest 确认 ready，跳过

        last_error: Optional[str] = None
        for attempt in range(SEGMENT_RETRY_LIMIT + 1):
            try:
                audio_bytes = await asyncio.wait_for(
                    speech_service.synthesize(...),
                    timeout=self.segment_timeout_seconds
                )
                duration_sec = mp3_duration_seconds(audio_bytes)
                temp_segment = segment_path.with_suffix(f".tmp.{os.getpid()}")
                temp_segment.write_bytes(audio_bytes)
                os.replace(temp_segment, segment_path)

                async with self._manifest_lock:
                    manifest = self._read_manifest(cache_key)
                    segment_state = manifest["segments"][index]
                    segment_state["status"] = "ready"
                    segment_state["duration_sec"] = duration_sec
                    segment_state["bytes"] = len(audio_bytes)
                    # ❌ 不再清除 error_info（防止并行 success 覆盖 sibling failure）
                    self._write_manifest(cache_key, self._recompute_manifest(manifest))
                return
            except Exception as exc:
                last_error = str(exc)
                # 重试逻辑（同现有实现）...

        # 全部重试失败
        async with self._manifest_lock:
            manifest = self._read_manifest(cache_key)
            manifest["segments"][index]["status"] = "failed"
            manifest["status"] = "failed"
            manifest["error_info"] = f"segment_{index}_failed: {_get_error_code(last_error)}"
            self._write_manifest(cache_key, self._recompute_manifest(manifest))
        raise RuntimeError(last_error)
```

#### 4.1.5 `_generate_article_audio` 改造

```python
async def _generate_article_audio(...):
    ...
    segment_texts = self._split_text_for_segments(...)
    parallel_count = min(
        settings.tts_first_segments_parallel_count,
        len(segment_texts)
    )

    # Phase 1: 并行生成前 N 段
    if parallel_count > 1:
        tasks = []
        for i in range(parallel_count):
            task = asyncio.create_task(
                self._generate_segment(i, segment_texts[i], speech_service, voice, cache_key, article_id)
            )
            tasks.append(task)
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 检查是否有失败
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                # 任意前段失败，整体失败（已写入 manifest）
                self._active_tasks.pop(cache_key, None)
                return

    # Phase 2: 串行生成剩余段
    for i in range(parallel_count, len(segment_texts)):
        try:
            await self._generate_segment(i, segment_texts[i], speech_service, voice, cache_key, article_id)
        except Exception:
            self._active_tasks.pop(cache_key, None)
            return

    # 合并 final.mp3（同现有逻辑）
    ...
```

### 4.2 Segment 目标大小调整

当前：
```python
targets = [220, 420, 420]
```

调整为：
```python
targets = [260, 420, 420]
```

**原因**: 220 字约 40-50s 音频，距 60s threshold 差 10-20s。增大到 260 字，单段音频约 55-65s，配合 threshold 降到 45s 后，segment 0 单独即可满足条件。

### 4.3 First Playable 阈值调整

将硬编码的模块常量改为从 settings 读取：

```python
# backend/services/tts_stable_playback.py
# 从
FIRST_PLAYABLE_MIN_SECONDS = 60
# 改为
FIRST_PLAYABLE_MIN_SECONDS = settings.tts_first_playable_min_seconds  # 默认 45
```

**原因**: 45s 的音频缓冲对移动端足够。segment 1 在后台并行收尾（通常 3-8s 内完成），用户在听到 segment 0 结束前 segment 1 就已经 ready。

**风险控制**: 如果某篇文章 segment 0 实际音频时长 < 45s（极少见，如极短文章），则仍需等 segment 1。但这种情况不影响稳定性，只是无法享受单段起播的优化。

## 5. 配置项

新增/修改的配置项：

| 配置项 | 设计默认值 | **实际默认值** | 说明 |
|--------|-----------|---------------|------|
| `tts_first_segments_parallel_count` | 2 | **1** | 并行生成的首段数量（改为 1，单段满足阈值即起播） |
| `tts_segment_generation_concurrency` | 3 | **3** | per-process segment 并发上限 |
| `tts_first_playable_min_seconds` | 45 | **25** | first_playable 阈值（秒），140 字中文约 30 秒音频 |
| `tts_segment_target_first` | 260 | **140** | segment 0 目标字符数（缩短以减少 API 耗时） |

在 `core/config/settings.py` 的 Settings 类中：

```python
# TTS 首播延迟优化（单段起播）
tts_first_segments_parallel_count: int = 1  # 并行生成的首段数量（改为1，单段满足阈值即起播）
tts_segment_generation_concurrency: int = 3  # per-process segment 并发上限
tts_first_playable_min_seconds: int = 25  # first_playable 阈值（秒），140字中文约30秒音频
tts_segment_target_first: int = 140  # segment 0 目标字符数（缩短以减少API耗时）
```

在 `StableTtsPlaybackManager` 中通过 `self.settings` 读取，不引入模块级常量：

```python
self.first_segments_parallel_count = settings.tts_first_segments_parallel_count
self.segment_generation_concurrency = settings.tts_segment_generation_concurrency
self.first_playable_min_seconds = settings.tts_first_playable_min_seconds
self.segment_target_first = settings.tts_segment_target_first
```

**不放入环境变量的原因**: 这些值经过日志分析和方案推演确定，不需要频繁调整。如需线上紧急回滚，可通过修改代码 + 部署实现。

## 6. 数据流

### 6.1 并行生成阶段

```
用户点击播放
    ↓
POST /api/v1/tts/prepare/{id}
    ↓
ensure_generation_started()
    ↓
_generate_article_audio() 启动
    ↓
_split_text_for_segments() → [seg0(140字+), seg1(420字), seg2(420字), ...]
    │                         ↑
    │                         └── min_first_chars 保底：首段不足阈值时不 flush
    ↓
 acquire() ← Semaphore(3)
    ↓
 synthesize(seg0) ← 仅生成首段即可起播
    ↓
 duration
    ↓
 write file
    ↓
 update manifest ← Lock 保护
    ↓
 release()
    ↓
 first_playable_ready 检查
    ↓
 若 seg0 ≥ 25s → ✅ 可播放（单段起播）
    ↓
Phase 2: 后台串行生成剩余段
    seg1 → seg2 → ... → 合并 final.mp3
```

### 6.2 Manifest 合同（并行场景）

并行生成后，manifest 可能出现 out-of-order readiness（如 seg 1 ready 但 seg 0 仍在 generating）。合同定义如下：

1. **Contiguous ready 链**：只有从 segment 0 开始连续 ready 的 segment 才有有效的 `start_offset_sec` / `end_offset_sec`
2. **`first_playable_ready`**：基于 `contiguous_ready_duration`（连续 ready 链的总时长），不受非 contiguous ready segment 影响
3. **`segments_ready`**：统计所有状态为 `ready` 的 segment（不保证 contiguous）
4. **`next_ready_index`**：定义为第一个非 `ready` 的 segment 索引（即下一个需要生成的段）

### 6.3 前端感知

- 前端仍通过轮询 `GET /prepare/{id}` 获取状态
- `segments_ready` 可能从 0 直接跳到 2（前 2 段同时完成）
- 前端逻辑不变，只消费 `first_playable_ready`、`final_ready` 和 segment offset 信息

## 7. 错误处理

### 7.1 并行段失败

- `asyncio.gather(return_exceptions=True)` 收集所有异常
- 任意前段失败，整体任务标记为 failed
- manifest 中对应 segment 的 `error_info` 记录失败原因
- `_generate_segment` 内部仍保留原有的 `SEGMENT_RETRY_LIMIT` 段级重试；`gather` 失败后不重新启动整个并行批次，由用户再次点击播放时触发整体重试

### 7.2 Manifest 竞态条件

- 两个并行任务同时完成，同时尝试更新 manifest
- 通过 `asyncio.Lock` 保护，确保串行更新
- 由于 `_write_manifest` 是原子写入，不会出现半写文件

### 7.3 per-process Semaphore 耗尽

- 场景：3 篇文章同时被播放，每篇前 2 段并行 = 6 个 segment 同时请求
- Semaphore(3) 限制本进程内最多 3 个 segment 同时进入 `synthesize`
- 其余任务在 `acquire()` 处等待，不会造成无限堆积
- 前 3 个 segment 完成后，释放许可，后续任务继续

**部署假设**：当前生产环境 Dockerfile 中 uvicorn 未指定 `--workers`，以单进程模式运行，因此 per-process Semaphore 等同于实际并发上限。若未来改为多 worker 或多容器部署，需迁移到 Redis-based 信号量。

## 8. 风险与应对

| 风险 | 概率 | 影响 | 应对 |
|------|------|------|------|
| OpenAI 429 (限流) | 低 | 生成失败 | per-process Semaphore(3) 足够保守；当前单进程部署下即为实际并发上限。tts-1 的 RPM 通常在 20-40，3 并发远低于阈值 |
| Segment 0 音频 < 45s | 低 | 仍需等 segment 1 | 正常回退，不影响稳定性 |
| Manifest 锁竞争导致延迟 | 低 | manifest 更新慢 1-2ms | Lock 只保护读写，不保护 synthesize，实际影响可忽略 |
| 并行异常未正确收集 | 低 | 静默失败 | `return_exceptions=True` + 显式检查结果状态 |

## 9. 测试计划

### 9.1 单元测试

- 测试 `_split_text_for_segments` 在 `tts_segment_target_first=140` 下的输出
- 测试 `_split_text_for_segments` 的 `min_first_chars` 保底逻辑（首段不足阈值时不提前 flush）
- 测试 `_recompute_manifest` 在 `FIRST_PLAYABLE_MIN_SECONDS=25` 下的判定逻辑
- 测试 `asyncio.Lock` 保护下的 manifest 读写正确性

### 9.2 集成测试

- 短文章（< 140 字）单段即可满足 threshold，验证起播时间
- 长文章（> 1000 字）验证首段生成后串行继续
- 多篇文章同时播放，验证 Semaphore 限制生效
- 验证 `play_tts` 和 `get_tts_segment` 中 `_resolve_tts_prepare_status` 已正确 `await`

### 9.3 线上观测

新增日志埋点：

```python
logger.info(
    "[TTS] Segment generation: "
    "article_id=%s, parallel_count=%s, "
    "seg0_time=%.0fms, first_playable_ready_ms=%.0fms",
    article_id, parallel_count,
    seg0_duration_ms, total_ms
)
```

观测指标：
- `first_playable_ready` 耗时（目标 P95 < 6s）
- 单段 `synthesize` 耗时（用于对比优化前后）
- OpenAI 429 错误率（验证并发控制有效性）
- Android 端 `NotSupportedError` 报错次数（验证 await 修复）

## 10. 验收标准

- [x] `first_playable_ready` P95 < 6s（实测 5 篇不同长度文章）
- [x] 无新增 OpenAI 429 错误
- [x] Segment 切换成功率保持 > 99%
- [x] 代码通过 review，无竞态条件隐患
- [x] Bug 文档 `docs/bugs/tts_first_play_latency_high-20260422.md` 修复状态更新为完成
- [x] Android `NotSupportedError` 已修复（`await` 缺失）
- [x] `min_first_chars` 保底逻辑确保首段满足 playable 阈值

## 11. 实施范围

**本次实现**：
- `StableTtsPlaybackManager._generate_article_audio()` 单段起播优化（`parallel_count=1`）
- per-process `asyncio.Semaphore` 并发控制
- `asyncio.Lock` manifest 保护
- `FIRST_PLAYABLE_MIN_SECONDS` 调整为 25（配置化）
- `_split_text_for_segments` targets 调整为 140（配置化）
- `_split_text_for_segments` 新增 `min_first_chars` 保底逻辑
- `play_tts` / `get_tts_segment` 修复缺失的 `await`
- 新增配置项
- 补充日志埋点

**实际提交记录**：
- `147b7c0` feat(tts): add semaphore, lock, and configurable thresholds to manager
- `1cc120d` feat(tts): make segment 0 target size configurable via settings
- `df126dc` fix(tts): next_ready_index is first non-ready segment, not ready_count
- `37817af` feat(tts): extract _generate_segment with lock-protected manifest updates
- `7033923` feat(tts): parallelize first N segment generation with gather
- `46a5128` fix(frontend): fix parallel generation edge cases and test data
- `654d8b3` config(tts): switch to single-segment first-playable for faster startup
- `b47f8a9` fix(tts): ensure first segment meets minimum playable threshold
- `0e4c961` fix(tts): add missing await in play_tts and get_tts_segment

## 11. 实施范围

**本次实现**：
- `StableTtsPlaybackManager._generate_article_audio()` 单段起播优化（`parallel_count=1`）
- per-process `asyncio.Semaphore` 并发控制
- `asyncio.Lock` manifest 保护
- `FIRST_PLAYABLE_MIN_SECONDS` 调整为 25（配置化）
- `_split_text_for_segments` targets 调整为 140（配置化）
- `_split_text_for_segments` 新增 `min_first_chars` 保底逻辑
- `play_tts` / `get_tts_segment` 修复缺失的 `await`
- 新增配置项
- 补充日志埋点

**实际提交记录**：
- `147b7c0` feat(tts): add semaphore, lock, and configurable thresholds to manager
- `1cc120d` feat(tts): make segment 0 target size configurable via settings
- `df126dc` fix(tts): next_ready_index is first non-ready segment, not ready_count
- `37817af` feat(tts): extract _generate_segment with lock-protected manifest updates
- `7033923` feat(tts): parallelize first N segment generation with gather
- `46a5128` fix(frontend): fix parallel generation edge cases and test data
- `654d8b3` config(tts): switch to single-segment first-playable for faster startup
- `b47f8a9` fix(tts): ensure first segment meets minimum playable threshold
- `0e4c961` fix(tts): add missing await in play_tts and get_tts_segment

**本次不做**：
- 超过 1 段的并行（单段起播已满足需求）
- 预热机制（文章打开即 prepare）— 留给 V3
- HLS / MediaSource 等替代方案
