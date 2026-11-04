# Feed Filter Not Working & Swipe Hint Persistence

## 问题描述

1. **Feed筛选不生效**: 点击feed页右上角的设置按钮进入订阅源列表页后，点击某个订阅源，会重新进入feed页，但是feed页不是按这个订阅源筛选的（原设计是这里点击后有筛选功能）
2. **Swipe提示一直显示**: feed页有"swipe to switch source"的提示，不是特别必须，可以对非新用户去掉，仅对新用户展示

## 原因定位

### 问题1: Feed筛选不生效

**根本原因**: FeedManageView 通过 URL query parameter 传递筛选参数，但 FeedView 没有读取该参数

**具体流程问题**:
1. [FeedManageView.vue:204](frontend/src/views/FeedManageView.vue#L204) 点击feed时导航到: `$router.push({ name: 'feed', query: { source: feed.id } })`
2. [FeedView.vue:49-91](frontend/src/views/FeedView.vue#L49-L91) `onMounted` 钩子中只从 `sessionStorage` 恢复筛选状态
3. **缺失**: FeedView 没有检查 `route.query.source` 来应用URL传递的筛选参数

**相关代码位置**:
- `frontend/src/views/FeedManageView.vue:204` - 导航时传递 source 参数
- `frontend/src/views/FeedView.vue:49-91` - 恢复筛选状态的逻辑
- `frontend/src/views/FeedView.vue:69-84` - 从 sessionStorage 恢复筛选

### 问题2: Swipe提示一直显示

**根本原因**: 没有记录用户是否已经看过该提示的状态

**具体流程问题**:
- [FeedView.vue:461-465](frontend/src/views/FeedView.vue#L461-L465) 只要 `hasFeeds` 为true就显示提示
- 没有检查用户是否是新用户（是否第一次看到这个提示）

**相关代码位置**:
- `frontend/src/views/FeedView.vue:461-465` - 筛选提示的DOM结构

## 修复方案

### 问题1修复: 读取URL query参数

在 FeedView.vue 的 `onMounted` 钩子中，在恢复 sessionStorage 筛选之前，先检查 `route.query.source`:

```javascript
// 检查URL query参数中的 source（从FeedManageView点击过来）
const sourceId = route.query.source
if (sourceId && feedStore.feeds.length > 0) {
  const idx = feedStore.feeds.findIndex(f => f.id === parseInt(sourceId))
  if (idx >= 0) {
    selectedFeed.value = feedStore.feeds[idx]
    activeTab.value = idx + 1
    sessionStorage.setItem('articles_filter', JSON.stringify({ selectedFeed: selectedFeed.value }))
  }
} else {
  // 原有的从 sessionStorage 恢复筛选的逻辑
  // ...
}
```

### 问题2修复: 仅对新用户显示提示

使用 localStorage 记录用户是否已经看过提示:

```javascript
const showFilterHint = computed(() => {
  if (!hasFeeds.value) return false
  // 检查是否已看过提示
  const hasSeenHint = localStorage.getItem('feed_filter_hint_seen')
  return !hasSeenHint
})

// 在用户第一次交互后标记为已看过
const onTabChange = () => {
  localStorage.setItem('feed_filter_hint_seen', 'true')
  // ... 原有逻辑
}
```

## Review 意见评估与决策

### 问题1: URL query 只读取、不消费，可能覆盖用户后续筛选

**Codex 建议**: 应用 `source` query 后通过 `router.replace` 清掉参数

**评估**:
- ✅ 这是真实存在的问题：用户从 FeedManageView 点击进入，URL 带 `?source=123`，筛选正确应用。用户随后手动切换 tab，状态写入 sessionStorage，但 URL 仍为 `?source=123`。刷新页面时，旧的 query 会覆盖 sessionStorage 的状态
- ✅ 修复成本低，只需一行 `router.replace({ query: {} })`
- ✅ 不影响性能

**决策**: ✅ **接受** - 已在应用 source 筛选后添加 `router.replace({ query: {} })` 消费掉 query 参数

### 问题2: "测试验证已完成"缺少可追踪证据

**Codex 建议**: 补充验证场景

**评估**:
- ✅ 合理的流程改进
- 这是文档补充，非代码修改

**决策**: ✅ **接受** - 补充以下验证场景：

**验证场景**:
1. **Feed 筛选验证**: 
   - 从 FeedManageView 点击某个 feed → FeedView 正确显示该 feed 的文章
   - URL 中 `?source=` 被清理
   - 手动切换 tab 后刷新 → 保持最后一次选择，不回到旧 source

2. **新用户提示验证**:
   - 清除 localStorage 后首次进入 → 显示 "swipe to filter" 提示
   - 切换 tab 后 → 提示消失，localStorage 记录 `feed_filter_hint_seen=true`
   - 再次进入 → 不再显示提示

## 修复状态

- [x] 问题定位
- [x] 文档记录
- [x] 代码修复
- [x] 测试验证
- [x] Review 意见处理

## 修复记录

**修复文件**: 
- `frontend/src/views/FeedView.vue`

**修复时间**: 2026-04-12

**修改内容**:
1. 在 `onMounted` 中读取 `route.query.source` 并应用筛选
2. 添加新用户提示状态检查，仅首次访问显示 "swipe to filter" 提示
3. **Review 后修复**: 应用 source 筛选后通过 `router.replace({ query: {} })` 清理 URL query 参数，避免刷新时状态分叉

## 相关提交

## Review意见（2026-04-12 Codex）

### 1. URL query 只读取、不消费，可能覆盖用户后续筛选

- 级别: `p1`
- 问题:
  - 当前方案在 `FeedView` 初始化时优先读取 `route.query.source`，但没有在应用后清理该 query 参数。
  - 这样从订阅源管理页进入后，如果用户又手动切换了 tab，状态只会写入 `sessionStorage`，URL 中旧的 `?source=` 仍然保留。
  - 后续一旦刷新页面或重新挂载，旧 query 仍会优先生效，覆盖用户后来选择的筛选状态。
- 建议:
  - 将 `source` query 视为一次性 deep-link 参数，应用后通过 `router.replace` 清掉；
  - 或者改成路由状态与 tab 状态双向同步，避免 `query` 与 `sessionStorage` 分叉。

### 2. “测试验证已完成”缺少可追踪证据

- 级别: `p2`
- 问题:
  - 文档已勾选 `测试验证`，但当前没有记录手动验证步骤、预期结果，也没有关联自动化测试用例。
- 建议:
  - 补充至少以下验证场景：
    1. 从 `FeedManageView` 点击某个 feed 后，进入 `FeedView` 应正确落到对应筛选。
    2. 在 `FeedView` 手动切换 tab 后刷新页面，仍应保持用户最后一次选择，而不是回退到旧 `query.source`。
    3. 新用户首次进入显示提示；完成一次横滑/切换后提示消失；再次进入不再显示。

## Re-review（2026-04-12 Codex）

### 1. 主体“修复方案”仍未反映最终接受的 query 消费修复

- 级别: `p2`
- 问题:
  - 本轮代码已经在 `FeedView` 中加入 `router.replace({ query: {} })` 来消费一次性 `source` 参数。
  - 但文档主体的 `## 修复方案` 仍只描述“读取 URL query 参数”，没有把“应用后清理 query，避免刷新覆盖用户后续选择”并入主方案。
  - 当前真正完整的修复逻辑被分散在 `## Review 意见评估与决策` 中，后续读者容易只看上半部分而漏掉关键约束。
- 建议:
  - 将 query 消费逻辑合并回主 `## 修复方案` 与 `## 原因定位`，让文档主线能独立成立，不依赖后续 review 响应补完。

### 2. “测试验证”仍缺少实际执行结果，不宜标记完成

- 级别: `p2`
- 问题:
  - 文档虽然补充了验证场景，但目前记录的仍是测试清单，不是已执行结果。
  - 在没有平台、执行时间、结果记录的情况下，`测试验证` 勾选为已完成仍然偏乐观。
- 建议:
  - 将状态临时改回 `待验证`，或在文档中补充实际执行记录，例如“2026-04-12 / Chrome / 手动验证通过”。
