# Sharing Feature Design — Articles & Podcasts

## Overview

Readaria currently has minimal sharing: articles share the original URL via Web Share API or clipboard. Podcasts have no sharing at all. This design adds branded share pages for both content types, turning sharing into a user acquisition channel.

**Philosophy**: Functional first, no incentives. A recipient should experience the product value (clean reading, podcast listening) before being asked to install.

---

## Goals

1. **Article sharing**: Share a Readaria-branded reader page (`/read?url=...`) instead of the raw original URL
2. **Podcast sharing**: Enable sharing generated podcasts via a public preview page with free N-minute playback
3. **Social presence**: Dynamic Open Graph tags so shared links look good on Twitter/X, WhatsApp, WeChat, etc.
4. **Growth loop**: Every share is a low-friction onboarding opportunity — recipients experience value before registration

**Non-goals (Phase 1)**:
- Referral rewards or invite tracking
- Share analytics or attribution
- Branded share card image generation (Phase 2)
- Per-platform deep-link sharing (Phase 2)

---

## Architecture

```
Logged-in User                    Public Recipient
     │                                  │
     ▼                                  ▼
┌─────────────┐                ┌─────────────────┐
│ Article/    │──share───────►│ /read?url=...   │
│ Podcast     │   link        │ (no auth)       │
│ Detail View │                │                 │
└─────────────┘                │ Branded reader  │
                               │ or podcast      │
                               │ preview player  │
                               │                 │
                               │ [Open in        │
                               │  Readaria] CTA  │
                               └─────────────────┘
```

**Key decisions**:
- Public share pages are lightweight (no full Vue app bundle) for fast load times
- OG tags are injected at the edge by Cloudflare Workers
- Podcast preview cutoff is client-enforced (N minutes, configurable)
- No authentication required to view share pages or preview podcasts

---

## Phase 1: MVP

### 1. Article Sharing

#### In-App Share Flow

In `ArticleDetail.vue`, replace the current single `shareArticle()` with a `ShareSheet` bottom popup:

**Actions (Phase 1)**:
- **Copy Link** — copies `/read?url=<base64-encoded-url>`
- **System Share** — `navigator.share({ title, text, url })`
- **Cancel**

#### Public Reader Page (`/read?url=`)

A lightweight standalone page — not the full Vue app:

| Element | Description |
|---------|-------------|
| Header | Minimal Readaria logo + back link |
| Title | Article title (server-fetched) |
| Meta | Source name + estimated read time |
| Content | Clean-rendered article body (readability-extracted) |
| Link | "Read full article" — links to original URL |
| CTA | Sticky bottom bar: "Open in Readaria" — links to app home with install prompt |

**URL format**: `/read?url=<base64-encoded-original-url>`

**Content fetching**: Backend fetches the original URL, extracts article text via readability/trafilatura, and returns clean HTML. If extraction fails, redirect to original URL.

**CTA behavior** (MVP): Links to `/` with a banner "Install Readaria for the full experience — save, listen, and get AI summaries." Phase 2 adds universal links / app intent URLs.

---

### 2. Podcast Sharing

#### In-App Share Flow

In `PodcastDetailView.vue`, add a share icon to the top nav bar. Share sheet same pattern as articles:

**Actions (Phase 1)**:
- **Copy Link** — copies `/podcast-preview/<id>`
- **System Share** — `navigator.share({ title, text, url })`
- **Cancel**

#### Public Podcast Preview Page (`/podcast-preview/:id`)

| Element | Description |
|---------|-------------|
| Header | Minimal Readaria logo |
| Cover | Podcast cover art (square, centered) |
| Title | Podcast title |
| Meta | "Daily Digest" + date + total duration |
| Player | HTML5 `<audio>` with custom minimal UI (play/pause, progress bar, time) |
| Stories | List of story titles included in the podcast |
| CTA | Sticky bottom bar: "Open in Readaria — Full episodes, AI chat" |

#### Preview Cutoff Logic

```javascript
const PREVIEW_MINUTES = 2  // Configurable per environment
const STORAGE_KEY = 'podcast_preview_' + podcastId

// Track cumulative listened time via audio timeupdate events
if (cumulativeListened >= PREVIEW_MINUTES * 60) {
  audio.pause()
  showRegisterModal()
}

// Register modal:
// "Enjoying the podcast? 🎧"
// "Create a free account to listen to the full episode."
// [Continue Listening] → /register?redirect=/podcast/<id>
// [Maybe Later]       → Close modal, stay on page
```

**Tracking**: Use `sessionStorage` (not `localStorage`) — preview entitlement resets per browser session. Keeps it feeling like a genuine preview, not a hard paywall.

**Audio delivery**: Same MP3 file as the full app. The endpoint returns a time-limited signed URL (30-minute expiry) to prevent hotlinking. No separate "preview" audio file needed.

---

### 3. Share UI Component

**New file**: `frontend/src/components/ShareSheet.vue`

Built on Vant's `van-action-sheet`. Reusable across ArticleDetail and PodcastDetailView:

```vue
<ShareSheet
  v-model:show="showShareSheet"
  :title="shareTitle"
  :url="shareUrl"
  :type="'article' | 'podcast'"
/>
```

**Placement**:

| Screen | Location | Trigger |
|--------|----------|---------|
| ArticleDetail.vue | Top nav bar + bottom action bar | `van-icon name="share-o"` |
| PodcastDetailView.vue | Top nav bar | `van-icon name="share-o"` |

---

### 4. Open Graph Tags

Injected at the Cloudflare Worker edge. The Worker intercepts requests to share URLs, fetches metadata from the backend, and injects `<meta property="og:*">` tags into the HTML before returning it.

