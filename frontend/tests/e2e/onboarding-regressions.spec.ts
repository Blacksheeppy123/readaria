import { test, expect } from '@playwright/test'

// 本 spec 验证移动端 UI；钉住移动视口，避免桌面断点（≥1024px）激活桌面布局
test.use({ viewport: { width: 390, height: 844 } });


const mockUser = {
  id: 'onboarding-regression-user',
  username: 'test-user',
  email: 'test@example.com',
  preferred_language: 'en'
}

const mockFeeds = [
  {
    id: 1,
    feed_name: 'Deep Tech',
    feed_url: 'https://example.com/feed.xml',
    is_active: true
  }
]

const mockArticle = {
  id: 101,
  title: 'Open article from feed and land at the top',
  url: 'https://example.com/articles/feed-scroll-top',
  summary: 'A long-form article used to verify article-detail scroll restoration.',
  content: '<p>This is the opening paragraph for the article detail regression test.</p>',
  source: 'https://example.com/feed.xml',
  author: 'Readaria QA',
  published_at: new Date().toISOString(),
  updated_at: new Date().toISOString()
}

const mockArticleList = Array.from({ length: 18 }, (_, index) => ({
  ...mockArticle,
  id: 101 + index,
  title: `${mockArticle.title} #${index + 1}`,
  url: `https://example.com/articles/feed-scroll-top-${index + 1}`
}))

const mockPodcast = {
  id: 501,
  title: 'Daily Podcast (April 29) - Deep Dive Briefing',
  description: 'A cached onboarding podcast ready to play immediately.',
  duration: 320,
  play_count: 0,
  generation_status: 'completed',
  source: 'onboarding_cache',
  created_at: new Date().toISOString(),
  articles: [
    {
      id: 201,
      title: mockArticle.title,
      url: mockArticle.url,
      feed_title: 'Deep Tech',
      start_time: 12
    }
  ]
}

async function seedAuth(page) {
  await page.addInitScript(({ user }) => {
    localStorage.setItem('readaria_token', 'test-token')
    localStorage.setItem('readaria_user', JSON.stringify(user))
    localStorage.setItem('readaria_cookie_consent', 'accepted')
    localStorage.setItem('locale', 'en')
    localStorage.setItem('onboarding_state', 'starter_pack_selected')
    localStorage.setItem(
      'onboarding_completed',
      JSON.stringify({
        language_selected: true,
        path_selected: true,
        selected_path: 'starter_pack'
      })
    )
  }, { user: mockUser })
}

async function mockOnboardingRegressionApis(page) {
  await page.route('**/api/v1/subscription/me', async (route) => {
    await route.fulfill({
      json: {
        plan: 'free',
        plan_name: 'Free',
        status: 'active',
        tts_daily_limit: 1,
        tts_used_today: 0,
        podcast_daily_limit: 0,
        podcast_used_today: 0
      }
    })
  })

  await page.route('**/api/auth/me', async (route) => {
    await route.fulfill({ json: mockUser })
  })

  await page.route('**/api/v1/playback-state', async (route) => {
    await route.fulfill({ json: { playlist: [] } })
  })

  await page.route('**/api/v1/queue', async (route) => {
    await route.fulfill({ json: { items: [] } })
  })

  await page.route('**/user/*/feeds', async (route) => {
    if (route.request().method() === 'GET') {
      await route.fulfill({ json: mockFeeds })
      return
    }
    await route.fulfill({ json: { status: 'success' } })
  })

  await page.route('**/api/user/*/feeds/articles**', async (route) => {
    await route.fulfill({
      json: {
        status: 'success',
        articles: mockArticleList,
        pagination: {
          page: 1,
          size: 20,
          total: mockArticleList.length,
          has_more: false,
          playable_total: mockArticleList.length
        },
        overview: {
          today_ready_count: mockArticleList.length
        }
      }
    })
  })

  await page.route('**/api/user/*/feeds/stats', async (route) => {
    await route.fulfill({
      json: {
        total_feeds: 1,
        active_feeds: 1,
        total_articles: mockArticleList.length,
        unread_articles: mockArticleList.length
      }
    })
  })

  await page.route('**/api/articles/by-url**', async (route) => {
    const url = new URL(route.request().url())
    const articleUrl = url.searchParams.get('url')
    const article = mockArticleList.find(item => item.url === articleUrl) || mockArticle
    await route.fulfill({ json: { article } })
  })

  await page.route('**/articles/search**', async (route) => {
    await route.fulfill({ json: { results: [mockArticle] } })
  })

  await page.route('**/api/saved/status**', async (route) => {
    await route.fulfill({ json: { saved: false } })
  })

  await page.route('**/api/saved', async (route) => {
    await route.fulfill({ json: { status: 'success' } })
  })

  await page.route('**/api/articles/read', async (route) => {
    await route.fulfill({ json: { status: 'success' } })
  })

  await page.route('**/api/v1/podcasts/501/audio-url', async (route) => {
    await route.fulfill({ json: { success: true, audio_url: '/mock/podcast.mp3' } })
  })

  await page.route('**/mock/podcast.mp3', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'audio/mpeg',
      body: ''
    })
  })

  await page.route('**/api/v1/podcasts/501/conversations**', async (route) => {
    await route.fulfill({ json: { success: true, conversations: [] } })
  })

  await page.route('**/api/v1/podcasts/501/suggested-questions**', async (route) => {
    await route.fulfill({ json: { success: true, questions: [] } })
  })

  await page.route('**/api/v1/podcasts/501', async (route) => {
    await route.fulfill({ json: { podcast: mockPodcast } })
  })

  await page.route('**/api/v1/podcasts', async (route) => {
    await route.fulfill({ json: { podcasts: [mockPodcast] } })
  })

  await page.route('**/api/tts/google/client-id', async (route) => {
    await route.fulfill({ status: 204, body: '' })
  })

  await page.route('**/api/auth/google/client-id', async (route) => {
    await route.fulfill({ status: 204, body: '' })
  })
}

