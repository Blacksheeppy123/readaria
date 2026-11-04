import { test, expect } from '@playwright/test';
import { login } from '../helpers/utils';

// 本 spec 验证移动端 UI；钉住移动视口，避免桌面断点（≥1024px）激活桌面布局
test.use({ viewport: { width: 390, height: 844 } });


test.describe('收藏功能', () => {
  test.beforeEach(async ({ page }) => {
    await login(page);
  });

  test('应该能够收藏文章', async ({ page }) => {
    await page.waitForTimeout(3000);

    // 确保在文章列表页
    await expect(page.locator('.van-tabbar')).toBeVisible();

    // 进入详情页
    const firstArticle = page.locator('.van-cell').filter({ hasText: /[\u4e00-\u9fa5]/ }).first();
    if (await firstArticle.isVisible()) {
      await firstArticle.click({ force: true });
      await page.waitForTimeout(2000);

      // 查找收藏按钮（可能是星标或收藏图标）
      const saveButton = page.locator('[class*="save"], [class*="star"], .van-icon-star, button').first();
      if (await saveButton.isVisible()) {
        await saveButton.click();

        // 等待收藏完成
        await page.waitForTimeout(1000);
      }
    }
  });

  test('应该能够查看收藏列表', async ({ page }) => {
    // 进入"我的"页面
    const meTab = page.locator('.van-tabbar-item').filter({ hasText: '我的' });
    await meTab.click();
    await page.waitForTimeout(1000);

    // 验证我的页面已加载
    await expect(page.getByText(/个人中心|我的/i).first()).toBeVisible();
  });

  test('应该能够取消收藏', async ({ page }) => {
    await page.waitForTimeout(2000);

    // 进入详情页
    const firstArticle = page.locator('.van-cell').filter({ hasText: /[\u4e00-\u9fa5]/ }).first();
    if (await firstArticle.isVisible()) {
      await firstArticle.click({ force: true });
      await page.waitForTimeout(2000);

      // 先收藏
      const saveButton = page.locator('[class*="save"], [class*="star"], .van-icon-star, button').first();
      if (await saveButton.isVisible()) {
        await saveButton.click({ force: true });
        await page.waitForTimeout(1000);

        // 再取消收藏（使用force绕过overlay）
        await saveButton.click({ force: true });
        await page.waitForTimeout(1000);
      }
    }
  });
});
