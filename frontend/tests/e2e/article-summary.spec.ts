import { test, expect, type Page } from '@playwright/test'

const USER = {
  id: 'summary-e2e-user',
  username: 'summary-e2e',
  email: 'summary@example.com',
  preferred_language: 'en'
}

const ARTICLES = [
  {
    id: 1,
    title: 'Article with summary',
    url: 'https://example.com/articles/with-summary',
    summary: '<p>A useful summary.</p><p>Second paragraph<br class="break">with a break.</p>',
    content: '<p>Body for article one.</p>',
    source: 'https://example.com/feed.xml',
    author: 'Readaria QA',
    published_at: '2026-11-03T08:00:00Z',
    updated_at: '2026-11-03T08:00:00Z'
  },
  {
    id: 2,
    title: 'Article without summary',
    url: 'https://example.com/articles/without-summary',
    summary: '<p>&nbsp;</p>',
    content: '<p>Body for article two.</p>',
    source: 'https://example.com/feed.xml',
    author: 'Readaria QA',
    published_at: '2026-11-03T09:00:00Z',
    updated_at: '2026-11-03T09:00:00Z'
  }
]

async function seedAuth(page: Page) {
  await page.addInitScript(({ user }) => {
    localStorage.setItem('readaria_token', 'summary-e2e-token')
    localStorage.setItem('readaria_user', JSON.stringify(user))
    localStorage.setItem('locale', 'en')
    localStorage.setItem('onboarding_state', 'onboarding_complete')
    localStorage.setItem('onboarding_completed', JSON.stringify({ first_audio_played: true }))
  }, { user: USER })
}

async function mockApis(page: Page) {
  await page.route('**/api/auth/me', route => route.fulfill({ json: USER }))
  await page.route('**/api/v1/playback-state', route => route.fulfill({ json: { playlist: [] } }))
  await page.route('**/api/v1/queue', route => route.fulfill({ json: { items: [] } }))
  await page.route('**/api/v1/subscription/me', route => route.fulfill({
    json: {
      plan: 'free', plan_name: 'Free', status: 'active',
      tts_daily_limit: 1, tts_used_today: 0,
      podcast_daily_limit: 0, podcast_used_today: 0
    }
  }))
  await page.route('**/user/*/feeds', route => route.fulfill({
    json: [{ id: 1, feed_name: 'Deep Tech', feed_url: 'https://example.com/feed.xml', is_active: true }]
  }))
  await page.route('**/api/user/*/feeds/articles**', route => route.fulfill({
    json: {
      articles: ARTICLES,
      pagination: { total: ARTICLES.length, playable_total: ARTICLES.length },
      overview: {}
    }
  }))
  await page.route('**/api/articles/by-url**', route => {
    const url = new URL(route.request().url()).searchParams.get('url')
    const article = ARTICLES.find(item => item.url === url)
    return route.fulfill({ json: { article } })
  })
  await page.route('**/api/saved/status**', route => route.fulfill({ json: { saved: false } }))
  await page.route('**/api/articles/read**', route => route.fulfill({ json: { ok: true } }))
  await page.route('**/api/tts/google/client-id', route => route.fulfill({ status: 204, body: '' }))
  await page.route('**/api/auth/google/client-id', route => route.fulfill({ status: 204, body: '' }))
}

async function openArticle(page: Page, index: number) {
  await page.goto(`/article/${encodeURIComponent(ARTICLES[index].url)}`)
}

test.describe('desktop article summary', () => {
  test.use({ viewport: { width: 1440, height: 900 } })
  test.beforeEach(async ({ page }) => {
    await seedAuth(page)
    await mockApis(page)
  })

  test('shows cleaned summary before the body and clears it when switching articles', async ({ page }) => {
    await openArticle(page, 0)
    const summary = page.locator('.reading-article > .article-summary')
    const body = page.locator('.reading-body')
    await expect(summary.locator('.summary-label')).toHaveText('AI Summary')
    expect(await summary.locator('.summary-content').textContent()).toBe('A useful summary.\nSecond paragraph\nwith a break.')
    await expect(body).toContainText('Body for article one.')
    const summaryTop = await summary.evaluate(el => el.getBoundingClientRect().top)
    const bodyTop = await body.evaluate(el => el.getBoundingClientRect().top)
    expect(summaryTop).toBeLessThan(bodyTop)

    await page.locator('.article-list-pane .list-item').nth(1).click()
    await expect(page.locator('.reading-title')).toHaveText('Article without summary')
    await expect(summary.locator('.summary-content')).toHaveText('No summary available')
    await expect(summary.locator('.summary-content')).not.toContainText('A useful summary.')
  })
})

test.describe('mobile article summary', () => {
  test.use({ viewport: { width: 390, height: 844 } })
  test.beforeEach(async ({ page }) => {
    await seedAuth(page)
    await mockApis(page)
  })

  test('shows cleaned summary before the body', async ({ page }) => {
    await openArticle(page, 0)
    const summary = page.locator('.article-content > .article-summary')
    const body = page.locator('.article-content > .article-body')
    await expect(summary.locator('.summary-label')).toHaveText('AI Summary')
    expect(await summary.locator('.summary-content').textContent()).toBe('A useful summary.\nSecond paragraph\nwith a break.')
    await expect(body).toContainText('Body for article one.')
    const summaryTop = await summary.evaluate(el => el.getBoundingClientRect().top)
    const bodyTop = await body.evaluate(el => el.getBoundingClientRect().top)
    expect(summaryTop).toBeLessThan(bodyTop)
  })

  test('shows the empty state when summary is missing', async ({ page }) => {
    await openArticle(page, 1)
    const summary = page.locator('.article-content > .article-summary')
    await expect(summary).toBeVisible()
    await expect(summary.locator('.summary-label')).toHaveText('AI Summary')
    await expect(summary.locator('.summary-content')).toHaveText('No summary available')
    await expect(page.locator('.article-content > .article-body')).toContainText('Body for article two.')
  })
})