test.describe('Onboarding regressions', () => {
  test.beforeEach(async ({ page }) => {
    await seedAuth(page)
    await mockOnboardingRegressionApis(page)
  })

  test('first podcast CTA opens podcast detail instead of only leaving a floating player', async ({ page }) => {
    await page.goto('/feed')

    await expect(page.locator('.first-podcast-cta')).toBeVisible()
    await expect(page.getByText('Play Your First Podcast')).toBeVisible()

    await page.locator('.first-podcast-cta').click()

    await expect(page).toHaveURL(/\/podcasts\/501$/)
    await expect(page.getByRole('heading', { name: mockPodcast.title })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Chat with Podcast' })).toBeVisible()
  })

  test('podcast chat page keeps default questions and input composer visible', async ({ page }) => {
    await page.goto('/podcasts/501/chat')

    await expect(page.getByText('Related Articles')).toBeVisible()
    await expect(page.getByText('What are the key takeaways from this podcast?')).toBeVisible()
    await expect(page.getByText('What are the important points to note?')).toBeVisible()
    await expect(page.getByText('Can you summarize the main content?')).toBeVisible()
    await expect(page.getByPlaceholder('Type your question...')).toBeVisible()
    await expect(page.getByRole('button', { name: 'Send' })).toBeVisible()
  })

  test('opening article detail resets the app scroll container to the top', async ({ page }) => {
    await page.goto('/feed')

    await page.evaluate(() => {
      const appScroll = document.querySelector('.content')
      if (appScroll) appScroll.scrollTop = 1200
    })

    await page.locator('.featured-article').click()
    await expect(page).toHaveURL(/\/article\//)
    await expect(page.getByRole('heading', { name: mockArticleList[0].title })).toBeVisible()

    const scrollTop = await page.evaluate(() => {
      const appScroll = document.querySelector('.content')
      return appScroll ? appScroll.scrollTop : -1
    })

    expect(scrollTop).toBeLessThanOrEqual(5)
  })

  test('quick start resets legacy starter-pack feeds before adding localized feeds', async ({ page }) => {
    const seenRequests = []

    await page.route('**/api/v1/onboarding/starter-pack/reset**', async (route) => {
      seenRequests.push({ type: 'reset', url: route.request().url() })
      await route.fulfill({ json: { status: 'success', removed_feed_ids: [11, 12] } })
    })

    await page.route('**/api/v1/onboarding/starter-pack/activate**', async (route) => {
      seenRequests.push({ type: 'starter-pack', url: route.request().url() })
      await route.fulfill({
        json: {
          status: 'success',
          feeds: [
            { feed_name: '牧之野', feed_url: 'https://wechat2rss.marlinworks.xyz/feed/3551111165.xml' },
            { feed_name: '金渐成', feed_url: 'https://wechat2rss.marlinworks.xyz/feed/3639555537.xml' },
            { feed_name: '路透财经早报', feed_url: 'https://wechat2rss.marlinworks.xyz/feed/3589865648.xml' },
            { feed_name: '程苓峰', feed_url: 'https://wechat2rss.marlinworks.xyz/feed/2399005440.xml' }
          ]
        }
      })
    })

    await page.route('**/api/v1/onboarding/experience-podcast?language=zh', async (route) => {
      seenRequests.push({ type: 'experience-podcast', url: route.request().url() })
      await route.fulfill({
        json: {
          success: true,
          podcast: { ...mockPodcast, title: '每日播客（4月30日）' }
        }
      })
    })

    await page.addInitScript(({ user }) => {
      localStorage.setItem('readaria_token', 'test-token')
      localStorage.setItem('readaria_user', JSON.stringify({ ...user, preferred_language: 'zh' }))
      localStorage.setItem('readaria_cookie_consent', 'accepted')
      localStorage.setItem('locale', 'zh')
      localStorage.setItem('onboarding_state', 'onboarding_complete')
      localStorage.setItem(
        'onboarding_completed',
        JSON.stringify({
            language_selected: true
        })
      )
    }, { user: mockUser })

    // Load legacy feeds into feedStore, then enter onboarding without a reload so
    // confirmQuickStart exercises the reset-existing-feeds branch.
    await page.goto('/feed')
    await expect(page.locator('.feed-tabs').getByText('Deep Tech')).toBeVisible()
    await page.evaluate(() => {
      window.history.pushState({}, '', '/onboarding/path')
      window.dispatchEvent(new PopStateEvent('popstate'))
    })
    await expect(page).toHaveURL(/\/onboarding\/path/)

    await page.locator('.path-card--primary .card-cta, .path-card--primary button').first().click()
    await expect(page).toHaveURL(/\/feed/)

    expect(seenRequests.map(item => item.type)).toEqual([
      'reset',
      'experience-podcast',
      'starter-pack'
    ])
  })
})
