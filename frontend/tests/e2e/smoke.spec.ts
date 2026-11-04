import { test, expect } from '@playwright/test';

// 本 spec 验证移动端 UI；钉住移动视口，避免桌面断点（≥1024px）激活桌面布局
test.use({ viewport: { width: 390, height: 844 } });


test.describe('App smoke', () => {
  test('loads launch landing page', async ({ page }) => {
    await page.goto('/');

    await expect(page.getByRole('heading', { name: 'Turn your feed into a daily brief.' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Start Free' })).toBeVisible();
    await expect(page.getByText('12 new from trusted sources')).toBeVisible();
  });
});