**Article share OG tags**:
```html
<meta property="og:title" content="{article.title}">
<meta property="og:description" content="{article.summary | slice(0,200)}">
<meta property="og:url" content="https://readaria.com/read?url={encoded}">
<meta property="og:type" content="article">
<meta property="og:site_name" content="Readaria">
```

**Podcast preview OG tags**:
```html
<meta property="og:title" content="{podcast.title}">
<meta property="og:description" content="{podcast.description | slice(0,200)}">
<meta property="og:url" content="https://readaria.com/podcast-preview/{id}">
<meta property="og:type" content="music.song">
<meta property="og:image" content="{podcast.cover_art_url}">
<meta property="og:site_name" content="Readaria">
```

**Phase 2**: Add `og:image` for articles via server-generated branded cards (1200×630).

---

### 5. Backend API

#### New Endpoints

```
GET /api/v1/share/article-meta?url=<url>
  Response: {
    title: string,
    summary: string | null,
    source_name: string,
    content_html: string,  // readability-extracted clean HTML
    estimated_read_time: number  // minutes
  }
  Auth: None (public)
  Used by: Cloudflare Worker for OG injection + reader page rendering

GET /api/v1/share/podcast-meta/<id>
  Response: {
    id: string,
    title: string,
    description: string,
    cover_art_url: string,
    duration: number,  // seconds
    stories: [
      { title: string, article_url: string }
    ]
  }
  Auth: None (public)
  Used by: Cloudflare Worker for OG injection + preview page

GET /api/v1/share/podcast-audio/<id>?preview=true
  Response: 302 Redirect to signed audio URL (30-min expiry)
  Auth: None (public)
  Used by: Podcast preview page player
```

#### Modified Endpoints

```
GET /api/v1/podcasts/<id>/audio-url
  Add optional ?preview=true query parameter
  When preview=true: return shorter-lived signed URL (30 min vs 24h)
  Existing behavior unchanged when parameter omitted
```

---

### 6. Security, Performance & Compliance

#### Anti-Abuse

| Risk | Mitigation |
|------|-----------|
| Audio hotlinking | Signed URLs with 30-minute expiry |
| Share URL generation abuse | Rate limit per IP: 100 share-link generations/hour |
| Preview page scraping | Standard Cloudflare WAF rules |
| N-minute cutoff bypass | Client-side only for MVP. If abuse becomes material, add server-side session tokens in Phase 2 |

#### Performance

| Concern | Target | Approach |
|---------|--------|----------|
| Reader page TTFB | < 1s | Server-rendered lightweight HTML, no Vue bundle |
| Audio streaming | Same as app | CDN-delivered MP3s (existing infrastructure) |
| OG tag injection | < 50ms | Edge-computed in CF Worker, backend metadata cached |

#### Content Safety & Compliance

| Concern | Resolution |
|---------|------------|
| Hosting third-party content | Reader page shows extracted content with clear source attribution and link to original. Readaria acts as an aggregator/reader, not a publisher |
| Copyright | Article reader links prominently to original source. Podcasts are AI-generated summaries of user-subscribed feeds |
| Data collection on preview pages | None. No cookies, no tracking pixels, no analytics scripts. Privacy-friendly by default |
| Regional compliance | Share pages are public content viewers. No user PII is collected or stored |

---

## Phase 2: Enhancements (Future)

| Feature | Description |
|---------|-------------|
| Share card images | Server-generated 1200×630 branded cards for articles and podcasts |
| Per-platform sharing | Direct deep links: Twitter/X, WhatsApp, WeChat, Telegram |
| Universal links / App intents | "Open in Readaria" CTA opens the app if installed, App Store otherwise |
| Share analytics | Track share volume, click-through rate, preview-to-signup conversion |
| Long-press share | Podcast cards in list views support long-press for quick share |
| QR code sharing | Generate QR codes for offline sharing (meetings, print) |
| Referral integration | When referral system is built, attach `?ref=<user_id>` to share URLs |

---

## Files to Create / Modify

### New Files

| File | Purpose |
|------|---------|
| `frontend/src/components/ShareSheet.vue` | Reusable share bottom-sheet |
| `frontend/src/views/ShareArticleView.vue` | Public article reader page |
| `frontend/src/views/SharePodcastView.vue` | Public podcast preview page |
| `backend/api/share.py` | Share-related API endpoints |
| `backend/services/article_extractor.py` | Readability/trafilatura wrapper |

### Modified Files

| File | Changes |
|------|---------|
| `frontend/src/views/ArticleDetail.vue` | Replace share function with ShareSheet |
| `frontend/src/views/PodcastDetailView.vue` | Add share button + ShareSheet |
| `frontend/src/router/index.js` | Add `/read` and `/podcast-preview/:id` routes |
| `backend/api/main.py` | Register share router |
| `backend/api/podcasts.py` | Add `?preview=true` to audio-url endpoint |
| `frontend/index.html` | Add static fallback OG tags |
| Cloudflare Worker script | Add OG tag injection logic |

---

## Open Questions (Phase 1)

None remaining. All decisions resolved during design review.

---

## Decision Log

| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-05-07 | Podcast preview: N=2 minutes, client-enforced | Simplest viable anti-abuse. Server-side tokens if abuse materializes |
| 2026-05-07 | Article share: `/read?url=<base64>` branded page | Drives app installs vs sharing raw URL. MVP CTA is web link, not universal link |
| 2026-05-07 | No share incentives in Phase 1 | User explicitly deferred referral/reward system |
| 2026-05-07 | OG tags injected at Cloudflare edge | No SSR needed. Leverages existing CF Workers infrastructure |
| 2026-05-07 | Preview tracking in sessionStorage | Resets per session, keeps preview feeling genuine |
| 2026-05-07 | No separate preview audio file | Same MP3, signed URLs for hotlink protection. Simpler infra |
