<script setup>
import { onMounted, reactive, ref } from 'vue'
import { createDemoSummary, fetchDemoContent } from './api'
import { demoApiBaseUrl } from './config'
import ByokPanel from './ByokPanel.vue'

const articles = ref([])
const loading = ref(true)
const loadError = ref('')
const interactions = reactive({})

onMounted(async () => {
  try {
    const data = await fetchDemoContent()
    articles.value = data.articles
  } catch (error) {
    loadError.value = error.message
  } finally {
    loading.value = false
  }
})

async function summarize(article) {
  interactions[article.id] = { loading: true, summary: '', error: '' }
  try {
    const data = await createDemoSummary(article)
    interactions[article.id] = { loading: false, summary: data.summary, error: '' }
  } catch (error) {
    interactions[article.id] = { loading: false, summary: '', error: error.message }
  }
}
</script>

<template>
  <main class="demo-page">
    <header class="demo-hero">
      <p class="kicker">Readaria / Public demo</p>
      <h1>Read less.<br><em>Understand more.</em></h1>
      <p class="hero-copy">Explore pre-generated summaries and podcasts at zero API cost, or bring your own OpenAI-compatible key for a live summary.</p>
    </header>

    <ByokPanel />

    <section class="showcase" aria-labelledby="showcase-title">
      <div class="section-heading">
        <p class="kicker">Showcase mode</p>
        <h2 id="showcase-title">A small, curated reading list</h2>
        <p>These summaries and audio samples are seeded with the demo. Viewing them makes no AI API calls.</p>
      </div>

      <p v-if="loading" class="notice">Loading the reading list…</p>
      <p v-else-if="loadError" class="notice error" role="alert">{{ loadError }}</p>

      <article v-for="(article, index) in articles" :key="article.id" class="demo-article">
        <div class="article-index">{{ String(index + 1).padStart(2, '0') }}</div>
        <div class="article-body">
          <a class="source-name" :href="article.url" target="_blank" rel="noopener noreferrer">{{ article.source.name }}</a>
          <h3>{{ article.title }}</h3>
          <p class="summary">{{ article.summary }}</p>

          <audio
            class="audio-player"
            :src="`${demoApiBaseUrl}${article.podcast_audio_url}`"
            controls
            preload="none"
            crossorigin="anonymous"
          >
            Your browser does not support audio playback.
          </audio>

          <div class="interactive-summary">
            <button
              type="button"
              :disabled="interactions[article.id]?.loading"
              @click="summarize(article)"
            >
              {{ interactions[article.id]?.loading ? 'Generating…' : 'AI Summary' }}
            </button>
            <p v-if="interactions[article.id]?.summary" class="live-result">
              <strong>Your live summary</strong>
              {{ interactions[article.id].summary }}
            </p>
            <p v-if="interactions[article.id]?.error" class="error" role="alert">
              {{ interactions[article.id].error }}
            </p>
          </div>
        </div>
      </article>
    </section>
  </main>
</template>

<style scoped>
.demo-page {
  box-sizing: border-box;
  width: min(980px, 100%);
  min-height: 100%;
  margin: 0 auto;
  padding: 56px 28px 80px;
  color: var(--readaria-navy);
}

.demo-hero {
  max-width: 720px;
  margin-bottom: 38px;
}

.kicker {
  margin: 0 0 14px;
  color: var(--readaria-accent);
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 0.17em;
  text-transform: uppercase;
}

h1 {
  margin: 0;
  font-family: Georgia, 'Times New Roman', serif;
  font-size: clamp(46px, 8vw, 82px);
  font-weight: 400;
  letter-spacing: -0.045em;
  line-height: 0.98;
}

h1 em {
  color: var(--readaria-accent);
  font-weight: 400;
}

.hero-copy {
  max-width: 600px;
  margin: 24px 0 0;
  color: rgba(27, 41, 58, 0.72);
  font-size: 16px;
  line-height: 1.75;
}

.showcase {
  margin-top: 56px;
}

.section-heading {
  padding-bottom: 22px;
  border-bottom: 2px solid var(--readaria-navy);
}

.section-heading h2 {
  margin: 0;
  font-family: Georgia, 'Times New Roman', serif;
  font-size: 30px;
  font-weight: 400;
}

.section-heading > p:last-child {
  margin: 10px 0 0;
  color: rgba(27, 41, 58, 0.65);
  font-size: 13px;
  line-height: 1.6;
}

.demo-article {
  display: grid;
  grid-template-columns: 48px 1fr;
  gap: 18px;
  padding: 30px 0;
  border-bottom: 1px solid rgba(27, 41, 58, 0.18);
}

.article-index {
  padding-top: 4px;
  color: var(--readaria-accent);
  font-family: Georgia, 'Times New Roman', serif;
  font-size: 20px;
}

.source-name {
  color: rgba(27, 41, 58, 0.65);
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 0.11em;
  text-decoration: none;
  text-transform: uppercase;
}

h3 {
  margin: 8px 0 12px;
  font-family: Georgia, 'Times New Roman', serif;
  font-size: 26px;
  font-weight: 400;
  line-height: 1.2;
}

.summary {
  margin: 0;
  color: rgba(27, 41, 58, 0.78);
  font-size: 14px;
  line-height: 1.75;
}

.audio-player {
  width: min(440px, 100%);
  height: 36px;
  margin-top: 18px;
}

.interactive-summary {
  margin-top: 16px;
}

.interactive-summary button {
  padding: 9px 15px;
  border: 1px solid var(--readaria-accent);
  border-radius: 3px;
  background: transparent;
  color: var(--readaria-accent);
  font: inherit;
  font-size: 12px;
  font-weight: 800;
  cursor: pointer;
}

.interactive-summary button:disabled {
  cursor: wait;
  opacity: 0.55;
}

.live-result {
  margin: 14px 0 0;
  padding: 14px 16px;
  border-left: 3px solid var(--readaria-accent);
  background: var(--readaria-accent-soft);
  font-size: 14px;
  line-height: 1.7;
}

.live-result strong {
  display: block;
  margin-bottom: 4px;
  font-size: 11px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.notice {
  padding: 24px 0;
}

.error {
  color: #a13224;
  font-size: 13px;
}

@media (max-width: 640px) {
  .demo-page { padding: 38px 18px 60px; }
  .demo-article { grid-template-columns: 30px 1fr; gap: 10px; }
  h3 { font-size: 23px; }
}
</style>
