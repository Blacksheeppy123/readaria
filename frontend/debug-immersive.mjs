import { chromium } from '@playwright/test';

const ARTICLES = [
  { id: 1, title: '文章一', url: 'https://example.com/article-1', published_at: new Date().toISOString(), summary: 's1', source: 'https://example.com/feed.xml', is_read: false },
  { id: 2, title: '文章二', url: 'https://example.com/article-2', published_at: new Date().toISOString(), summary: 's2', source: 'https://example.com/feed.xml', is_read: false }
];
const FEEDS = [{ id: 11, feed_name: '示例博客', feed_url: 'https://example.com/feed.xml', is_active: true }];

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
page.on('console', m => { if (m.type() === 'error' || m.type() === 'warning') console.log('[console]', m.type(), m.text().slice(0, 200)); });
page.on('pageerror', e => console.log('[pageerror]', String(e).slice(0, 300)));

await page.addInitScript(() => {
  localStorage.setItem('readaria_token', 'e2e-fake-token');
  localStorage.setItem('readaria_user', JSON.stringify({ id: 1, username: 'e2e-user' }));
  localStorage.setItem('onboarding_state', 'onboarding_complete');
  localStorage.setItem('onboarding_completed', JSON.stringify({ first_audio_played: true }));
});
await page.route('**/api/auth/me', r => r.fulfill({ json: { id: 1, username: 'e2e-user' } }));
await page.route('**/api/user/*/feeds/articles**', r => r.fulfill({ json: { articles: ARTICLES, pagination: { total: 2 }, overview: {} } }));
await page.route('**/user/*/feeds', r => r.fulfill({ json: FEEDS }));
await page.route('**/api/articles/by-url**', r => r.fulfill({ json: { article: { ...ARTICLES[0], content: '<p>正文</p>' } } }));
await page.route('**/api/saved/status**', r => r.fulfill({ json: { saved: false } }));
await page.route('**/api/saved**', r => r.fulfill({ json: [] }));
await page.route('**/api/articles/read**', r => r.fulfill({ json: { ok: true } }));

await page.goto('http://localhost:5173/feed');
await page.locator('.article-list-pane .list-item').first().click();
await page.waitForURL(/\/article\//);
await page.keyboard.press('f');
await page.waitForTimeout(300);
console.log('after f: sidebar visible =', await page.locator('.desktop-sidebar').isVisible());
// instrument: what does keydown see?
await page.evaluate(() => {
  window.__keys = [];
  window.addEventListener('keydown', e => window.__keys.push({ key: e.key, target: e.target.tagName, defaultPrevented: e.defaultPrevented }), true);
});
await page.keyboard.press('1');
await page.waitForTimeout(500);
console.log('keys seen:', JSON.stringify(await page.evaluate(() => window.__keys)));
console.log('URL after 1:', page.url());
await browser.close();
