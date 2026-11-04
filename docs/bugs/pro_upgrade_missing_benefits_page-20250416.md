# Pro 升级缺少权益介绍页

> **历史记录，不适用于当前开源自托管版。** 当前代码已移除 Stripe、Pro 订阅及 Free/Pro 额度。以下界面、权益表、代码位置和修复步骤仅用于理解历史问题，不是当前功能或开发指导。

## 问题描述

在个人中心（Me）Tab 中，用户点击 "Upgrade to Pro" 按钮后，系统直接调起 Stripe 付款页面，中间没有展示 Pro 会员权益的介绍页。

### 用户操作步骤
1. 打开 Jasmine App
2. 点击底部导航栏 "Me"
3. 在订阅卡片中点击 "Upgrade to Pro" 按钮

### 实际表现
- 点击后直接跳转 Stripe Checkout 付款页
- 用户没有机会了解 Pro 会员包含哪些权益

### 预期表现
- 点击后先展示 Pro 会员权益介绍页/弹窗
- 用户明确了解权益后，再自主选择是否进入付款流程

## 原因定位

### 根本原因（第一部分 - 已修复）
`MeView.vue` 中的 `handleUpgrade` 方法直接调用 `createCheckout` API 并跳转 Stripe，缺少中间的用户教育和权益展示环节。

### 根本原因（第二部分 - 生产环境弹窗未显示）
在 `MeView.vue` 中添加 `van-popup` 后，开发环境正常显示，但生产环境点击 "Upgrade to Pro" 后弹窗未正确渲染。
经排查，`frontend/src/main.js` 中全局注册 Vant 组件时遗漏了 `Popup` 和 `Switch`。Vue 3 在生产构建中对未注册组件会回退为原生自定义元素，导致 `<van-popup>` 被渲染为 `<VAN-POPUP>`（`display: inline`），无法展开 Vant 的遮罩层和底部弹窗结构。

### 相关代码位置
- **文件**: [`frontend/src/views/MeView.vue:83-95`](frontend/src/views/MeView.vue#L83-L95)
- **函数**: `handleUpgrade`
- **新增文件**: [`frontend/src/main.js`](frontend/src/main.js#L44-L45)

```javascript
const handleUpgrade = async () => {
  try {
    const result = await createCheckout({ plan_id: 'pro', billing_cycle: 'monthly' })
    if (result.url) {
      window.location.href = result.url
    }
  } catch (error) {
    ...
  }
}
```

### 当前 Pro 权益（根据 `subscription_plans` 表）

| 权益 | Free | Pro |
|------|------|-----|
| TTS 每日额度 | 1 篇 | 10 篇 |
| AI 摘要每日额度 | 20 次 | 无限 |
| 播客生成每日额度 | 0 个 | 1 个 |
| 优先刷新 | 无 | 有 |
| OPML 导入/导出 | 有 | 有 |

## 修复方案

1. 在 `MeView.vue` 中添加一个 Pro 权益介绍的弹窗（van-popup 或 van-dialog）
2. 修改 `handleUpgrade`：先打开权益弹窗，而非直接跳转付款
3. 在弹窗内提供 "Upgrade Now" 按钮，点击后再执行原有的 `createCheckout` 逻辑
4. 添加对应的 i18n 文案（中英文）

### UI 设计思路
- 使用全屏弹窗或底部弹窗展示 Pro 权益
- 顶部显示 "Pro Plan" 标题和价格（$7.99/month）
- 中间用图标 + 文字列出核心权益
- 底部放置 "Upgrade Now" 主按钮和 "Maybe Later" 次要按钮

## 修复状态

- [x] 问题定位
- [x] 文档记录
- [x] 代码修复
- [x] 测试验证

## 修复记录

**修复文件**: 
- `frontend/src/views/MeView.vue`
- `frontend/src/i18n/en.json`
- `frontend/src/i18n/zh.json`

**修复时间**: 2026-04-16

**修改内容**:
- `MeView.vue`: 在 `handleUpgrade` 中改为打开 Pro 权益弹窗，新增 `confirmUpgrade` 方法执行原有 Stripe 跳转逻辑；新增底部 `van-popup` 弹窗展示 Pro 权益列表和升级/稍后按钮
- `en.json` / `zh.json`: 在 `subscription` 命名空间下新增 `perMonth`、`proTtsTitle`、`proTtsDesc`、`proSummaryTitle`、`proSummaryDesc`、`proPodcastTitle`、`proPodcastDesc`、`proRefreshTitle`、`proRefreshDesc` 等文案
- `frontend/src/main.js`: 全局注册遗漏的 `Popup` 和 `Switch` 组件，修复生产环境下 `van-popup` 无法渲染为 Vant 遮罩弹窗的问题
- 前端构建验证通过
- 在线验证通过：生产环境点击 "Upgrade to Pro" 后正常显示 Pro 权益弹窗，"Maybe Later" 可正确关闭弹窗

## 相关提交

- `2222ba5` feat(me): add Pro benefits popup before Stripe checkout
- `6e30b7d` fix(frontend): register missing Vant Popup and Switch components in main.js
