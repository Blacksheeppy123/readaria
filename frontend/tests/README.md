# Playwright E2E 测试文档

## 概述

本项目使用 Playwright 进行端到端测试，覆盖移动端和桌面端的核心功能。

## 安装依赖

```bash
# 安装 Playwright
npm install -D @playwright/test

# 安装浏览器
npx playwright install
```

## 运行测试

### 所有测试

```bash
# Headless 模式（CI环境）
npm run test:e2e

# Headed 模式（可见浏览器）
npm run test:e2e:headed

# UI 模式（交互式调试）
npm run test:e2e:ui
```

### 特定测试文件

```bash
# 只运行认证测试
npx playwright test auth.spec.ts

# 只运行移动端测试
npx playwright test mobile.spec.ts
```

### 特定浏览器/设备

```bash
# 只在 Chromium 运行
npx playwright test --project=chromium

# 只在移动端 Safari 运行
npx playwright test --project=mobile-safari

# 只在移动端 Chrome 运行
npx playwright test --project=mobile-chrome
```

### 调试测试

```bash
# 使用调试器
npx playwright test --debug

# 逐步执行
npx playwright test --headed --slowMo=1000
```

## 查看测试报告

```bash
# 打开 HTML 报告
npm run test:e2e:report

# 或直接打开
npx playwright show-report tests/reports/e2e
```

## 测试覆盖范围

### 核心功能测试

- **auth.spec.ts**: 用户认证流程
  - ✅ 登录/注册
  - ✅ Token 持久化
  - ✅ 错误处理

- **articles.spec.ts**: 文章管理
  - ✅ 列表展示
  - ✅ 分页加载
  - ✅ 下拉刷新
  - ✅ 文章详情
  - ✅ 已读/未读标记

- **saved.spec.ts**: 收藏功能
  - ✅ 收藏文章
  - ✅ 查看收藏列表
  - ✅ 取消收藏

- **search.spec.ts**: 搜索功能
  - ✅ 全文搜索
  - ✅ 关键词高亮
  - ✅ 搜索历史
  - ✅ 用户作用域搜索

- **feeds.spec.ts**: 订阅管理
  - ✅ 查看订阅列表
  - ✅ 添加订阅
  - ✅ 刷新订阅
  - ✅ 删除订阅
  - ✅ URL 验证

### 移动端专项测试

- **mobile.spec.ts**: 移动端特性
  - ✅ 响应式布局
  - ✅ 底部导航
  - ✅ 触摸滚动
  - ✅ 手势操作
  - ✅ 性能测试
  - ✅ 状态保持

## 测试设备配置

### 桌面浏览器
- Chrome (Desktop)
- Safari (Desktop)
- Firefox (Desktop)

### 移动设备模拟
- iPhone 12 (iOS Safari)
- Pixel 5 (Android Chrome)

## 测试策略

### 1. 并发执行
测试默认并发运行，在 CI 环境中串行执行以保证稳定性。

### 2. 重试机制
CI 环境自动重试失败的测试 2 次。

### 3. 截图和视频
- 失败时自动截图
- 失败时保留视频
- 首次重试时记录 trace

### 4. 网络模拟
可以模拟不同网络条件：

```typescript
test.use({
  offline: false,
  httpCredentials: undefined,
});
```

## 编写测试最佳实践

### 1. 使用辅助函数

```typescript
import { login } from '../helpers/utils';

test('example', async ({ page }) => {
  await login(page);
  // 你的测试逻辑
});
```

### 2. 使用语义化的选择器

```typescript
// ❌ 避免
await page.locator('.class-123').click();

// ✅ 推荐
await page.getByRole('button', { name: '登录' }).click();
await page.getByText('文章').click();
```

### 3. 等待策略

```typescript
// 等待导航
await page.waitForURL('**/articles');

// 等待元素可见
await expect(page.getByText('成功')).toBeVisible();

// 等待网络空闲
await page.waitForLoadState('networkidle');
```

### 4. 移动端测试

```typescript
test.use({ ...devices['iPhone 12'] });

test('mobile test', async ({ page }) => {
  // 触摸操作
  await page.touchscreen.tap(100, 100);

  // 滑动
  await page.mouse.move(100, 100);
  await page.mouse.down();
  await page.mouse.move(100, 300);
  await page.mouse.up();
});
```

## 常见问题

### 1. 测试超时

增加超时时间：

```typescript
test('slow test', async ({ page }) => {
  test.setTimeout(60000); // 60 秒
});
```

### 2. 元素未找到

使用更宽松的选择器或等待：

```typescript
// 等待元素出现
await page.waitForSelector('.element', { timeout: 5000 });

// 使用更通用的选择器
await page.locator('[class*="article"]').first();
```

### 3. 网络请求失败

检查后端服务是否启动：

```bash
# 确保后端 API 运行在 localhost:8000
curl http://localhost:8000/api/scheduler/status
```

### 4. 移动端布局问题

确保使用正确的设备配置：

```typescript
test.use({ viewport: { width: 375, height: 667 } });
```

## CI/CD 集成

### GitHub Actions 示例

```yaml
name: E2E Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-node@v3
        with:
          node-version: 18
      - run: npm ci
      - run: npx playwright install --with-deps
      - run: npm run test:e2e
      - uses: actions/upload-artifact@v3
        if: always()
        with:
          name: playwright-report
          path: tests/reports/e2e/
```

## 测试报告

测试报告包含：
- 测试执行结果（通过/失败）
- 执行时间统计
- 失败截图
- 失败视频
- Trace 文件（可回放）

报告位置：`tests/reports/e2e/index.html`

## 下一步

- [ ] 添加 API 测试
- [ ] 添加视觉回归测试
- [ ] 集成代码覆盖率
- [ ] 添加性能监控
- [ ] 添加可访问性测试
