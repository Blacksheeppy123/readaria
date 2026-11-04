# OAuth 用户删除账号时强制要求输入密码

## 问题描述

使用 Google OAuth 登录的用户，在「我」页面点击「删除账号」时，系统弹出一个密码输入框要求输入密码进行确认。但 OAuth 用户从未设置过密码（后端使用随机生成的不可用的密码哈希），因此无法输入正确的密码，导致无法删除账号。

### 用户操作步骤
1. 使用 Google 登录注册/登录账号
2. 进入「我」页面
3. 展开「关于」折叠面板
4. 点击「删除账号」
5. 确认删除弹窗后出现密码输入框
6. 用户不知道密码，无法继续

### 实际表现 vs 预期表现
- **实际**：OAuth 用户必须输入密码才能删除账号，但用户从未设置过密码
- **预期**：OAuth 用户删除账号时不需要输入密码，直接确认即可删除

## 原因定位

### 根本原因
系统没有区分「密码注册用户」和「OAuth 注册用户」，删除账号流程统一要求密码验证。

### 具体流程问题
1. 前端 `MeView.vue` 中 `handleDeleteAccount` → `beforeDeleteClose` 强制检查密码非空
2. 后端 `delete_account` API 虽然已兼容空密码（不传密码则跳过验证），但前端始终会传密码
3. 数据库中没有任何字段标识用户的注册来源（OAuth vs 密码）

### 相关代码位置
- **前端删除流程**：`frontend/src/views/MeView.vue:138-176`
- **后端删除 API**：`backend/api/main.py:828-865`
- **Google OAuth 注册**：`backend/api/main.py:653-738`
- **普通注册**：`backend/api/main.py:540-580`

## 修复方案

### 思路
给 `users` 表增加 `auth_provider` 字段，标记用户的注册来源（`password` / `google`）。前端根据该字段决定是否显示密码输入框。

### 修改范围
1. **数据库**：添加 `auth_provider` 字段（migration + schema）
2. **后端**：
   - `UserResponse` 增加 `auth_provider` 字段
   - `create_user` 方法增加 `auth_provider` 参数
   - 普通注册设置 `auth_provider = 'password'`
   - Google OAuth 注册设置 `auth_provider = 'google'`
   - 现有用户 backfill（有随机密码哈希且近期无登录记录的设为 `'google'`，其余设为 `'password'`）
3. **前端**：
   - `MeView.vue` 根据 `auth_provider === 'google'` 跳过密码输入
   - `userStore.js` 保存/恢复 `auth_provider`
   - `LoginView.vue` / `RegisterView.vue` 设置 `auth_provider`

## 修复状态

- [x] 问题定位
- [x] 文档记录
- [x] 代码修复
- [x] 测试验证

## 修复记录

**修复文件**:
- `backend/storage/migrations/2026_04_28_add_auth_provider.sql`
- `backend/storage/schemas.sql`
- `backend/storage/database.py`
- `backend/api/main.py`
- `frontend/src/views/MeView.vue`
- `frontend/src/stores/userStore.js`
- `frontend/src/views/LoginView.vue`
- `frontend/src/views/RegisterView.vue`

**修复时间**: 2026-04-28

**修改内容**:
- 数据库：新增 `auth_provider` 字段到 `users` 表
- 后端：`UserResponse` 返回 `auth_provider`，注册/OAuth 流程设置对应值
- 前端：OAuth 用户删除账号跳过密码输入，直接确认删除

## 相关提交

- [待补充]
