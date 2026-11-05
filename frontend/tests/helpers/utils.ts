/**
 * 测试工具函数
 */

import { Page } from '@playwright/test';

/**
 * 登录辅助函数
 */
export async function login(page: Page, username = 'test-user', password = 'test1234') {
  await page.addInitScript((userId) => {
    localStorage.setItem('locale', 'zh');
    localStorage.setItem('readaria_cookie_consent', 'accepted');
    localStorage.setItem('onboarding_state', 'onboarding_complete');
    localStorage.setItem('onboarding_completed', JSON.stringify({ first_audio_played: true }));
    localStorage.setItem('last_user_id', userId);
  }, username);
  await page.goto('/login');
  await page.getByPlaceholder('请输入用户名').fill(username);
  await page.getByPlaceholder('请输入密码').fill(password);
  await page.getByRole('button', { name: '登录' }).click();
  await page.waitForURL('**/feed', { timeout: 10000 });
  await page.locator('.van-tabbar').waitFor({ state: 'visible' });
}

/**
 * 注册新用户
 */
export async function register(page: Page, username: string, email: string, password: string) {
  await page.goto('/');
  await page.getByText('还没有账号？').click();

  await page.locator('input[type="text"]').fill(username);
  await page.locator('input[type="email"]').fill(email);
  await page.locator('input[type="password"]').first().fill(password);
  await page.locator('input[type="password"]').last().fill(password);

  await page.getByRole('button', { name: '注册' }).click();
}

/**
 * 退出登录
 */
export async function logout(page: Page) {
  await page.getByText('我的').click();
  const logoutButton = page.getByText(/退出|登出/i);
  if (await logoutButton.isVisible()) {
    await logoutButton.click();
  }
}

/**
 * 添加订阅源
 */
export async function addFeed(page: Page, feedUrl: string) {
  await page.getByText('订阅').click();

  const addButton = page.locator('button[class*="add"], .van-icon-plus').first();
  await addButton.click();

  const urlInput = page.locator('input[placeholder*="URL"], input[name="url"]').first();
  await urlInput.fill(feedUrl);

  const submitButton = page.getByRole('button', { name: /确定|添加|提交/i });
  await submitButton.click();

  await page.waitForTimeout(1000);
}

/**
 * 等待网络空闲
 */
export async function waitForNetworkIdle(page: Page, timeout = 3000) {
  await page.waitForLoadState('networkidle', { timeout });
}

/**
 * 清除localStorage
 */
export async function clearLocalStorage(page: Page) {
  await page.evaluate(() => localStorage.clear());
}

/**
 * 清除sessionStorage
 */
export async function clearSessionStorage(page: Page) {
  await page.evaluate(() => sessionStorage.clear());
}

/**
 * 获取localStorage数据
 */
export async function getLocalStorage(page: Page, key: string) {
  return await page.evaluate((k) => localStorage.getItem(k), key);
}

/**
 * 设置localStorage数据
 */
export async function setLocalStorage(page: Page, key: string, value: string) {
  await page.evaluate(
    ({ k, v }) => localStorage.setItem(k, v),
    { k: key, v: value }
  );
}

/**
 * 模拟下拉刷新
 */
export async function pullToRefresh(page: Page) {
  const startY = 100;
  const endY = 300;

  await page.touchscreen.tap(100, startY);
  await page.mouse.move(100, startY);
  await page.mouse.down();
  await page.mouse.move(100, endY, { steps: 10 });
  await page.mouse.up();

  await page.waitForTimeout(1000);
}

/**
 * 滚动到页面底部
 */
export async function scrollToBottom(page: Page) {
  await page.evaluate(() => {
    window.scrollTo(0, document.body.scrollHeight);
  });
  await page.waitForTimeout(500);
}

/**
 * 检查元素是否在视口内
 */
export async function isInViewport(page: Page, selector: string): Promise<boolean> {
  return await page.evaluate((sel) => {
    const element = document.querySelector(sel);
    if (!element) return false;

    const rect = element.getBoundingClientRect();
    return (
      rect.top >= 0 &&
      rect.left >= 0 &&
      rect.bottom <= window.innerHeight &&
      rect.right <= window.innerWidth
    );
  }, selector);
}

/**
 * 生成随机字符串
 */
export function randomString(length = 8): string {
  return Math.random().toString(36).substring(2, 2 + length);
}

/**
 * 生成测试邮箱
 */
export function generateTestEmail(): string {
  return `test-${randomString()}@example.com`;
}

/**
 * 截图并保存
 */
export async function takeScreenshot(page: Page, name: string) {
  await page.screenshot({ path: `tests/reports/screenshots/${name}.png`, fullPage: true });
}
