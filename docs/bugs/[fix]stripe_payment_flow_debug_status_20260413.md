# Stripe 支付流 Debug 状态报告

> **历史记录，不适用于当前开源自托管版。** 当前代码已移除 Stripe、订阅、Customer Portal 和 Pro/Free 配额。本文中的文件路径、接口、账号、数据库表及“下一步操作”仅记录原托管 SaaS 的历史排查过程，不应作为现行测试或运维指南。

**日期**: 2026-04-13  
**负责人**: Claude Code  
**状态**: 已修复核心问题，待 CI/CD 构建完成后最终验证

---

## 1. 任务背景与目标

修复 Jasmine App 的 Stripe 订阅支付流程，确保端到端功能完全正常。需验证的环节包括：

- [x] Checkout 页面创建与跳转
- [x] 用户完成支付（测试卡 4242）
- [x] Webhook `checkout.session.completed` 正确处理
- [x] 数据库 `user_subscriptions` 更新（plan_id, status, stripe_customer_id, stripe_subscription_id）
- [ ] 数据库中 `current_period_start` / `current_period_end` 正确写入
- [ ] Customer Portal 正常访问

---

## 2. 已发现的问题与修复记录

### 2.1 Webhook Handler 报错：`error=get`（P0 - 已修复并部署）

**现象**: 生产环境 Webhook 处理失败，日志显示 `error=get`，无任何上下文。

**根因**: 生产服务器安装的 `stripe` Python SDK 版本为 **v15.0.1**。在此版本中，`StripeObject` 不再继承自 `dict`，也不再支持 `.get()` 方法。代码中多处使用 `session.get("id")`、 `subscription.get("status")` 等调用，触发 `AttributeError: get`，异常信息被截断后只显示 `"get"`。

**修复内容**:
- 文件: `backend/services/stripe_service.py`
- 新增 `_so_get(obj, key, default=None)` 辅助函数，兼容 `StripeObject`（使用 `getattr`）和原生 `dict`（使用 `.get`）。
- 将所有 Webhook Handler 中对 Stripe 对象的 `.get()` 调用全部替换为 `_so_get()`：
  - `_on_checkout_completed`
  - `_resolve_plan_id_from_subscription`
  - `_on_subscription_updated`
  - `_on_subscription_deleted`
  - `_on_payment_failed`

**验证结果**: 部署后重新用测试用户 `stripetest2026x` 走完全流程，Webhook `checkout.session.completed` 被成功处理，日志显示 `Webhook processed: checkout.session.completed`。

### 2.2 `current_period_start` / `current_period_end` 为 `NULL`（P1 - 已定位并修复代码，待部署验证）

**现象**: Webhook 已处理成功，但数据库中 `current_period_start` 和 `current_period_end` 字段为 `NULL`。

**日志证据**:
```
[INFO] 2026-04-13 09:33:29 [Webhook] Periods: start=None, end=None
[INFO] 2026-04-13 09:33:29 Checkout completed: user=stripetest2026x, plan=pro
```

**排查过程**:
1. 在生产容器内直接执行 `stripe.Subscription.retrieve(sub_id)`，确认对象能成功返回。
2. 测试 `getattr(sub, "current_period_start", "MISSING")`，结果返回 `"MISSING"`。
3. 测试 `sub["current_period_start"]`，抛出 `KeyError`。
4. 通过 `sub.to_dict()` 列出所有 keys，共 48 个，确认 `current_period_start` 和 `current_period_end` **确实不在返回字段列表中**。
5. 使用 `curl` 直接访问 Stripe API 原始端点，**不带** `Stripe-Version` header，返回的 JSON 同样不包含这两个字段。
6. 使用 `curl` 带上 `Stripe-Version: 2024-12-18.acacia` header 后，**成功返回** `current_period_start` 和 `current_period_end`。

**根因**: 后端代码初始化 `stripe` 模块时**只设置了 `stripe.api_key`**，**未设置 `stripe.api_version`**。当不指定 API Version 时，Stripe 会使用账户的默认版本。当前账户默认版本（或 stripe 库默认版本）在订阅对象返回中**不包含** `current_period_start` / `current_period_end`。

