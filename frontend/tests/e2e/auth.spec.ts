import { test, expect } from '@playwright/test';

// 本 spec 验证移动端 UI；钉住移动视口，避免桌面断点（≥1024px）激活桌面布局
test.use({ viewport: { width: 390, height: 844 } });


const mockUser = {
  id: 'test-user-id',
  username: 'test-user',
  email: 'test@example.com',
  preferred_language: 'en',
};

async function mockAuthApi(page) {
  await page.route('**/api/auth/google/client-id', async (route) => {
    await route.fulfill({ json: {} });
  });

  await page.route('**/api/v1/playback-state', async (route) => {
    await route.fulfill({ json: { playlist: [] } });
  });

  await page.route('**/api/v1/queue', async (route) => {
    await route.fulfill({ json: { items: [] } });
  });

  await page.route('**/api/v1/podcasts', async (route) => {
    await route.fulfill({ json: { podcasts: [] } });
  });

  await page.route('**/api/auth/login', async (route) => {
    const body = route.request().postDataJSON();
    if (body.username === 'test-user' && body.password === 'test123') {
      await route.fulfill({
        json: {
          user: mockUser,
          access_token: 'test-token',
        },
      });
      return;
    }

    await route.fulfill({
      status: 401,
      json: { detail: 'Login failed' },
    });
  });

  await page.route('**/api/auth/me', async (route) => {
    await route.fulfill({ json: mockUser });
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
        articles: [
          {
            id: 101,
            title: 'Launch article',
            url: 'https://example.com/articles/launch',
            summary: 'A mocked article for auth smoke tests.',
            content: 'Readable launch article body.',
            source: 'https://example.com/feed.xml',
            updated_at: new Date().toISOString(),
          },
        ],
        pagination: { total: 1, playable_total: 1 },
        overview: {},
      },
    });
  });
}

test.describe('Auth flow', () => {
  test.beforeEach(async ({ page }) => {
    await mockAuthApi(page);
    await page.addInitScript(() => {
      localStorage.setItem('readaria_cookie_consent', 'accepted');
      localStorage.setItem('locale', 'en');
    });
  });

  test('shows the launch login page', async ({ page }) => {
    await page.goto('/login');

    await expect(page.getByRole('heading', { name: "Bring your feeds. We'll make them playable." })).toBeVisible();
    await expect(page.getByPlaceholder('Enter username')).toBeVisible();
    await expect(page.getByPlaceholder('Enter password')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Log In' })).toBeVisible();
  });

  test('logs in and lands on the Feed page', async ({ page }) => {
    await page.goto('/login');

    await page.getByPlaceholder('Enter username').fill('test-user');
    await page.getByPlaceholder('Enter password').fill('test123');
    await page.getByRole('button', { name: 'Log In' }).click();

    await page.waitForURL('**/feed');
    await expect(page.getByText('Featured')).toBeVisible();
    await expect(page.getByText('Launch article')).toBeVisible();
  });

  test('navigates from login to register', async ({ page }) => {
    await page.goto('/login');

    await page.getByRole('button', { name: 'Sign Up' }).click();

    await expect(page).toHaveURL(/\/register/);
    await expect(page.getByRole('heading', { name: 'Start with feeds you trust.' })).toBeVisible();
    await expect(page.getByPlaceholder('Enter email')).toBeVisible();
  });

  test('submits registration and redirects to onboarding', async ({ page }) => {
    let registerRequestBody = null;
    await page.route('**/api/auth/register', async (route) => {
      registerRequestBody = route.request().postDataJSON();
      await route.fulfill({
        json: {
          user: {
            id: 'new-user-id',
            username: registerRequestBody.username,
            email: registerRequestBody.email,
            preferred_language: registerRequestBody.preferred_language,
          },
          access_token: 'register-token',
        },
      });
    });

    await page.goto('/register');

    await page.getByPlaceholder('Enter username').fill('new-user');
    await page.getByPlaceholder('Enter email').fill('new-user@example.com');
    await page.getByPlaceholder(/Enter password \(min 8 chars/).fill('password123');
    await page.getByPlaceholder('Enter password again').fill('password123');
    await page.getByRole('button', { name: 'Sign Up' }).click();

    await expect.poll(() => registerRequestBody).not.toBeNull();
    expect(registerRequestBody).toMatchObject({
      username: 'new-user',
      email: 'new-user@example.com',
      password: 'password123',
      preferred_language: 'en',
    });

    await page.waitForURL('**/onboarding/language');
    await expect(page.getByRole('heading', { name: 'Choose Your Language' })).toBeVisible();
  });

  test('shows login failure feedback', async ({ page }) => {
    await page.goto('/login');

    await page.getByPlaceholder('Enter username').fill('wrong-user');
    await page.getByPlaceholder('Enter password').fill('wrong-pass');
    await page.getByRole('button', { name: 'Log In' }).click();

    await expect(page.getByText(/Login failed/i)).toBeVisible();
  });

  test('keeps authenticated users on refresh', async ({ page }) => {
    await page.goto('/login');

    await page.getByPlaceholder('Enter username').fill('test-user');
    await page.getByPlaceholder('Enter password').fill('test123');
    await page.getByRole('button', { name: 'Log In' }).click();
    await page.waitForURL('**/feed');

    await page.reload();

    await expect(page).toHaveURL(/\/feed/);
    await expect(page.getByText('Launch article')).toBeVisible();
  });
});
