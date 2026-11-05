import { test, expect } from '@playwright/test';

// 本 spec 验证移动端 UI；钉住移动视口，避免桌面断点（≥1024px）激活桌面布局
test.use({ viewport: { width: 390, height: 844 } });


const mockUser = {
  id: 'test-user-id',
  username: 'test-user',
  email: 'test@example.com',
  preferred_language: 'en',
};

const mockArticle = {
  id: 101,
  title: 'Open article while audio keeps playing',
  url: 'https://example.com/articles/audio-bridge',
  summary: 'The player and article page should share context while audio continues.',
  content: '<p>This is the original article body used for the launch UI bridge test.</p>',
  source: 'https://example.com/feed.xml',
  author: 'Jasmine QA',
  published_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
};

async function mockLaunchApi(page) {
  await page.route('**/api/auth/me', async (route) => {
    await route.fulfill({ json: mockUser });
  });

  await page.route('**/api/v1/playback-state', async (route) => {
    await route.fulfill({ json: { playlist: [] } });
  });

  await page.route('**/api/v1/queue', async (route) => {
    await route.fulfill({ json: { items: [] } });
  });

  await page.route('**/user/*/feeds', async (route) => {
    await route.fulfill({
      json: [
        {
          id: 1,
          feed_name: 'Deep Tech',
          feed_url: 'https://example.com/feed.xml',
          is_active: true,
        },
      ],
    });
  });

  await page.route('**/api/user/*/feeds/articles**', async (route) => {
    await route.fulfill({
      json: {
        articles: [mockArticle],
        pagination: { total: 1, playable_total: 1 },
        overview: {},
      },
    });
  });

  await page.route('**/api/articles/by-url**', async (route) => {
    await route.fulfill({ json: { article: mockArticle } });
  });

  await page.route('**/api/saved/status**', async (route) => {
    await route.fulfill({ json: { saved: false } });
  });

  await page.route('**/api/articles/read', async (route) => {
    await route.fulfill({ json: { status: 'success' } });
  });

  await page.route('**/api/v1/subscription/me', async (route) => {
    await route.fulfill({
      json: {
        plan: 'pro',
        plan_name: 'Pro',
        status: 'active',
        tts_daily_limit: -1,
        tts_used_today: 0,
        podcast_daily_limit: 1,
        podcast_used_today: 0,
      },
    });
  });

  await page.route('**/api/v1/podcasts', async (route) => {
    await route.fulfill({ json: { podcasts: [] } });
  });

  // Mock TTS prepare endpoint: audio is ready
  await page.route('**/api/v1/tts/prepare/*', async (route) => {
    await route.fulfill({ json: { final_ready: true, first_playable_ready: true, status: 'ready' } });
  });

  // Mock the signed-URL handoff, then serve the resulting audio from the existing mock endpoint.
  await page.route('**/api/v1/tts/play-url/*', async (route) => {
    await route.fulfill({ json: { audio_url: '/api/v1/tts/play/101' } });
  });

  // Serve 100 ms of valid PCM silence so browser playback works without an external TTS service.
  await page.route('**/api/v1/tts/play/*', async (route) => {
    const sampleCount = 800;
    const wav = Buffer.alloc(44 + sampleCount * 2);
    wav.write('RIFF', 0);
    wav.writeUInt32LE(36 + sampleCount * 2, 4);
    wav.write('WAVEfmt ', 8);
    wav.writeUInt32LE(16, 16);
    wav.writeUInt16LE(1, 20);
    wav.writeUInt16LE(1, 22);
    wav.writeUInt32LE(8000, 24);
    wav.writeUInt32LE(16000, 28);
    wav.writeUInt16LE(2, 32);
    wav.writeUInt16LE(16, 34);
    wav.write('data', 36);
    wav.writeUInt32LE(sampleCount * 2, 40);
    await route.fulfill({ status: 200, contentType: 'audio/wav', body: wav });
  });
}

