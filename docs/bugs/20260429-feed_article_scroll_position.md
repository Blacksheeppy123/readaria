# Android Feed 文章打开滚动位置错误

## 问题描述

在 Android 设备上，从 Feed 页面点击打开文章详情页时，页面没有定位到文章标题和开头部分，而是滚动到了文章中间位置。

- **功能模块**: Feed → Article Detail
- **设备**: Android
- **实际表现**: 文章详情页打开后，滚动位置在文章中间
- **预期表现**: 文章详情页打开后，应该显示在文章标题和开头部分（顶部）

## 原因定位

### 根本原因

Vue Router 未配置 `scrollBehavior`，导致 Android 浏览器在路由跳转时自行处理滚动位置。由于 ArticleDetail 页面存在动态内容加载（骨架屏 → 正文过渡、懒加载图片），浏览器在内容高度变化过程中恢复或计算滚动位置，导致页面打开后定位到了文章中间而非顶部。

### 相关代码位置

- Router 配置: `frontend/src/router/index.js`（缺少 `scrollBehavior`）
- Feed 文章跳转: `frontend/src/views/FeedView.vue:388-422`
- 文章详情页: `frontend/src/views/ArticleDetail.vue`

## 修复方案

在 Vue Router 配置中显式添加 `scrollBehavior`：
- 当使用浏览器返回/前进时（`savedPosition` 存在），恢复之前的滚动位置
- 其他导航（如从 Feed 打开文章）时，强制滚动到页面顶部 `{ top: 0 }`

这样可以避免 Android 浏览器在动态内容加载期间的滚动位置误判。

## 修复状态

- [x] 问题定位
- [x] 文档记录
- [x] 代码修复
- [ ] 测试验证

## 修复记录

**修复文件**: `frontend/src/router/index.js`

**修复时间**: 2026-04-29

**修改内容**:
- 在 `createRouter` 配置中添加 `scrollBehavior` 方法
- 有 `savedPosition` 时恢复滚动位置（支持返回/前进手势）
- 无 `savedPosition` 时强制滚动到顶部 `{ top: 0 }`

## 2026-04-30 补充

在 Android 新人流程回归中发现，仅靠 router 级 `scrollBehavior` 仍不足以覆盖 `ArticleDetail.vue` 的动态内容加载场景。页面会先渲染缓存头部 / skeleton，再异步补正文，浏览器可能在 `.content` 容器高度变化时恢复到中部位置。

因此新增 view 级兜底修复：

- 在 `frontend/src/views/ArticleDetail.vue` 中增加 `scrollToTop()`
- 在页面挂载、开始加载、命中缓存全文和异步补全正文后，主动重置 `.content` 与 window 的滚动位置

这次补丁是对原修复的增强，而不是推翻 router 侧修复。

## 相关提交

- 待记录
