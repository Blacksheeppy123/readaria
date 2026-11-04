<template>
  <div class="landing-page">
    <section class="hero">
      <nav class="landing-nav">
        <span class="brand">Readaria</span>
        <div class="nav-actions">
          <button class="lang-switch" @click="toggleLocale">
            EN / 中文
          </button>
          <button class="nav-link" @click="goToLogin">{{ $t('landing.signIn') }}</button>
        </div>
      </nav>

      <div class="hero-grid">
        <div class="hero-copy">
          <p class="eyebrow">{{ $t('landing.eyebrow') }}</p>
          <h1>{{ $t('landing.launchHeadline') }}</h1>
          <p class="hero-subtitle">{{ $t('landing.launchSubtitle') }}</p>
          <div class="hero-actions">
            <van-button round type="primary" size="large" @click="goToRegister">
              {{ $t('landing.primaryCta') }}
            </van-button>
            <van-button round plain size="large" class="secondary-btn" @click="scrollToDemo">
              {{ $t('landing.secondaryCta') }}
            </van-button>
          </div>
          <div class="audience-row">
            <span>{{ $t('landing.audienceFounders') }}</span>
            <span>{{ $t('landing.audienceInvestors') }}</span>
            <span>{{ $t('landing.audienceOperators') }}</span>
            <span>{{ $t('landing.audienceResearchers') }}</span>
          </div>
        </div>

        <div id="hero-preview" class="product-mock" aria-label="Readaria product preview">
          <div class="mock-topbar">
            <span>Readaria</span>
            <span>{{ $t('landing.signIn') }}</span>
          </div>
          <div class="mock-copy">
            <p class="mock-label">{{ $t('landing.previewToday') }}</p>
            <h2>{{ $t('landing.previewHeadline') }}</h2>
            <p>{{ $t('landing.previewDescription') }}</p>
          </div>
          <div class="mock-list">
            <div class="mock-row">
              <div>
                <strong>{{ $t('landing.previewItemOneTitle') }}</strong>
                <span>{{ $t('landing.previewItemOneMeta') }}</span>
              </div>
              <span class="round-token">▶</span>
            </div>
            <div class="mock-row">
              <div>
                <strong>{{ $t('landing.previewItemTwoTitle') }}</strong>
                <span>{{ $t('landing.previewItemTwoMeta') }}</span>
              </div>
              <span class="round-token round-token--soft">+</span>
            </div>
          </div>
          <div class="mock-podcast">
            <span>{{ $t('landing.previewQueueSummary') }}</span>
            <strong>{{ $t('landing.previewQueueCta') }}</strong>
          </div>
        </div>
      </div>
    </section>

    <section class="value-chain">
      <article class="value-item">
        <span>01</span>
        <h3>{{ $t('landing.valueOneTitle') }}</h3>
        <p>{{ $t('landing.valueOneDesc') }}</p>
      </article>
      <article class="value-item">
        <span>02</span>
        <h3>{{ $t('landing.valueTwoTitle') }}</h3>
        <p>{{ $t('landing.valueTwoDesc') }}</p>
      </article>
      <article class="value-item">
        <span>03</span>
        <h3>{{ $t('landing.valueThreeTitle') }}</h3>
        <p>{{ $t('landing.valueThreeDesc') }}</p>
      </article>
    </section>

    <section id="demo" class="demo-band">
      <div class="section-intro">
        <p class="eyebrow">{{ $t('demo.eyebrow') }}</p>
        <h2>{{ $t('demo.headline') }}</h2>
      </div>

      <div class="demo-shell">
        <div class="phone-frame">
          <div class="phone-notch"></div>
          <div class="screen demo-screen">

            <!-- Tab nav -->
            <div class="demo-tabs">
              <button
                :class="{ active: activeTab === 'listen' }"
                @click="activeTab = 'listen'"
              >
                {{ $t('demo.tabListen') }}
              </button>
              <button
                :class="{ active: activeTab === 'podcast' }"
                @click="activeTab = 'podcast'"
              >
                {{ $t('demo.tabPodcast') }}
              </button>
              <button
                :class="{ active: activeTab === 'chat' }"
                @click="activeTab = 'chat'"
              >
                {{ $t('demo.tabChat') }}
              </button>
            </div>

            <!-- Listen Tab -->
            <div v-show="activeTab === 'listen'" class="demo-tab-panel">
              <div
                v-for="article in demoArticles()"
                :key="article.id"
                class="demo-article-card"
              >
                <h4>{{ article.title }}</h4>
                <p class="meta">{{ article.source }} · {{ article.duration }}</p>
                <div class="demo-player-bar">
                  <button
                    class="demo-play-btn"
                    :aria-label="currentSrc === article.audioUrl && isPlaying ? 'Pause article audio' : 'Play article audio'"
                    @click="playArticle(article.audioUrl)"
                  >
                    {{ currentSrc === article.audioUrl && isPlaying ? '⏸' : '▶' }}
                  </button>
                  <div
                    class="demo-wave"
                    :class="{ playing: currentSrc === article.audioUrl && isPlaying }"
                  >
                    <span></span><span></span><span></span><span></span><span></span>
                  </div>
                  <span class="demo-time">{{ article.duration }}</span>
                </div>
              </div>
            </div>

            <!-- Podcast Tab -->
            <div v-show="activeTab === 'podcast'" class="demo-tab-panel">
              <div class="demo-podcast-cover">
                <div
                  class="demo-podcast-ring"
                  :class="{ playing: podcastPlaying && isPlaying }"
                >
                  <span class="ring-icon"></span>
                </div>
                <div
                  class="demo-podcast-wave"
                  :class="{ playing: podcastPlaying && isPlaying }"
                >
                  <span></span><span></span><span></span><span></span><span></span><span></span><span></span>
                </div>
              </div>
              <h3>{{ demoPodcast()?.title || $t('demo.podcastTitle') }}</h3>
              <p class="meta">{{ demoPodcast()?.meta || $t('demo.podcastMeta') }}</p>
              <button class="demo-big-play" @click="playPodcast">
                {{ podcastPlaying && isPlaying ? $t('demo.pause') : $t('demo.playDemo') }}
              </button>
            </div>

            <!-- Chat Tab -->
            <div v-show="activeTab === 'chat'" class="demo-tab-panel">
              <div class="demo-chat-list">
                <div
                  v-for="(qa, idx) in demoQA()"
                  :key="idx"
                  class="demo-chat-item"
                  :class="{ expanded: expandedQA === idx }"
                >
                  <button
                    class="demo-question"
                    :aria-expanded="expandedQA === idx"
                    @click="toggleQA(idx)"
                  >
                    <span class="q-mark">Q</span>
                    <p>{{ qa.question }}</p>
                    <span class="demo-chevron">
                      {{ expandedQA === idx ? '▲' : '▼' }}
                    </span>
                  </button>
                  <div v-show="expandedQA === idx" class="demo-answer">
                    <p>{{ qa.answer }}</p>
                  </div>
                </div>
              </div>
            </div>

            <!-- Bottom CTA -->
            <div class="demo-bottom-cta">
              <p>{{ $t('demo.ctaText') }}</p>
              <button class="demo-cta-btn" @click="goToRegister">
                {{ $t('demo.ctaButton') }}
              </button>
            </div>
          </div>
        </div>
      </div>
    </section>

    <section class="cta">
      <p class="eyebrow">{{ $t('landing.ctaEyebrow') }}</p>
      <h2>{{ $t('landing.ctaHeadline') }}</h2>
      <p>{{ $t('landing.ctaDescription') }}</p>
      <van-button round type="primary" size="large" @click="goToRegister">
        {{ $t('landing.ctaButton') }}
      </van-button>
    </section>

    <footer class="landing-footer">
      <div class="footer-links">
        <router-link to="/privacy">{{ $t('me.privacyPolicy') }}</router-link>
        <span class="footer-divider">·</span>
        <router-link to="/terms">{{ $t('me.termsOfService') }}</router-link>
      </div>
      <p class="footer-copy">© {{ new Date().getFullYear() }} Marlinworks Limited. All rights reserved.</p>
    </footer>
  </div>
