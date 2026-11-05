import { test, expect, Page } from '@playwright/test';

// 桌面端布局 E2E：1440×900 视口。登录态经 localStorage 注入，API 全部 mock，
// 因此不依赖本地后端与测试账号。
test.use({ viewport: { width: 1440, height: 900 } });

// 列表接口为 only_summary（不含 content），正文需经 /api/articles/by-url 补拉——
// 与生产契约一致，覆盖 DesktopArticleReader 的全文补水路径。
const FULL_CONTENT = '<p>过去十二个月里，七大科技巨头的资本支出创下了历史新高。</p><p>这些钱主要流向了 GPU 采购和数据中心建设。</p>';

const ARTICLES = [
  {
    id: 1,
    title: '为什么大公司都在疯狂建数据中心？',
    url: 'https://example.com/article-1',
    author: '作者甲',
    published_at: new Date().toISOString(),
    summary: '过去十二个月里，七大科技巨头的资本支出创下了历史新高。',
    source: 'https://example.com/feed.xml',
    is_read: false
  },
  {
    id: 2,
    title: 'AI 算力需求才刚刚开始',
    url: 'https://example.com/article-2',
    author: '作者乙',
    published_at: new Date().toISOString(),
    summary: '微软、谷歌和亚马逊都在押注同一个判断。',
    source: 'https://example.com/feed.xml',
    is_read: false
  }
];

const FEEDS = [
  { id: 11, feed_name: '示例博客', feed_url: 'https://example.com/feed.xml', is_active: true }
];

async function setupDesktopSession(page: Page) {
  await page.addInitScript(() => {
    localStorage.setItem('readaria_token', 'e2e-fake-token');
    localStorage.setItem('readaria_user', JSON.stringify({ id: 1, username: 'e2e-user', email: 'e2e@example.com' }));
    // 跳过 onboarding 状态机（值为 onboardingStore 的完成态）
    localStorage.setItem('onboarding_state', 'onboarding_complete');
    localStorage.setItem('onboarding_completed', JSON.stringify({ first_audio_played: true }));
  });
  // 认证刷新（request.js 401 会清登录态，必须 mock 成功）
  await page.route('**/api/auth/me', (route) =>
    route.fulfill({ json: { id: 1, username: 'e2e-user', email: 'e2e@example.com' } })
  );
  await page.route('**/api/v1/playback-state', (route) =>
    route.fulfill({ json: { playlist: [] } })
  );
  await page.route('**/api/v1/queue', (route) =>
    route.fulfill({ json: { items: [] } })
  );
  await page.route('**/api/user/*/feeds/articles**', (route) =>
    route.fulfill({ json: { articles: ARTICLES, pagination: { total: 2, playable_total: 0 }, overview: {} } })
  );
  await page.route('**/user/*/feeds', (route) => route.fulfill({ json: FEEDS }));
  await page.route('**/api/articles/by-url**', (route) => {
    const u = new URL(route.request().url());
    const target = ARTICLES.find(a => a.url === u.searchParams.get('url')) || ARTICLES[0];
    return route.fulfill({ json: { article: { ...target, content: FULL_CONTENT } } });
  });
  await page.route('**/api/saved/status**', (route) => route.fulfill({ json: { saved: false } }));
  await page.route('**/api/saved**', (route) => route.fulfill({ json: [] }));
  await page.route('**/api/articles/read**', (route) => route.fulfill({ json: { ok: true } }));
  await page.route('**/api/user/*/feeds/refresh/status**', (route) => route.fulfill({ json: { results: [] } }));
}