**修复内容**:
1. `core/config/settings.py`: 新增配置项 `stripe_api_version: str = "2024-12-18.acacia"`，带有安全默认值。
2. `backend/services/stripe_service.py`: `__init__` 中同步设置 `stripe.api_version = settings.stripe_api_version`。
3. `.env.example`: 补充 Stripe 相关环境变量示例，包括 `STRIPE_API_VERSION`。

**当前状态**: 代码已 commit (`a4bd5c3`) 并 push。但重新部署服务时提示 Docker image "is up to date"，说明 `Backend CI & CD` GitHub Actions 可能尚未完成新镜像构建。生产容器当前仍在运行旧镜像（验证：`docker exec docker-api-1 grep 'stripe.api_version' /app/backend/services/stripe_service.py` 返回空）。

### 2.3 周期字段路径兼容性不足（P1 - 已补强代码与测试，待部署验证）

**新增发现**: 在继续复核 Stripe 文档与本地代码时，发现 `current_period_start` / `current_period_end` 不应只假设存在于 subscription 根对象上。较新的 Stripe 文档/变更线索表明，这两个字段在某些 API 版本或对象形态下可能仅出现在 `subscription.items.data[0]` 上。

**风险**:
- 即使 `stripe.api_version` 已显式设置，未来升级 Stripe API Version 或 Webhook Endpoint Version 后，`customer.subscription.updated` 仍可能再次把 period 写成 `NULL`
- Customer Portal 触发的升降级/取消，本质依赖 `customer.subscription.updated` / `deleted` 事件同步，如果字段路径变更而代码只读根对象，线上状态可能再次漂移

**修复内容**:
1. `backend/services/stripe_service.py`
   - 新增 `_subscription_period_bounds()` 统一解析周期字段
   - 优先读取根对象 `current_period_start` / `current_period_end`
   - 若缺失，则回退读取 `items.data[0].current_period_start` / `current_period_end`
   - `_on_checkout_completed` 与 `_on_subscription_updated` 统一走该 helper
2. `tests/api/test_stripe_service.py`
   - 新增 4 个聚焦测试
   - 覆盖根字段解析、item 字段回退、`checkout.session.completed`、`customer.subscription.updated`

**本地验证结果**:
```bash
source venv/bin/activate && pytest -q tests/api/test_stripe_service.py
```

结果：`4 passed`

### 2.4 `customer.subscription.updated` 二次覆盖 period 为 `NULL`（P1 - 已定位并修复代码，待二次部署验证）

**现象**: 二次上线后重新走生产真实支付，`checkout.session.completed` 日志已经打印出正确的 period 时间，但数据库 `user_subscriptions.current_period_start/current_period_end` 仍然是 `NULL`。

**线上证据**:
```text
[INFO] 2026-04-13 20:10:38 [Webhook] Periods: start=2026-04-13T12:10:33+00:00, end=2026-05-13T12:10:33+00:00
[INFO] 2026-04-13 20:10:39 Webhook processed: customer.subscription.updated
```

数据库查询结果：
```sql
SELECT user_id, plan_id, status, current_period_start, current_period_end
FROM user_subscriptions
WHERE user_id='stripeverify20260413_200449';
```

返回：
```text
plan_id=pro, status=active, current_period_start=NULL, current_period_end=NULL
```

**推断根因**:
- `checkout.session.completed` 分支通过 `stripe.Subscription.retrieve()` 拿到了完整 subscription，对应 period 正常
- 随后 Stripe 又发送了 `customer.subscription.updated`
- 该 event payload 很可能没有携带 period 字段，或携带结构与 `retrieve()` 返回不同
- 现有 `_on_subscription_updated()` 会把解析出的 `None` 原样写回数据库，导致前一步刚写入的 period 被覆盖为空

**修复内容**:
1. `backend/services/stripe_service.py`
   - `_on_subscription_updated()` 中若 event payload 解析不到 period，则按 `subscription.id` 再调用一次 `stripe.Subscription.retrieve()`
   - 若补拉后仍拿不到值，则不再把 `None` 写回数据库，避免覆盖已有 period
