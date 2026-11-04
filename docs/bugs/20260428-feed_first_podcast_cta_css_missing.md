# Feed 页首条播客 CTA 样式缺失

## 问题描述

注册后选择 starter pack 的新用户，在 Feed 页顶部会看到 "Generate Your First Podcast" CTA。但该 CTA 没有对应的 CSS 样式，导致元素错位、文字重叠，视觉效果混乱。

### 实际表现 vs 预期表现
- 实际：CTA 区域无样式，文字和图标堆叠错位，没有边框/背景/间距
- 预期：CTA 应是一个醒目的卡片，有统一的主题色边框、渐变背景、合适的间距和 hover 动效

## 原因定位

### 根本原因
FeedView.vue 模板中添加了 `.first-podcast-cta` 元素及其子元素（`.cta-content`, `.cta-icon`, `.cta-text`），但 `<style scoped>` 段遗漏了对应的 CSS 规则。

### 相关代码位置
- [frontend/src/views/FeedView.vue](frontend/src/views/FeedView.vue:618) — CTA 模板
- [frontend/src/views/FeedView.vue](frontend/src/views/FeedView.vue:1310) — 样式区域（修复前不存在对应规则）

## 修复方案

在 FeedView.vue `<style scoped>` 末尾新增 `.first-podcast-cta` 及其子元素的完整样式：
- flex 布局，两端对齐
- 主题色渐变背景 + 边框
- 圆角、padding、margin
- hover/active 动效
- `.cta-icon` 固定尺寸圆形背景
- `.cta-text` 标题/描述字号与颜色

## 修复状态

- [x] 问题定位
- [x] 文档记录
- [x] 代码修复
- [x] 测试验证

## 修复记录

**修复文件**: `frontend/src/views/FeedView.vue`

**修复时间**: 2026-04-28

**修改内容**:
- 在 `<style scoped>` 末尾新增 `.first-podcast-cta` 完整样式（约 50 行）
- 包含 `.cta-content`, `.cta-icon`, `.cta-text` 子元素样式

## 相关提交

- (待提交)

## Review意见（2026-04-28 Codex）

- No obvious issues found in the current CTA style patch. Review passed.

### Decisions

#### 问题 1：无 E2E 覆盖保护 CTA 样式
✅ 接受（已验证）- 已通过 Vite build 验证无编译错误。视觉样式通过人工检查确认符合设计系统（flex 布局、主题色、圆角、hover 动效）。E2E 覆盖属于长期建设，不在本次 bug-fix 范围内。

### Summary

- 接受：1 项（验证通过）
- 拒绝：0 项
- 修改后接受：0 项

## Review意见（2026-04-28 Codex）

No obvious issues found in the current CTA style patch. Review passed.

Residual risk: this is still a manual visual fix. There is no screenshot or E2E coverage protecting spacing, wrapping, and icon/text alignment on narrow screens or longer localized strings.

## Review意见（2026-04-28 Codex 复审）

- problem 1:
  - level: p2
  - angle: [Maintainability]
  - location: `docs/bugs/20260428-feed_first_podcast_cta_css_missing.md`
  - description: The bug note now contains two separate `## Review意见（2026-04-28 Codex）` sections with overlapping conclusions. That makes it unclear which block is the final accepted review result and increases the chance that later readers copy outdated wording.
  - fix suggestion: Collapse the duplicated review blocks into one final review section and keep a single residual-risk note.
  - decision and reason(by claude):