test.describe('桌面端三栏布局', () => {
  test.beforeEach(async ({ page }) => {
    await setupDesktopSession(page);
  });

  test('/feed 渲染侧栏 + 列表 + 阅读空态', async ({ page }) => {
    await page.goto('/feed');
    await expect(page.locator('.desktop-sidebar')).toBeVisible();
    await expect(page.locator('.article-list-pane .list-item')).toHaveCount(2);
    await expect(page.locator('.pane-empty')).toBeVisible();
  });

  test('点击文章进入三栏阅读页，正文衬线排版', async ({ page }) => {
    await page.goto('/feed');
    await page.locator('.article-list-pane .list-item').first().click();
    await expect(page).toHaveURL(/\/article\//);
    await expect(page.locator('.reading-pane .reading-title')).toHaveText('为什么大公司都在疯狂建数据中心？');
    await expect(page.locator('.reading-pane .reading-body')).toBeVisible();
    // 中栏列表仍在（三栏布局）
    await expect(page.locator('.article-list-pane .list-item')).toHaveCount(2);
  });

  test('阅读页内切换文章：URL/标题同步，无旧文残留', async ({ page }) => {
    await page.goto('/feed');
    await page.locator('.article-list-pane .list-item').first().click();
    await expect(page.locator('.reading-pane .reading-title')).toHaveText('为什么大公司都在疯狂建数据中心？');
    await page.locator('.article-list-pane .list-item').nth(1).click();
    await expect(page).toHaveURL(/article-2/);
    await expect(page.locator('.reading-pane .reading-title')).toHaveText('AI 算力需求才刚刚开始');
  });

  test('j/k 快捷键移动选中，Enter 打开', async ({ page }) => {    await page.goto('/feed');
    await expect(page.locator('.article-list-pane .list-item')).toHaveCount(2);
    await page.keyboard.press('j');
    await expect(page.locator('.list-item.selected')).toHaveCount(1);
    await page.keyboard.press('k');
    await page.keyboard.press('j');
    await page.keyboard.press('Enter');
    await expect(page).toHaveURL(/\/article\//);
  });

  test('? 打开快捷键帮助，Esc 关闭', async ({ page }) => {
    await page.goto('/feed');
    await page.keyboard.press('?');
    await expect(page.locator('.shortcut-card')).toBeVisible();
    await page.keyboard.press('Escape');
    await expect(page.locator('.shortcut-card')).not.toBeVisible();
  });

  test('1/2/3 切换分区', async ({ page }) => {
    await page.goto('/feed');
    await page.keyboard.press('3');
    await expect(page).toHaveURL(/\/feed\/manage/);
    await expect(page.locator('.desktop-manage')).toBeVisible();
    await page.keyboard.press('1');
    await expect(page).toHaveURL(/\/feed$/);
  });

  test('/feed/manage 显示订阅表格', async ({ page }) => {
    await page.goto('/feed/manage');
    await expect(page.locator('.manage-table tbody tr')).toHaveCount(1);
    await expect(page.getByText('示例博客').first()).toBeVisible();
  });

  test('缩小到移动视口恢复移动布局（无桌面侧栏）', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto('/feed');
    await expect(page.locator('.desktop-sidebar')).not.toBeVisible();
  });

  test('侧栏订阅源列表：点击源即筛选中栏', async ({ page }) => {
    await page.goto('/feed');
    // 侧栏渲染源列表（全部来源 + 示例博客）
    await expect(page.locator('.sidebar-feeds .feed-item')).toHaveCount(2);
    // 监听筛选请求参数
    const requestPromise = page.waitForRequest((req) =>
      req.url().includes('/feeds/articles') && req.url().includes('feed_id=11')
    );
    await page.locator('.sidebar-feeds .feed-item', { hasText: '示例博客' }).click();
    await requestPromise;
    // 工具条显示当前源名
    await expect(page.locator('.list-toolbar .toolbar-source')).toHaveText('示例博客');
  });

  test('阅读页内可直接切换源筛选（不离开当前页）', async ({ page }) => {
    await page.goto('/feed');
    await page.locator('.article-list-pane .list-item').first().click();
    await expect(page).toHaveURL(/\/article\//);
    // 阅读页中栏也有工具条
    await expect(page.locator('.list-toolbar')).toBeVisible();
    await page.locator('.sidebar-feeds .feed-item', { hasText: '示例博客' }).click();
    // URL 不离开文章页，工具条源名更新
    await expect(page).toHaveURL(/\/article\//);
    await expect(page.locator('.list-toolbar .toolbar-source')).toHaveText('示例博客');
  });

  test('拖拽分隔线调整中栏宽度并持久化', async ({ page }) => {
    await page.goto('/feed');
    const divider = page.locator('.pane-divider').last();
    const listCol = page.locator('.feed-column');
    const before = (await listCol.boundingBox())!.width;
    const box = (await divider.boundingBox())!;
    await page.mouse.move(box.x + box.width / 2, box.y + 300);
    await page.mouse.down();
    await page.mouse.move(box.x + 80, box.y + 300, { steps: 5 });
    await page.mouse.up();
    const after = (await listCol.boundingBox())!.width;
    expect(after).toBeGreaterThan(before);
    // localStorage 持久化
    const saved = await page.evaluate(() => localStorage.getItem('readaria_desktop_layout'));
    expect(saved).toBeTruthy();
    // 刷新后宽度保持
    await page.reload();
    await expect(page.locator('.desktop-sidebar')).toBeVisible();
    const persisted = (await page.locator('.feed-column').boundingBox())!.width;
    expect(Math.abs(persisted - after)).toBeLessThan(2);
  });

  test('f 进入沉浸阅读，Esc 退出；桌面端无悬浮播放器', async ({ page }) => {
    await page.goto('/feed');
    // 桌面端不渲染悬浮播放器
    await expect(page.locator('.unified-floating-player')).toHaveCount(0);
    await page.locator('.article-list-pane .list-item').first().click();
    await expect(page).toHaveURL(/\/article\//);
    await page.keyboard.press('f');
    await expect(page.locator('.desktop-sidebar')).not.toBeVisible();
    await expect(page.locator('.reader-column')).not.toBeVisible();
    await expect(page.locator('.reading-pane .reading-title')).toBeVisible();
    await page.keyboard.press('Escape');
    await expect(page.locator('.desktop-sidebar')).toBeVisible();
    await expect(page.locator('.reader-column')).toBeVisible();
  });

  test('离开文章页后自动退出沉浸模式', async ({ page }) => {
    await page.goto('/feed');
    await page.locator('.article-list-pane .list-item').first().click();
    await page.keyboard.press('f');
    await expect(page.locator('.desktop-sidebar')).not.toBeVisible();
    await page.keyboard.press('1');
    await expect(page).toHaveURL(/\/feed$/);
    await expect(page.locator('.desktop-sidebar')).toBeVisible();
  });

  test('排序按钮获得焦点时 Enter 不打开文章', async ({ page }) => {
    await page.goto('/feed');
    await page.keyboard.press('j');
    await page.locator('.sort-btn').focus();
    await page.keyboard.press('Enter');
    await expect(page).toHaveURL(/\/feed$/);
  });
});
