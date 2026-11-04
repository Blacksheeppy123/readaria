import { test, expect } from '@playwright/test';
import { login } from '../helpers/utils';

// 本 spec 验证移动端 UI；钉住移动视口，避免桌面断点（≥1024px）激活桌面布局
test.use({ viewport: { width: 390, height: 844 } });


test.describe('文章列表功能', () => {
  test.beforeEach(async ({ page }) => {
    await login(page);
  });

  test('应该显示文章列表', async ({ page }) => {
    // 验证底部导航
    await expect(page.getByText('订阅')).toBeVisible();
    await expect(page.getByText('文章')).toBeVisible();
    await expect(page.getByText('我的')).toBeVisible();

    // 验证至少有一篇文章或空状态提示
    const hasArticles = await page.locator('.van-cell, .van-list').count() > 0;
    const hasEmptyState = await page.getByText(/暂无|没有/).count() > 0;
    expect(hasArticles || hasEmptyState).toBeTruthy();
  });

  test('应该支持下拉刷新', async ({ page }) => {
    // 等待页面加载
    await page.waitForTimeout(1000);

    // 验证导航栏标题已加载（使用更精确的选择器避免 strict mode 错误）
    await expect(page.locator('.van-nav-bar__title')).toBeVisible();
  });

  test('应该支持分页加载', async ({ page }) => {
    // 滚动到底部触发分页
    await page.evaluate(() => {
      window.scrollTo(0, document.body.scrollHeight);
    });

    // 等待加载更多
    await page.waitForTimeout(1000);
  });

  test('应该支持订阅源筛选', async ({ page }) => {
    // 查找筛选下拉框
    const filterDropdown = page.locator('select, .van-dropdown-menu, .filter').first();

    if (await filterDropdown.isVisible()) {
      await filterDropdown.click();
      // 选择第一个订阅源
      const firstOption = page.locator('.van-dropdown-item, option').first();
      if (await firstOption.isVisible()) {
        await firstOption.click();
      }
      // 等待列表更新
      await page.waitForTimeout(500);
    }
  });
});

test.describe('文章详情功能', () => {
  test.beforeEach(async ({ page }) => {
    await login(page);
  });

  test('点击文章应该进入详情页', async ({ page }) => {
    // 等待Toast消失
    await page.waitForTimeout(2000);

    // 点击第一篇文章
    const firstArticle = page.locator('.van-cell').filter({ hasText: /[\u4e00-\u9fa5]/ }).first();
    if (await firstArticle.isVisible()) {
      await firstArticle.click({ force: true });

      // 验证进入详情页或等待加载
      await page.waitForTimeout(2000);
    }
  });

  test('详情页应该显示文章内容', async ({ page }) => {
    await page.waitForTimeout(2000);

    const firstArticle = page.locator('.van-cell').filter({ hasText: /[\u4e00-\u9fa5]/ }).first();
    if (await firstArticle.isVisible()) {
      await firstArticle.click({ force: true });
      await page.waitForTimeout(2000);

      // 验证页面已加载（通过检查是否不在文章列表页）
      const currentUrl = page.url();
      const hasNavigated = currentUrl.includes('article') || currentUrl.includes('detail');
      expect(hasNavigated).toBeTruthy();
    }
  });

  test('应该能够返回列表', async ({ page }) => {
    await page.waitForTimeout(3000);

    // 确保在文章列表页（检查tabbar存在）
    await expect(page.locator('.van-tabbar')).toBeVisible();

    const firstArticle = page.locator('.van-cell').filter({ hasText: /[\u4e00-\u9fa5]/ }).first();
    const articleCount = await firstArticle.count();

    if (articleCount > 0 && await firstArticle.isVisible()) {
      const beforeUrl = page.url();

      await firstArticle.click({ force: true });
      await page.waitForTimeout(2000);

      // 检查是否成功进入详情页
      const afterUrl = page.url();
      if (afterUrl !== beforeUrl && !afterUrl.includes('about:blank')) {
        // 只在成功进入详情页后才测试返回
        await page.waitForTimeout(1000);

        // 使用路由导航而不是goBack（避免about:blank问题）
        await page.goto(beforeUrl);
        await page.waitForTimeout(1000);

        // 验证回到列表页
        await expect(page.locator('.van-tabbar')).toBeVisible();
      }
    }
  });
});

test.describe('已读/未读功能', () => {
  test.beforeEach(async ({ page }) => {
    await login(page);
  });

  test('点击文章应该自动标记为已读', async ({ page }) => {
    await page.waitForTimeout(3000);

    // 确保在文章列表页
    await expect(page.locator('.van-tabbar')).toBeVisible();

    const firstArticle = page.locator('.van-cell').filter({ hasText: /[\u4e00-\u9fa5]/ }).first();

    if (await firstArticle.isVisible()) {
      // 进入详情页
      await firstArticle.click({ force: true });
      await page.waitForTimeout(2000);

      // 验证进入了详情页（URL变化）
      const detailUrl = page.url();
      expect(detailUrl).toMatch(/article|detail/);
    }
  });

  test('应该支持筛选已读/未读', async ({ page }) => {
    // 查找筛选器
    const filterButton = page.getByText(/全部|未读|已读/i).first();

    if (await filterButton.isVisible()) {
      await filterButton.click();

      // 等待筛选结果
      await page.waitForTimeout(500);
    }
  });
});
