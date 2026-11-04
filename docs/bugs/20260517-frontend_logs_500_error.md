# Frontend Logs 接口持续返回 500

## 问题描述

生产环境持续收到 nginx 5xx 错误率过高的报警：
- 报警类型: `nginx_5xx_high`
- 错误率: 8.0% (2/25 请求)
- 时间: 2026-05-17 08:28:01（持续性报警）

实际现象：所有 500 错误均来自 `POST /api/v1/frontend-logs` 接口，由白名单用户设备持续触发。

## 原因定位

### 根本原因

`submit_frontend_logs` 函数中使用了未定义的变量 `username`（[backend/api/main.py:3613](backend/api/main.py#L3613)），导致每次白名单用户上传前端日志时触发 `NameError`，返回 HTTP 500。

### 具体流程问题

1. 白名单用户设备在运行中遇到前端错误
2. 前端定时将日志批量 POST 到 `/api/v1/frontend-logs`
3. 后端认证通过（403 检查已通过）
4. 在处理日志循环中执行 `context["username"] = username`
5. `username` 未定义 → `NameError` → FastAPI 返回 500
6. 前端收到 500 后不会停止重试（或按固定间隔继续上报），形成持续 500 风暴

### 相关代码位置

- 文件: [backend/api/main.py:3585-3638](backend/api/main.py#L3585-L3638)
- 问题行: 第 3613 行 `context["username"] = username`
- 对比: 同文件的 `submit_feedback` 函数（第 3649 行）正确地先定义了 `username = current_user.get("username") or current_user.get("id")`

## 修复方案

在 `submit_frontend_logs` 函数的白名单验证通过后，添加 `username` 变量定义：

```python
username = current_user.get("username") or current_user.get("id")
```

与 `submit_feedback` 函数保持一致。

## 修复状态

- [x] 问题定位
- [x] 文档记录
- [x] 代码修复
- [x] 测试验证
- [x] 部署验证

## 修复记录

**修复文件**: [backend/api/main.py](backend/api/main.py)

**修复时间**: 2026-05-17

**修改内容**:
- 在 `submit_frontend_logs` 函数中添加 `username = current_user.get("username") or current_user.get("id")`，修复未定义变量导致的 500 错误

## 相关提交

- 待补充（部署后）
