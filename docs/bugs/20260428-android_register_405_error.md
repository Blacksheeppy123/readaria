# Android 注册按钮点击后无响应 / 误判为 405 错误

## 问题描述

用户在 Android 设备（Chrome Mobile）上通过注册页面填写信息后点击 "Sign Up"，页面没有进入注册流程。此前一次排查把它记录成了 405 错误，但这次继续定位后确认，当前主问题其实是前端提交回调没有执行。

### 用户操作步骤
1. 打开 Readaria PWA（https://readaria.com）
2. 进入注册页面
3. 填写用户名、邮箱、密码、确认密码
4. 邀请码为空（可选）
5. 点击 "Sign Up" 按钮
6. 页面无明显反应，未进入 onboarding，部分环境可能只看到泛化的请求失败提示

### 实际表现 vs 预期表现
- **预期**：注册成功，跳转到 onboarding 流程
- **实际**：点击按钮后注册请求没有正常发出，页面停留在当前表单

## 原因定位

### 排查过程

1. **后端路由检查**：`@app.post("/api/auth/register")` 正确定义，POST 路由本身没有问题
2. **前端 API 检查**：`frontend/src/api/auth.js` 中 `register()` 仍然是 `POST /api/auth/register`
3. **表单组件实现检查**：Vant `Form` 组件内部原生 `form` 的 `onSubmit` 已经调用了 `preventDefault()`，然后才 `emit("submit", values)`
4. **注册页事件绑定检查**：`frontend/src/views/RegisterView.vue` 使用了 `@submit.prevent="onSubmit"`
5. **框架行为确认**：Vue 的 `.prevent` 会对事件对象直接执行 `event.preventDefault()`；但 Vant 发出的 `submit` 是组件自定义事件，参数是表单值对象，不是原生 DOM Event
6. **结论**：点击按钮时，Vue 会尝试在表单值对象上执行 `.prevent`，导致 `onSubmit` 回调不再按预期执行，注册请求自然不会发出

### 根本原因

根因是 **对 Vant 自定义 `submit` 事件错误使用了 Vue 的 `.prevent` 修饰符**。

- `van-form` 内部已经处理了原生表单提交的 `preventDefault`
- 组件对外抛出的 `submit` 参数是 `values` 对象，不是浏览器 `SubmitEvent`
- 写成 `@submit.prevent="onSubmit"` 后，Vue 会先对这个 `values` 对象执行 `.prevent`
- 结果是提交处理链异常，`onSubmit` 不再稳定执行，表现出来就是按钮点了没有反应

此前文档里的 405 推断并不是这次问题的真实根因，更像是历史排查噪音或旧缓存环境中的伴随现象。

### 相关代码位置

- 前端注册组件：`frontend/src/views/RegisterView.vue`
- 前端订阅添加表单：`frontend/src/views/FeedsView.vue`（发现同类错误用法，一并修复）
- 前端 API：`frontend/src/api/auth.js`
- 请求拦截器：`frontend/src/api/request.js`
- 后端路由：`backend/api/main.py:518`
- Vant Form 实现：`frontend/node_modules/vant/es/form/Form.mjs`

## 修复方案

1. **移除错误的 `.prevent` 修饰符**：将 `van-form @submit.prevent="onSubmit"` 改为 `@submit="onSubmit"`
2. **保留 Vant 默认行为**：让组件内部处理原生表单 `preventDefault`，外层只接收已校验的 values 并执行业务提交
3. **补回归测试**：新增 E2E 用例，验证点击 `Sign Up` 会发出 `POST /api/auth/register` 并跳转到 `/onboarding/language`
4. **顺手修复同类隐患**：`FeedsView.vue` 使用了相同模式，也改为 `@submit="onSubmit"`

## 修复状态

- [x] 问题定位
- [x] 文档记录
- [x] 代码修复
- [ ] 测试验证

## 修复记录

**修复时间**: 2026-04-28

**修改内容**:
- `frontend/src/views/RegisterView.vue`:
  - 将 `@submit.prevent="onSubmit"` 改为 `@submit="onSubmit"`，恢复 Vant `submit` 自定义事件的正常处理链
- `frontend/src/views/FeedsView.vue`:
  - 修复相同的 `van-form @submit.prevent` 用法，避免添加订阅源表单出现同类“点击无反应”问题
- `frontend/tests/e2e/auth.spec.ts`:
  - 新增注册回归测试，断言点击 `Sign Up` 后会发出 `POST /api/auth/register`，并跳转到 onboarding 语言选择页

## 相关提交

- 待补充
