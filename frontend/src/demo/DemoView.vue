<script setup>
import { onMounted, reactive, ref } from 'vue'
import { createDemoSummary, fetchDemoContent } from './api'
import ByokPanel from './ByokPanel.vue'

const podcasts = ref([])
const articles = ref([])
const loading = ref(true)
const loadError = ref('')
const interactions = reactive({})

onMounted(async () => {
  try {
    const data = await fetchDemoContent()
    podcasts.value = data.podcasts || []
    articles.value = data.articles || []
  } catch (error) {
    loadError.value = error.message
  } finally {
    loading.value = false
  }
})

function formatDate(dateStr) {
  if (!dateStr) return ''
  const date = new Date(dateStr)
  if (Number.isNaN(date.getTime())) return ''
  return date.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })
}

function formatDuration(seconds) {
  if (seconds == null || Number.isNaN(Number(seconds))) return ''
  const total = Math.max(0, Math.floor(Number(seconds)))
  const mins = Math.floor(total / 60)
  const secs = total % 60
  return `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`
}

function podcastMeta(podcast) {
  return [formatDate(podcast.created_at), formatDuration(podcast.duration)].filter(Boolean).join(' · ')
}

async function summarize(article) {
  interactions[article.demo_id] = { loading: true, summary: '', error: '' }
  try {
    const data = await createDemoSummary({ content: article.excerpt })
    interactions[article.demo_id] = { loading: false, summary: data.summary, error: '' }
  } catch (error) {
    interactions[article.demo_id] = { loading: false, summary: '', error: error.message }
  }
}
</script>

<template>
  <main class="demo-page">
    <header class="demo-hero">
      <p class="kicker">Readaria / Public demo</p>
      <h1>Read less.<br><em>Understand more.</em></h1>
      <p class="hero-copy">Real AI-generated podcasts and article summaries — zero API cost to explore, or bring your own OpenAI-compatible key.</p>
    </header>

    <section v-if="podcasts.length" class="featured-podcast" aria-label="Featured podcast">
      <div class="section-heading">
        <p class="kicker">Featured podcast</p>
      </div>
      <article v-for="podcast in podcasts" :key="podcast.share_token" class="podcast-card">
        <h3>{{ podcast.title }}</h3>
        <p v-if="podcastMeta(podcast)" class="podcast-meta">{{ podcastMeta(podcast) }}</p>
        <RouterLink class="link-button" :to="`/podcast-preview/${podcast.share_token}`">
          Listen to the podcast
        </RouterLink>
      </article>
    </section>

    <section class="featured-reading" aria-label="Featured reading">
      <div class="section-heading">
        <p class="kicker">Featured reading</p>
      </div>

      <p v-if="loading" class="notice">Loading featured content…</p>
      <p v-else-if="loadError" class="notice error" role="alert">{{ loadError }}</p>
      <p v-else-if="!podcasts.length && !articles.length" class="notice">
        Content is being prepared — try the interactive mode below.
      </p>

      <article v-for="article in articles" :key="article.demo_id" class="featured-article">
        <p class="source-name">{{ article.source_name }}</p>
        <h3>{{ article.title }}</h3>
        <p class="summary">{{ article.summary }}</p>

        <div class="article-actions">
          <RouterLink class="read-link" :to="`/demo/article/${article.demo_id}`">Read</RouterLink>
          <div v-if="article.excerpt" class="interactive-summary">
            <button
              type="button"
              :disabled="interactions[article.demo_id]?.loading"
              @click="summarize(article)"
            >
              {{ interactions[article.demo_id]?.loading ? 'Generating…' : 'AI Summary (your key)' }}
            </button>
          </div>
        </div>
        <p v-if="interactions[article.demo_id]?.summary" class="live-result">
          <strong>Your live summary</strong>
          {{ interactions[article.demo_id].summary }}
        </p>
        <p v-if="interactions[article.demo_id]?.error" class="error" role="alert">
          {{ interactions[article.demo_id].error }}
        </p>
      </article>
    </section>

    <section class="byok-section" aria-labelledby="try-byok-title">
      <h2 id="try-byok-title">Try it with your own key</h2>
      <ByokPanel />
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
  margin-bottom: 56px;
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

.featured-reading,
.byok-section {
  margin-top: 56px;
}

.section-heading {
  padding-bottom: 12px;
  border-bottom: 2px solid var(--readaria-navy);
}

.section-heading .kicker {
  margin: 0;
}

.podcast-card,
.featured-article {
  padding: 28px 0;
  border-bottom: 1px solid rgba(27, 41, 58, 0.18);
}

h3 {
  margin: 0 0 12px;
  font-family: Georgia, 'Times New Roman', serif;
  font-size: 26px;
  font-weight: 400;
  line-height: 1.2;
}

.podcast-meta {
  margin: 0 0 20px;
  color: rgba(27, 41, 58, 0.65);
  font-size: 13px;
}

.link-button,
.read-link {
  color: var(--readaria-accent);
  font-size: 13px;
  font-weight: 800;
  text-decoration: none;
}

.link-button {
  display: inline-block;
  padding: 10px 16px;
  border: 1px solid var(--readaria-accent);
  border-radius: 3px;
}

.source-name {
  margin: 0 0 8px;
  color: var(--readaria-accent);
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 0.11em;
  text-transform: uppercase;
}

.summary {
  display: -webkit-box;
  margin: 0;
  overflow: hidden;
  color: rgba(27, 41, 58, 0.78);
  font-size: 14px;
  line-height: 1.75;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}

.article-actions {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 16px;
  margin-top: 18px;
}

.interactive-summary button {
  padding: 0;
  border: 0;
  background: transparent;
  color: rgba(27, 41, 58, 0.62);
  font: inherit;
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
}

.interactive-summary button:disabled {
  cursor: wait;
  opacity: 0.55;
}

.live-result {
  margin: 18px 0 0;
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

.byok-section h2 {
  margin: 0 0 18px;
  font-family: Georgia, 'Times New Roman', serif;
  font-size: 24px;
  font-weight: 400;
}

.notice {
  margin: 0;
  padding: 24px 0;
  color: rgba(27, 41, 58, 0.68);
  font-size: 14px;
  line-height: 1.6;
}

.error {
  color: #a13224;
  font-size: 13px;
}

@media (max-width: 640px) {
  .demo-page { padding: 38px 18px 60px; }
  .demo-hero { margin-bottom: 42px; }
  .featured-reading,
  .byok-section { margin-top: 42px; }
  h3 { font-size: 23px; }
}
</style>
