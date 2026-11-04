# Onboarding manual curation: no proceed button after selecting feeds

## 问题描述

在 onboarding 流程中，用户选择 "Curate My Own"（自己挑选订阅源）后，被重定向到 Discover Feeds 页面。用户可以在该页面浏览分类并订阅感兴趣的 feeds。但订阅完成后，页面上**没有明显的入口/按钮**让用户继续进入主页面（Feed 视图）。

用户操作步骤：
1. 新用户注册/登录后进入 onboarding
2. 在 OnboardingPathView 选择 "Curate My Own"
3. 进入 Discover Feeds 页面，展开分类并点击 Subscribe 添加 feeds
4. 添加完成后，找不到进入主页面的入口

实际表现 vs 预期表现：
- **实际**: Discover Feeds 页面只有返回箭头、搜索框、feed 列表和 "Add custom feed URL" 链接，没有 "Done" / "Continue" 按钮
- **预期**: 用户选择完 feeds 后，应该有明确的按钮引导进入主页面

## 原因定位

### 根本原因
`FeedDiscoverView.vue`（ Discover Feeds 页面）设计时主要面向**已在使用 app 的用户**从 FeedManageView 进入来添加新 feed，没有考虑 onboarding 流程中该页面作为"手动挑选"路径终点的场景。

### 具体流程问题
1. `OnboardingPathView.vue:31` - 用户点击 "Curate My Own" 时调用 `goToDiscover()`，即 `router.replace({ name: 'feed-discover' })`
2. `OnboardingPathView.vue:76-78` - 同时调用 `selectPath('manual')`，将 onboarding state 设为 `'manual_selected'`
3. `FeedDiscoverView.vue` - 该页面有 `goBack()`（返回上一页）和单个 feed 的 Subscribe 按钮，但**没有完成 onboarding 并进入主页面的入口**
4. 由于使用了 `router.replace`，点击返回箭头可能回到 onboarding 的前一步（language selection），而不是主页面

### 相关代码位置
- `frontend/src/views/OnboardingPathView.vue:31, 76-78, 151-153` - 选择 manual 路径并导航
- `frontend/src/views/FeedDiscoverView.vue` - Discover Feeds 页面，缺少 onboarding 完成入口
- `frontend/src/stores/onboardingStore.js:127` - `manual_selected` 状态定义

## 修复方案

在 `FeedDiscoverView.vue` 底部添加一个浮动 "Done" 按钮，仅在 onboarding 的 manual 路径下显示：

1. 引入 `useOnboardingStore`
2. 添加 computed: `isOnboardingManual = onboardingStore.state === 'manual_selected'`
3. 页面底部添加一个固定在底部的按钮区域（`position: fixed; bottom`），包含 "Done" 按钮
4. 点击后导航到主页面：`router.replace({ name: 'feed' })`
5. 添加 i18n 文案：`feeds.discoverDone` = "Done" / "完成"

## 修复状态

- [x] 问题定位
- [x] 文档记录
- [x] 代码修复
- [x] 测试验证（前端 build 通过）

## 修复记录

**修复文件**: `frontend/src/views/FeedDiscoverView.vue`, `frontend/src/i18n/en.json`, `frontend/src/i18n/zh.json`

**修复时间**: 2026-05-18

**修改内容**:
- 在 Discover Feeds 页面底部增加 onboarding 完成入口按钮
- 添加中英文 i18n 文案

## 相关提交

- (待补充)