</template>

<script setup>
import { ref, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { setLocale } from '@/i18n'
import { useDemoAudio } from '@/composables/useDemoAudio'
import { trackLandingViewed } from '@/utils/analytics'

const router = useRouter()
const { locale } = useI18n()

const { play: playAudio, stop: stopAudio, isPlaying, currentSrc } = useDemoAudio()

const activeTab = ref('listen')
const demoContent = ref(null)
const expandedQA = ref(null)
const podcastPlaying = ref(false)

// Stop audio when switching tabs
watch(activeTab, () => {
  stopAudio()
  podcastPlaying.value = false
})

const toggleLocale = () => {
  setLocale(locale.value === 'zh' ? 'en' : 'zh')
}

const goToRegister = () => router.push({ name: 'register' })
const goToLogin = () => router.push({ name: 'login' })
const scrollToDemo = () => {
  const el = document.getElementById('demo')
  if (el) {
    el.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }
}

onMounted(async () => {
  // 追踪落地页访问（仅首次）
  if (!localStorage.getItem('ph_landing_viewed')) {
    const urlParams = new URLSearchParams(window.location.search)
    trackLandingViewed({
      utm_source: urlParams.get('utm_source') || undefined,
      utm_medium: urlParams.get('utm_medium') || undefined,
      utm_campaign: urlParams.get('utm_campaign') || undefined,
    })
    localStorage.setItem('ph_landing_viewed', '1')
  }

  try {
    const res = await fetch('/demo/demo-content.json')
    demoContent.value = await res.json()
  } catch (e) {
    console.error('Failed to load demo content:', e)
  }
})

const demoArticles = () => {
  const lang = locale.value || 'en'
  return demoContent.value?.[lang]?.articles || []
}

const demoPodcast = () => {
  const lang = locale.value || 'en'
  return demoContent.value?.[lang]?.podcast || null
}

const demoQA = () => {
  const lang = locale.value || 'en'
  return demoContent.value?.[lang]?.qa || []
}

const toggleQA = (idx) => {
  expandedQA.value = expandedQA.value === idx ? null : idx
}

const playPodcast = async () => {
  const podcast = demoPodcast()
  if (!podcast) return
  if (podcastPlaying.value) {
    stopAudio()
    podcastPlaying.value = false
    return
  }
  const ok = await playAudio(podcast.audioUrl)
  if (ok) podcastPlaying.value = true
}

const playArticle = (url) => {
  if (podcastPlaying.value) {
    podcastPlaying.value = false
  }
  playAudio(url)
}

// Reset podcast state when article audio ends
watch(isPlaying, (playing) => {
  if (!playing) {
    podcastPlaying.value = false
  }
})
</script>

<style scoped>
.landing-page {
  min-height: 100%;
  overflow-y: auto;
  background:
    radial-gradient(circle at 0% 8%, rgba(199, 91, 57, 0.12), transparent 25%),
    linear-gradient(180deg, var(--readaria-paper) 0%, var(--readaria-stone) 100%);
  color: var(--readaria-ink);
}

.hero {
  padding: 36px 24px 72px;
}

.landing-nav {
  display: flex;
  justify-content: space-between;
  align-items: center;
  max-width: 1120px;
  margin: 0 auto 48px;
}

.brand {
  font-family: var(--readaria-serif);
  font-size: 24px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.nav-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

.lang-switch {
  border: 1px solid var(--readaria-border);
  background: rgba(255, 252, 248, 0.56);
  color: var(--readaria-ink);
  font-size: 13px;
  font-weight: 600;
  padding: 6px 14px;
  border-radius: 999px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.lang-switch:hover {
  background: rgba(255, 252, 248, 0.88);
  border-color: var(--readaria-muted);
}

.nav-link {
  border: 0;
  background: transparent;
  color: var(--readaria-ink);
  font-size: 14px;
  font-weight: 600;
}

.hero-grid {
  max-width: 1120px;
  margin: 0 auto;
  display: grid;
  gap: 32px;
  align-items: center;
}

.hero-copy {
  display: grid;
  gap: 24px;
}

.eyebrow,
.mock-label,
.value-item span {
  color: #9a674f;
  font-size: 11px;
  letter-spacing: 0.18em;
  text-transform: uppercase;
}

.hero-copy h1,
.mock-copy h2,
.value-item h3,
.cta h2 {
  font-family: var(--readaria-serif);
  font-weight: 600;
}

.hero-copy h1 {
  font-size: clamp(48px, 12vw, 88px);
  line-height: 1.02;
  max-width: 10ch;
}

.hero-subtitle,
.mock-copy p,
.value-item p,
.cta p {
  color: var(--readaria-muted);
  line-height: 1.7;
}

.hero-subtitle {
  max-width: 520px;
  font-size: 16px;
  line-height: 1.65;
  margin-top: 4px;
}

.hero-actions {
  margin-top: 8px;
}

.hero-actions,
.audience-row {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.secondary-btn {
  background: rgba(255, 252, 248, 0.72) !important;
  border-color: var(--readaria-border) !important;
  color: var(--readaria-navy) !important;
}

.audience-row span {
  padding: 8px 12px;
  border-radius: 999px;
  background: rgba(255, 252, 248, 0.56);
  border: 1px solid var(--readaria-border);
  color: var(--readaria-muted);
  font-size: 12px;
}

.product-mock {
  background: rgba(255, 251, 245, 0.92);
  border: 1px solid var(--readaria-border);
  border-radius: 32px;
  padding: 22px;
  display: grid;
  gap: 18px;
  box-shadow: 0 28px 80px rgba(64, 45, 31, 0.18);
}

.mock-topbar,
.mock-row,
.mock-podcast {
  display: flex;
  justify-content: space-between;
  gap: 12px;
}

.mock-topbar {
  color: var(--readaria-muted);
  font-size: 14px;
}

.mock-copy {
  display: grid;
  gap: 10px;
}

.mock-copy h2 {
  font-size: 30px;
  line-height: 1.08;
}

.mock-list {
  background: rgba(255, 252, 248, 0.88);
  border: 1px solid var(--readaria-border);
  border-radius: 24px;
  padding: 14px;
  display: grid;
  gap: 12px;
}

.mock-row div {
  display: grid;
  gap: 4px;
}

.mock-row span {
  color: var(--readaria-muted);
}

.round-token {
  width: 34px;
  height: 34px;
  border-radius: 999px;
  display: grid;
  place-items: center;
  background: var(--readaria-accent-soft);
  color: #b55333;
  font-size: 13px;
  flex-shrink: 0;
}

.round-token--soft {
  background: rgba(23, 33, 48, 0.06);
  color: var(--readaria-muted);
}

.mock-podcast {
  align-items: center;
  border-radius: 999px;
  padding: 12px 16px;
  background: var(--readaria-accent-soft);
  color: #b55333;
  font-size: 13px;
}

.value-chain {
  max-width: 1120px;
  margin: 0 auto;
  padding: 8px 20px 56px;
  display: grid;
  gap: 20px;
}

.value-item {
  border-top: 1px solid var(--readaria-border);
  padding-top: 20px;
  display: grid;
  gap: 8px;
}

.value-item h3 {
  font-size: 24px;
}

.cta {
  margin: 0 20px 0;
  padding: 42px 24px;
  border-radius: 28px;
  background: rgba(255, 251, 245, 0.76);
  border: 1px solid var(--readaria-border);
  text-align: center;
  display: grid;
  justify-items: center;
  gap: 12px;
}

.cta h2 {
  font-size: 36px;
}

.landing-footer {
  padding: 28px 20px 36px;
  text-align: center;
}

.footer-links {
  margin-bottom: 8px;
}

.footer-links a {
  font-size: 13px;
  color: var(--readaria-muted);
}

.footer-divider {
  margin: 0 8px;
  color: rgba(23, 33, 48, 0.28);
}

.footer-copy {
  font-size: 12px;
  color: var(--readaria-muted);
  margin: 0;
}

@media (min-width: 860px) {
  .hero {
    padding-top: 34px;
  }

  .hero-grid {
    grid-template-columns: minmax(0, 0.95fr) minmax(420px, 0.9fr);
  }

  .value-chain {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .cta {
    max-width: 1120px;
    margin: 0 auto;
  }
}

/* Phone frame base styles (extracted from LaunchPreviewView.vue) */
.phone-frame {
  width: 320px;
  background: #1a212d;
  border-radius: 40px;
  padding: 14px;
  box-shadow: 0 24px 64px rgba(25, 35, 48, 0.22);
  position: relative;
}

.phone-notch {
  position: absolute;
  top: 0;
  left: 50%;
  transform: translateX(-50%);
  width: 100px;
  height: 24px;
  background: #1a212d;
  border-radius: 0 0 16px 16px;
  z-index: 2;
  box-shadow: inset 0 -1px 2px rgba(0, 0, 0, 0.3);
}

.screen {
  background: linear-gradient(180deg, #fbf7f0, #f4ede3);
  border-radius: 28px;
  overflow: hidden;
  position: relative;
  z-index: 1;
}

.demo-band {
  max-width: 1120px;
  margin: 0 auto;
  padding: 56px 20px;
}

.demo-band .section-intro {
  text-align: center;
  margin-bottom: 32px;
}

.demo-band h2 {
  font-family: var(--readaria-serif);
  font-size: 36px;
  font-weight: 600;
}

.demo-shell {
  display: flex;
  justify-content: center;
}

.demo-screen {
  min-height: 520px;
  display: flex;
  flex-direction: column;
  padding-top: 28px;
}

.demo-tabs {
  display: flex;
  gap: 6px;
  margin-bottom: 16px;
}

.demo-tabs button {
  flex: 1;
  padding: 8px 12px;
  border-radius: 999px;
  border: 1px solid var(--readaria-border);
  background: rgba(255, 252, 248, 0.56);
  font-size: 13px;
  font-weight: 600;
  color: var(--readaria-muted);
  cursor: pointer;
  transition: all 0.2s ease;
}

.demo-tabs button.active {
  background: var(--readaria-navy);
  color: #f8f2e8;
  border-color: var(--readaria-navy);
}

.demo-tab-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 10px;
  overflow-y: auto;
}

.demo-article-card {
  background: rgba(255, 252, 248, 0.88);
  border: 1px solid var(--readaria-border);
  border-radius: 16px;
  padding: 14px;
}

.demo-article-card h4 {
  font-size: 14px;
  margin-bottom: 4px;
}

.demo-article-card .meta {
  font-size: 12px;
  color: var(--readaria-muted);
  margin-bottom: 10px;
}

.demo-player-bar {
  display: flex;
  align-items: center;
  gap: 10px;
}

.demo-play-btn {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  border: none;
  background: var(--readaria-navy);
  color: #f8f2e8;
  font-size: 12px;
  display: grid;
  place-items: center;
  cursor: pointer;
  flex-shrink: 0;
}

.demo-wave {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 3px;
  height: 28px;
}

.demo-wave span {
  width: 3px;
  border-radius: 999px;
  background: #d4c8b8;
  transition: all 0.3s ease;
}

.demo-wave.playing span {
  background: #c75b39;
  animation: demoPulse 1.2s ease-in-out infinite;
}

.demo-wave span:nth-child(1) { height: 8px; }
.demo-wave span:nth-child(2) { height: 18px; animation-delay: 0.1s; }
.demo-wave span:nth-child(3) { height: 12px; animation-delay: 0.2s; }
.demo-wave span:nth-child(4) { height: 22px; animation-delay: 0.3s; }
.demo-wave span:nth-child(5) { height: 10px; animation-delay: 0.4s; }

@keyframes demoPulse {
  0%, 100% { transform: scaleY(0.5); opacity: 0.5; }
  50% { transform: scaleY(1); opacity: 1; }
}

.demo-time {
  font-size: 11px;
  color: var(--readaria-muted);
  flex-shrink: 0;
}

.demo-podcast-cover {
  height: 180px;
  border-radius: 20px;
  background: radial-gradient(circle at center, rgba(27, 41, 58, 0.08), rgba(27, 41, 58, 0.02));
  display: grid;
  place-items: center;
  position: relative;
  margin-bottom: 12px;
}

.demo-podcast-ring {
  width: 90px;
  height: 90px;
  border-radius: 50%;
  border: 6px solid rgba(27, 41, 58, 0.92);
  box-shadow: 0 0 0 8px rgba(199, 91, 57, 0.12);
  display: grid;
  place-items: center;
  transition: box-shadow 0.3s ease;
}

.demo-podcast-ring.playing {
  animation: ringPulse 2s ease-in-out infinite;
}

.demo-podcast-ring .ring-icon::before {
  content: '▶';
  font-size: 22px;
  color: rgba(27, 41, 58, 0.92);
  margin-left: 3px;
}

.demo-podcast-ring.playing .ring-icon::before {
  content: '⏸';
  margin-left: 0;
}

@keyframes ringPulse {
  0%, 100% { box-shadow: 0 0 0 8px rgba(199, 91, 57, 0.12); }
  50% { box-shadow: 0 0 0 14px rgba(199, 91, 57, 0.22); }
}

.demo-podcast-wave {
  position: absolute;
  bottom: 20px;
  display: flex;
  align-items: center;
  gap: 3px;
  height: 36px;
}

.demo-podcast-wave span {
  width: 4px;
  border-radius: 999px;
  background: #d4c8b8;
  transition: background 0.3s ease;
}

.demo-podcast-wave.playing span {
  background: #c75b39;
  animation: demoPulse 1.2s ease-in-out infinite;
}

.demo-podcast-wave span:nth-child(1) { height: 10px; }
.demo-podcast-wave span:nth-child(2) { height: 22px; animation-delay: 0.1s; }
.demo-podcast-wave span:nth-child(3) { height: 16px; animation-delay: 0.2s; }
.demo-podcast-wave span:nth-child(4) { height: 28px; animation-delay: 0.3s; }
.demo-podcast-wave span:nth-child(5) { height: 14px; animation-delay: 0.4s; }
.demo-podcast-wave span:nth-child(6) { height: 24px; animation-delay: 0.15s; }
.demo-podcast-wave span:nth-child(7) { height: 12px; animation-delay: 0.25s; }

.demo-big-play {
  margin-top: 12px;
  padding: 12px 24px;
  border-radius: 999px;
  border: none;
  background: var(--readaria-navy);
  color: #f8f2e8;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  width: 100%;
}

.demo-chat-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.demo-chat-item {
  background: rgba(255, 252, 248, 0.88);
  border: 1px solid var(--readaria-border);
  border-radius: 14px;
  overflow: hidden;
  cursor: pointer;
}

.demo-question {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 14px;
  width: 100%;
  background: transparent;
  border: none;
  font-family: inherit;
  font-size: inherit;
  color: inherit;
  text-align: left;
  cursor: pointer;
}

.demo-question p {
  flex: 1;
  font-size: 13px;
  margin: 0;
}

.q-mark {
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: var(--readaria-accent-soft);
  color: #b55333;
  font-size: 11px;
  font-weight: 700;
  display: grid;
  place-items: center;
  flex-shrink: 0;
}

.demo-chevron {
  font-size: 10px;
  color: var(--readaria-muted);
  flex-shrink: 0;
}

.demo-answer {
  padding: 0 14px 14px 46px;
  border-top: 1px solid rgba(23, 33, 48, 0.06);
}

.demo-answer p {
  font-size: 13px;
  color: var(--readaria-muted);
  line-height: 1.6;
  margin: 0;
}

.demo-bottom-cta {
  margin-top: auto;
  padding-top: 16px;
  text-align: center;
}

.demo-bottom-cta p {
  font-size: 13px;
  color: var(--readaria-muted);
  margin-bottom: 10px;
}

.demo-cta-btn {
  padding: 10px 20px;
  border-radius: 999px;
  border: none;
  background: rgba(199, 91, 57, 0.12);
  color: #b55333;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
}
</style>
