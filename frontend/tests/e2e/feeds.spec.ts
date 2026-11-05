import { test, expect, type Page } from '@playwright/test';
import { login } from '../helpers/utils';

// 本 spec 验证移动端 UI；钉住移动视口，避免桌面断点（≥1024px）激活桌面布局
test.use({ viewport: { width: 390, height: 844 } });

async function mockFeedApis(page: Page) {
  const feeds = [{
    id: 1,
    feed_name: '示例博客',
    feed_url: 'https://example.com/feed.xml',
    is_active: true,
  }];

  await page.route('**/user/*/feeds', async (route) => {
    if (route.request().method() === 'GET') {
      await route.fulfill({ json: feeds });
      return;
    }

    const body = route.request().postDataJSON();
    const newFeed = {
      id: 2,
      feed_name: body.feed_name,
      feed_url: body.feed_url,
      is_active: true,
    };
    feeds.push(newFeed);
    await route.fulfill({ json: newFeed });
  });

  await page.route('**/user/*/feeds/*', async (route) => {
    if (route.request().method() === 'DELETE') feeds.length = 0;
    await route.fulfill({ json: { status: 'success', data: { deleted: true } } });
  });

  await page.route('**/api/user/*/feeds/refresh/status**', async (route) => {
    await route.fulfill({ json: { results: [] } });
  });

  await page.route('**/api/user/*/feeds/refresh', async (route) => {
    await route.fulfill({ json: { status: 'success', data: { refreshed: feeds.length } } });
  });

  await page.route('**/api/feeds/test', async (route) => {
    const { feed_url: feedUrl } = route.request().postDataJSON();
    if (feedUrl.includes('invalid.example.com')) {
      await route.fulfill({ json: { status: 'error', message: '无法解析该订阅地址' } });
      return;
    }
    await route.fulfill({
      json: {
        status: 'success',
        feed_title: '新增博客',
        optimal_url: feedUrl,
        item_count: 3,
      },
    });
  });
}

test.describe('订阅管理功能', () => {
  test.beforeEach(async ({ page }) => {
    await mockFeedApis(page);
    await login(page);

    await page.locator('.van-tabbar-item').filter({ hasText: '我的' }).click();
    await page.getByText('管理订阅', { exact: true }).click();
    await expect(page).toHaveURL(/\/feed\/manage$/);
    await expect(page.locator('.feed-name')).toHaveText('示例博客');
  });

  test('应该显示订阅列表', async ({ page }) => {
    await expect(page.locator('.van-nav-bar__title')).toHaveText('我的订阅');
    await expect(page.locator('.feed-cell')).toHaveCount(1);
    await expect(page.locator('.feed-name')).toHaveText('示例博客');
  });

  test('应该能够添加订阅', async ({ page }) => {
    await page.locator('.van-nav-bar .van-icon-add-o').click();
    await page.getByPlaceholder('请输入RSS订阅地址').fill('https://example.com/new.xml');

    await expect(page.locator('.result-title')).toHaveText('新增博客');
    await expect(page.locator('.subscribe-btn')).toBeEnabled();
    await page.locator('.subscribe-btn').click();

    await expect(page.locator('.add-feed-popup')).toHaveCount(0);
    await expect(page.locator('.feed-name')).toHaveText(['示例博客', '新增博客']);
  });

  test('应该能够刷新订阅', async ({ page }) => {
    const refreshRequest = page.waitForRequest((request) => {
      return request.method() === 'POST' && new URL(request.url()).pathname.endsWith('/feeds/refresh');
    });

    await page.getByText('刷新全部', { exact: true }).click();
    await refreshRequest;

    await expect(page.getByText('刷新成功', { exact: true })).toBeVisible();
  });

  test('应该能够删除订阅', async ({ page }) => {
    // 删除按钮位于 SwipeCell 的右侧插槽；直接触发其 click 处理器，聚焦验证删除流程。
    await page.locator('.swipe-btn').evaluate((button: HTMLButtonElement) => button.click());
    await expect(page.locator('.van-dialog')).toBeVisible();
    await page.locator('.van-dialog__confirm').click();

    await expect(page.locator('.feed-cell')).toHaveCount(0);
    await expect(page.locator('.empty-state')).toBeVisible();
  });

  test('无效订阅地址应该显示错误并禁止提交', async ({ page }) => {
    await page.locator('.van-nav-bar .van-icon-add-o').click();
    await page.getByPlaceholder('请输入RSS订阅地址').fill('https://invalid.example.com/feed.xml');

    await expect(page.locator('.status-text.error')).toHaveText('无法解析该订阅地址');
    await expect(page.locator('.subscribe-btn')).toBeDisabled();
    await expect(page.locator('.feed-cell')).toHaveCount(1);
  });
});
