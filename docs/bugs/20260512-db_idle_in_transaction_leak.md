# PostgreSQL idle in transaction 连接泄漏

## 问题描述

2026-05-12 21:00 线上 PostgreSQL 内存报警（>80%），`pg_stat_activity` 发现 6 个 `idle in transaction` 连接，最长已滞留 4 小时 9 分钟。连接长时间不释放导致内存占用持续上升，有池耗尽风险。

## 原因定位

### 根本原因

FastAPI 的 `DBConnectionMiddleware` 在 `async def dispatch()` 中通过 `db_manager.release_conn()` 释放连接，但连接存储在 `threading.local()` 中。当路由处理函数是同步 `def`（非 `async def`）时，FastAPI 会将其派发到工作线程池执行，而中间件的清理逻辑仍在 ASGI/事件循环线程运行。这两个线程不是同一个 Python 线程，因此 `threading.local()` 中的连接永远无法被中间件释放，导致连接泄漏并表现为 `idle in transaction`。

### 具体流程问题

1. 同步路由（如 `GET /user/{user_id}/feeds`、`GET /api/auth/data-export`、`GET /api/user/{user_id}/feeds/refresh/status`）在工作线程执行 DB 查询
2. `self.pg_conn` 属性懒加载，通过 `ThreadedConnectionPool.getconn()` 获取连接并存入当前工作线程的 `threading.local()`
3. 查询结束后没有显式归还连接（`autocommit=False`，即使只读查询也会开启事务）
4. 响应返回后，`DBConnectionMiddleware` 在事件循环线程调用 `release_conn()`，但事件循环线程的 `threading.local()` 中没有该连接
5. 连接一直被工作线程占用，直到工作线程被复用或进程退出

### 相关代码位置

- `backend/storage/database.py:90-118` — `threading.local()` 连接存储
- `backend/storage/database.py:114-124` — `pg_conn` 懒加载属性
- `backend/api/main.py:331-339` — `DBConnectionMiddleware` 异步清理
- `backend/api/main.py:981-1003` — 同步路由 `export_user_data`
- `backend/api/main.py:1142-1147` — 同步路由 `get_user_feeds`
- `backend/api/main.py:1568-1573` — 同步路由 `get_refresh_status`

### 关于 putconn() rollback 的说明

`psycopg2.pool.ThreadedConnectionPool.putconn()` 在归还非空闲连接时会自动执行 rollback，因此 `release_conn()` 中的显式 rollback 仅是防御性措施，不是主要修复机制。

## 修复方案

1. 引入可重入的 `connection_scope()` 上下文管理器（`backend/storage/database.py:152-179`），通过每线程嵌套深度计数确保最外层 `with` 退出时才归还连接
2. 添加 `@_with_db_scope` 装饰器（`backend/storage/database.py:36-55`），自动将方法体包裹在 `connection_scope()` 中
3. 对所有被同步路由调用的公共 DB 方法应用 `@_with_db_scope` 装饰器，确保 checkout 与 release 发生在同一线程
4. 保留 `release_conn()` 中的防御性 rollback，但不将其描述为主要修复机制

## 修复状态

- [x] 问题定位
- [x] 文档记录
- [x] 代码修复
- [x] Codex review 第 2 轮
- [x] 部署上线
- [x] 线上验证（部署后 10 分钟复查 idle in transaction = 0）

## 修复记录

**修复文件**: `backend/storage/database.py`

**修复时间**: 2026-05-12

**修改内容**:
- 新增 `functools` 导入
- 新增 `@_with_db_scope` 装饰器（同线程包裹 `connection_scope()`）
- 新增可重入 `connection_scope()` 上下文管理器（每线程 `scope_depth` 计数）
- 对 11 个公共 DB 方法应用 `@_with_db_scope`：`get_user_by_id`、`get_user_feeds`、`create_user_feed`、`create_user_feed_minimal`、`update_user_feed`、`delete_user_feed`、`list_saved_articles`、`get_user_articles`、`get_latest_feed_update_status_for_user`、`get_user_articles_stats`、`get_user_feed_overview_stats`

## 相关提交

- [cd7cd9c] fix(db): fix idle-in-transaction leak via @_with_db_scope decorator
