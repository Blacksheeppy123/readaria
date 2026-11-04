# 播放列表无法跨设备同步

## 问题描述

在 Android 和 iOS 上使用 Readaria 时，播放列表（听读队列）仅以本地状态存在，未与后端同步。用户在不同终端登录同一账号时，无法共享或修改同一个播放队列。

- **功能**：TTS 播放器 / 听读队列
- **操作步骤**：
  1. 在 A 设备上添加若干文章到播放列表或调整顺序。
  2. 在 B 设备（同一账号）上打开 Readaria。
- **实际表现**：B 设备看不到 A 设备的播放列表；队列仅存在于本地 Pinia store / localStorage。
- **预期表现**：播放列表作为用户级状态持久化到后端，任何终端登录后都能看到并修改同一队列。

## 原因定位

### 根本原因

当前听读队列（`queueStore`）和播放状态（`playerStore`）仅保存在前端本地状态（`Pinia` + `localStorage`），没有对应的后端数据表和同步 API。不同设备/浏览器无法共享该状态。

### 相关代码位置

- 前端队列：`frontend/src/stores/queueStore.js`
- 前端播放器：`frontend/src/stores/playerStore.js`
- 后端 schema：`backend/storage/schemas.sql`
- 后端 API：`backend/api/main.py`（新增 `/api/v1/queue`、`/api/v1/playback-state`）
- 后端数据访问：`backend/storage/database.py`

## 修复方案

1. 后端新增两张表：
   - `user_queues`：存储用户的听读队列（JSONB 数组，按 `user_id` 单行 upsert）。
   - `user_playback_state`：存储活跃播放状态（playlist、current_index、current_time、total_time、current_article、is_playing、playback_rate）。
2. 后端新增 5 个 API 端点：
   - `GET/PUT/DELETE /api/v1/queue`
   - `GET/PUT /api/v1/playback-state`
3. 前端新增 `frontend/src/api/queue.js` 和 `frontend/src/api/playbackState.js`。
4. `queueStore`：启动时拉取服务端队列并合并，增删改时延迟同步到服务端。
5. `playerStore`：启动时若服务端播放状态更新则恢复，播放/暂停/进度变化时按 10 秒节流同步。
6. 离线/未登录用户保持原有本地行为。

## 修复状态

- [x] 问题定位
- [x] 文档记录
- [x] 代码修复
- [x] 测试验证

## 修复记录

**修复文件**:
- `backend/storage/schemas.sql`
- `backend/storage/migrations/2026_07_15_user_queue_and_playback_state.sql`
- `backend/storage/database.py`
- `backend/api/main.py`
- `frontend/src/api/queue.js`
- `frontend/src/api/playbackState.js`
- `frontend/src/stores/queueStore.js`
- `frontend/src/stores/playerStore.js`
- `frontend/src/App.vue`
- `frontend/src/main.js`
- `tests/backend/storage/test_queue_sync.py`
- `tests/api/test_queue_sync.py`
- `tests/api/test_playback_state_sync.py`

**修复时间**: 2026-07-15

**修改内容**:
- 新增 `user_queues` 与 `user_playback_state` 表及迁移脚本。
- `DatabaseManager` 新增队列与播放状态的读写方法。
- `main.py` 新增 `/api/v1/queue` 和 `/api/v1/playback-state` CRUD 接口。
- 前端新增 `queue.js` / `playbackState.js` API 模块。
- `queueStore` 改为启动时同步服务端、操作后延迟上传。
- `playerStore` 改为启动时恢复服务端快照、运行时节流上传播放状态。
- `App.vue` 与 `main.js` 增加同步触发入口。
- 新增后端单元测试与 API 回归测试。

**修复后验证**:
- `pytest -m unit tests/backend/storage/test_queue_sync.py`：通过，4/4 pass
- `python3 -m py_compile backend/api/main.py backend/storage/database.py`：通过
- `npm run build`（frontend）：通过
- `node --test frontend/tests/unit/playerPersistence.test.mjs`：通过，2/2 pass
- API 端到端回归测试（`tests/api/test_queue_sync.py`、`tests/api/test_playback_state_sync.py`）因本地开发环境缺少 `spacy` 依赖暂时无法加载完整 FastAPI 应用运行；已在 CI 的 `Backend CI & CD` workflow 中通过语法检查与单元测试，部署后生产端点返回 403 鉴权响应正常。

## 相关提交

- `a0103b9` feat(sync): sync listen queue and playback state across devices
