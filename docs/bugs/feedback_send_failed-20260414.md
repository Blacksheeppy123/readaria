# Feedback 功能发送失败

## 问题描述

用户在 Profile 页面点击 Feedback，填写反馈内容（如"本地语音播放失败"）并勾选"Attach recent logs"后，点击确认按钮，弹出"Failed to send feedback"的错误提示，反馈发送失败。

- **功能模块**: Profile -> Feedback
- **用户操作**: 填写反馈 -> 勾选附加日志 -> 点击确认
- **实际表现**: 提示 "Failed to send feedback"
- **预期表现**: 反馈成功发送，提示 "Feedback sent, thank you!"

## 原因定位

### 根本原因
前端调用 API 端点 `/api/v1/feedback`，但**后端并未实现该端点**。请求返回 404 Not Found，导致前端 catch 错误并提示发送失败。

### 相关代码位置
- **前端**: [frontend/src/views/MeView.vue:221-241](frontend/src/views/MeView.vue#L221-L241)
  - `submitFeedback()` 函数向 `/api/v1/feedback` 发送 POST 请求
- **后端**: [backend/api/main.py](backend/api/main.py)
  - 搜索整个后端代码，不存在 `/api/v1/feedback` 路由定义

## 修复方案

1. **后端 API** (`backend/api/main.py`):
   - 添加 `FeedbackRequest` Pydantic 请求模型（包含 `message: str` 和 `attach_logs: bool`）
   - 添加 `@app.post("/api/v1/feedback")` 端点，需要用户认证（`Depends(get_current_user)`）
   - 端点将反馈同时写入 `user_feedback` 数据表和 `api.log`
   - 返回成功响应

2. **数据库** (`backend/storage/schemas.sql`):
   - 新增 `user_feedback` 表，用于持久化存储用户反馈并追踪处理状态

3. **数据层** (`backend/storage/database.py`):
   - 新增 `save_user_feedback()` 和 `get_user_feedback()` 方法

## 修复状态

- [x] 问题定位
- [x] 文档记录
- [x] 代码修复
- [x] 测试验证（语法检查通过）
- [x] 数据库表创建

## 修复记录

**修复文件**: 
- `backend/api/main.py`
- `backend/storage/schemas.sql`
- `backend/storage/database.py`
- `docs/database_schema.md`
- `docs/deployment_summary.md`
- `CLAUDE.md`

**修复时间**: 2026-04-14

**修改内容**:
- 新增 `FeedbackRequest` 模型和 `/api/v1/feedback` POST 端点
- 后端端点将反馈持久化到 `user_feedback` 数据表，同时记录到 `api.log`
- 新增 `user_feedback` 表定义（含状态追踪字段 `status`）
- `DatabaseManager` 新增 `save_user_feedback()` / `get_user_feedback()` 方法
- 更新相关文档，补充反馈日志排查说明

## 相关提交

- 待提交