2. `tests/api/test_stripe_service.py`
   - 新增测试覆盖“event payload 无 period，需补拉完整 subscription”的场景

**本地验证结果**:
```bash
source venv/bin/activate && pytest -q tests/api/test_stripe_service.py
```

结果：`5 passed`

---

## 3. 当前进度总览

| 步骤 | 状态 | 备注 |
|------|------|------|
| 修复 `.get()` 兼容性问题 | 完成 | 已合并、已部署 |
| 定位 period 字段缺失根因 | 完成 | API Version 未设置 |
| 修复 `stripe.api_version` 配置 | 完成 | 已 push，commit `a4bd5c3` |
| 补强 period 字段新旧路径兼容 | 完成 | 本地测试 `tests/api/test_stripe_service.py` 4 passed |
| 修复 `subscription.updated` 覆盖 period 为 NULL | 完成 | 本地测试 `tests/api/test_stripe_service.py` 5 passed，待二次部署 |
| 等待 CI/CD 构建新 Docker 镜像 | 进行中 | 本地 `gh` CLI 因网络/TLS 问题无法使用，无法精确查看 Actions 状态 |
| 重新部署并验证 period 字段写入 | 待开始 | 需等镜像构建完成后部署服务 |
| 验证 Customer Portal | 待开始 | 需等上述完成后测试 |

---

## 4. 涉及修改的文件

1. `backend/services/stripe_service.py`
   - 添加 `_so_get()` 辅助函数
   - 替换所有 Webhook handler 中的 `.get()` 调用
   - 初始化时设置 `stripe.api_version`
   - 新增 `_subscription_period_bounds()` 兼容新旧 period 字段路径
   - `customer.subscription.updated` 在 payload 缺失 period 时补拉完整 subscription，并避免用 `None` 覆盖数据库

2. `core/config/settings.py`
   - 新增 `stripe_api_version: str = "2024-12-18.acacia"`

3. `.env.example`
   - 新增 Stripe 配置示例（`STRIPE_SECRET_KEY`, `STRIPE_PUBLISHABLE_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_API_VERSION`）

4. `tests/api/test_stripe_service.py`
   - Stripe period 字段兼容性回归测试

5. `docs/bugs/[fix]stripe_payment_flow_debug_status_20260413.md`（本文档）

---

## 5. 已知阻塞与待确认事项

1. **CI/CD 镜像构建状态不可见**: 本地 `gh run list` 因 TLS 证书验证失败（Clash/Tailscale DNS 冲突）无法连接 `api.github.com`。浏览器访问 GitHub Actions 也因网络问题返回 404。只能依赖经验估算构建时间（通常 3-5 分钟）。
2. **镜像更新确认**: 需再次部署服务，并确认容器内 `/app/backend/services/stripe_service.py` 包含 `stripe.api_version` 行。
3. **测试环境**: 上一次 E2E 测试使用的是测试账号 `stripetest2026x`（已注册并已完成一次支付）。该账号当前在数据库中的订阅状态为 `active`，如需重新测试完整 Checkout 流程，建议：
   - 在 Stripe Dashboard 中先取消该测试订阅；或
   - 注册一个全新的测试用户。

---

## 6. 建议的下一步操作

1. 等待几分钟后重新部署服务，确认拉取到新镜像。
2. 注册新的测试用户（或清理 `stripetest2026x` 的订阅）。
3. 调用 `/api/v1/billing/checkout` 创建新 Session，用 Playwright 完成支付。
4. 检查 webhook 日志，确认 `Periods: start=..., end=...` 不再为 `None`。
5. 检查数据库 `user_subscriptions`，确认 `current_period_start` 和 `current_period_end` 有值。
6. 调用 `/api/v1/billing/portal` 测试 Customer Portal 跳转是否正常。
7. 额外验证一次 Customer Portal 引发的 `customer.subscription.updated` 事件，确认升降级/取消后的 period 字段仍能正确同步。
