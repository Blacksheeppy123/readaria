# 邀请码注册后未获得试用资格

> **历史记录，不适用于当前开源自托管版。** 当前代码已移除邀请码、试用资格和订阅计划。以下配置、接口、代码位置与修复方案只描述原托管 SaaS 的历史行为，不应在当前版本上复现或实施。

## 问题描述

用户 `mytest5` 使用邀请码注册后，没有获得 Pro 试用资格，而是被识别为免费用户。

- **用户操作**: 注册时填写了有效邀请码，前端显示邀请码有效
- **预期表现**: 注册后应获得 14 天 Pro 试用（`plan_id='pro'`, `status='trialing'`）
- **实际表现**: 用户被视为免费用户，无试用权限

## 原因定位

### 根本原因

后端配置 `settings.invitation_required = False` 导致邀请码处理逻辑被完全跳过。

### 具体流程问题

在 `backend/api/main.py` 的注册接口中（line 528-535）：

```python
invitation_data = None
if settings.invitation_required:  # ← 当此项为 False 时，整个块被跳过
    if not reg_req.invitation_code:
        raise HTTPException(...)
    result = subscription_service.validate_invitation_code(...)
    ...
```

当 `invitation_required=False` 时：
1. 即使用户提交了有效邀请码，`invitation_data` 仍为 `None`
2. 邀请码不会被消费（`use_invitation_code` 被跳过）
3. 不会创建订阅记录（`create_subscription` 依赖 `invitation_data`）
4. 用户无 `user_subscriptions` 记录，`get_effective_plan` 回退到 free 计划

### 相关代码位置

- `backend/api/main.py:528-577` — 注册接口邀请码处理逻辑
- `core/config/settings.py:203` — `invitation_required = False`
- `backend/services/subscription_service.py:146-176` — `create_subscription`

## 修复方案

修改注册接口逻辑：**无论 `invitation_required` 是否为 True，只要用户提供了邀请码，就应处理并授予试用资格**。

具体修改：
- 将邀请码验证从 `if settings.invitation_required:` 块中移出
- 保留 `settings.invitation_required` 仅控制"是否强制要求邀请码"
- 当用户提供了邀请码时，始终进行验证和消费

## 修复状态

- [x] 问题定位
- [x] 文档记录
- [x] 代码修复
- [x] 测试验证（37 项 unit tests 通过）
- [x] 生产部署
- [x] 线上验证

## 修复记录

**修复文件**: `backend/api/main.py`

**修复时间**: 2026-04-28

**修改内容**:
- 调整邀请码处理逻辑：用户主动提供邀请码时，不再受 `invitation_required=False` 影响
- 保持 `invitation_required=True` 时的强制校验行为不变

## 相关提交

- `ece923c` feat(onboarding): onboarding UX optimization + invitation code trial fix（初始修复：调整 invitation_required 逻辑）
- `fd78ea1` fix(invitation): resolve FK constraint on invitation_codes.used_by（FK 约束修复 + starter pack 固定列表）