async function seedAuth(page) {
  await page.addInitScript(({ user, article }) => {
    localStorage.setItem('readaria_token', 'test-token');
    localStorage.setItem('readaria_user', JSON.stringify(user));
    localStorage.setItem('locale', 'en');
    localStorage.setItem('readaria_cookie_consent', 'accepted');
    localStorage.setItem('onboarding_state', 'onboarding_complete');
    localStorage.setItem('onboarding_completed', JSON.stringify({ first_audio_played: true }));
    localStorage.setItem('tts_playlist', JSON.stringify([article]));
    localStorage.setItem('tts_current_index', '0');
    localStorage.setItem(
      'tts_progress',
      JSON.stringify({
        url: article.url,
        currentTime: 45,
        totalTime: 300,
        timestamp: Date.now(),
      }),
    );
  }, { user: mockUser, article: mockArticle });
}

test.describe('Launch UI critical flow', () => {
  test.beforeEach(async ({ page }) => {
    await mockLaunchApi(page);
    await seedAuth(page);
  });

  test('shows launch Feed and Listen modules with mocked data', async ({ page }) => {
    await page.goto('/feed');

    await expect(page.getByText('Featured')).toBeVisible();
    await expect(page.locator('.feed-overview h2')).toHaveText('1 new articles ready to listen');
    await expect(page.getByRole('button', { name: 'Playable' })).toBeVisible();
    await expect(page.locator('.featured-title')).toHaveText(mockArticle.title);

    await page.getByRole('button', { name: "Generate today's podcast" }).click();
    await expect(page).toHaveURL(/\/listen/);
    await expect(page.getByText('Continue')).toBeVisible();
    await expect(page.getByText('Your queue')).toBeVisible();
    await expect(page.getByText("Today's recap")).toBeVisible();
  });

  test('opens current article from Player without losing article context', async ({ page }) => {
    await page.goto('/player');

    await expect(page.getByText(mockArticle.title)).toBeVisible();
    await page.getByRole('button', { name: 'Open article' }).click();

    await expect(page).toHaveURL(/\/article\//);
    await expect(page.getByRole('heading', { name: mockArticle.title })).toBeVisible();
    await expect(page.getByText('This is the original article body used for the launch UI bridge test.')).toBeVisible();
    await expect(page.locator('.mini-player-bar .mini-player-title')).toHaveText(mockArticle.title);
    await expect(page.locator('.action-bar')).toHaveCount(0);

    // Regression: mini-player must have interactive controls, not a static bar
    await expect(page.locator('.mini-player-bar .mini-player-title')).toBeVisible();
    await expect(page.locator('.mini-player-bar .van-progress')).toBeVisible();
    await expect(page.locator('.mini-player-bar .mini-player-close')).toBeVisible();

    await page.locator('.mini-player-bar').click();
    await expect(page).toHaveURL(/\/player/);
  });

  test('article detail TTS mini-player shows interactive controls on playback', async ({ page }) => {
    await page.addInitScript(() => {
      localStorage.removeItem('tts_playlist');
      localStorage.removeItem('tts_current_index');
      localStorage.removeItem('tts_progress');
    });

    // Go to feed and open the article detail page
    await page.goto('/feed');
    await expect(page.locator('.featured-title')).toHaveText(mockArticle.title);
    await page.locator('.featured-article').click();
    await expect(page).toHaveURL(/\/article\//);

    // Click "Listen to this article" to trigger TTS
    await page.getByRole('button', { name: 'Listen to this article' }).click();

    // Mini-player should appear with loading or play/pause controls (not a static text bar)
    await expect(page.locator('.mini-player-bar')).toBeVisible();
    await expect(page.locator('.mini-player-bar .van-progress')).toBeVisible();
    await expect(page.locator('.mini-player-bar .mini-player-close')).toBeVisible();

    // The action bar should be hidden while the mini-player is active
    await expect(page.locator('.action-bar')).toHaveCount(0);

    // Close the mini-player
    await page.locator('.mini-player-bar .mini-player-close').click();
    await expect(page.locator('.mini-player-bar')).toHaveCount(0);

    // Action bar should reappear
    await expect(page.locator('.action-bar')).toBeVisible();
  });
});
