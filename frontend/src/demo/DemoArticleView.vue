<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { fetchDemoArticle } from './api'
import { demoApiBaseUrl } from './config'

const route = useRoute()
const article = ref(null)
const loading = ref(true)
const loadError = ref(false)

const excerptParagraphs = computed(() => {
  if (!article.value?.excerpt) return []
  return article.value.excerpt.split(/\n\s*\n/).map(paragraph => paragraph.trim()).filter(Boolean)
})

const publishedDate = computed(() => {
  if (!article.value?.published_at) return ''
  const date = new Date(article.value.published_at)
  if (Number.isNaN(date.getTime())) return ''
  return date.toLocaleDateString(undefined, { year: 'numeric', month: 'long', day: 'numeric' })
})

onMounted(async () => {
  try {
    article.value = await fetchDemoArticle(route.params.demo_id)
  } catch (_) {
    loadError.value = true
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <main class="demo-article-page">
    <div v-if="loading" class="page-state">Loading…</div>

    <div v-else-if="loadError || !article" class="page-state error-state">
      <p>This demo article is not available.</p>
      <RouterLink class="back-link" to="/">← Back to demo</RouterLink>
    </div>

    <article v-else class="article-content">
      <RouterLink class="back-link" to="/">← Back to demo</RouterLink>

      <header class="article-header">
        <p class="article-meta">
          <span class="source-name">{{ article.source_name }}</span>
          <span v-if="publishedDate">{{ publishedDate }}</span>
        </p>
        <h1>{{ article.title }}</h1>
      </header>

      <section v-if="article.summary" class="summary-card" aria-labelledby="summary-title">
        <h2 id="summary-title">AI Summary</h2>
        <p>{{ article.summary }}</p>
      </section>

      <div class="excerpt-body">
        <p v-for="(paragraph, index) in excerptParagraphs" :key="index">{{ paragraph }}</p>
      </div>

      <a
        v-if="article.original_url"
        class="original-link"
        :href="article.original_url"
        target="_blank"
        rel="noopener noreferrer"
      >
        Open original article
      </a>

      <audio
        v-if="article.audio_url"
        class="article-audio"
        controls
        preload="none"
        :src="`${demoApiBaseUrl}${article.audio_url}`"
      >
        Your browser does not support audio playback.
      </audio>
    </article>

    <footer class="selfhost-bar">
      <a
        class="selfhost-button"
        href="https://github.com/Blacksheeppy123/readaria"
        target="_blank"
        rel="noopener noreferrer"
      >
        Self-host Readaria — it's open source
      </a>
    </footer>
  </main>
</template>

<style scoped>
.demo-article-page {
  box-sizing: border-box;
  min-height: 100vh;
  padding-bottom: calc(92px + env(safe-area-inset-bottom));
  color: var(--readaria-navy);
}

.article-content {
  width: min(760px, 100%);
  box-sizing: border-box;
  margin: 0 auto;
  padding: 32px 20px 48px;
}

.back-link {
  display: inline-block;
  color: var(--readaria-muted);
  font-size: 13px;
  font-weight: 700;
  text-decoration: none;
}

.article-header {
  margin-top: 38px;
}

.article-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 14px;
  margin: 0 0 16px;
  color: var(--readaria-muted);
  font-size: 12px;
}

.source-name {
  color: var(--readaria-accent);
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 0.14em;
  text-transform: uppercase;
}

h1 {
  margin: 0;
  font-family: Georgia, 'Times New Roman', serif;
  font-size: clamp(34px, 9vw, 54px);
  font-weight: 400;
  letter-spacing: -0.035em;
  line-height: 1.08;
}

.summary-card {
  margin-top: 34px;
  padding: 20px;
  border-left: 3px solid var(--readaria-accent);
  background: var(--readaria-accent-soft);
}

.summary-card h2 {
  margin: 0 0 10px;
  color: var(--readaria-accent);
  font-size: 11px;
  letter-spacing: 0.14em;
  text-transform: uppercase;
}

.summary-card p {
  margin: 0;
  font-size: 15px;
  line-height: 1.75;
}

.excerpt-body {
  margin-top: 30px;
  color: rgba(27, 41, 58, 0.84);
  font-family: Georgia, 'Times New Roman', serif;
  font-size: 17px;
  line-height: 1.85;
}

.excerpt-body p {
  margin: 0 0 20px;
}

.original-link {
  display: inline-block;
  margin-top: 8px;
  padding: 11px 16px;
  border: 1px solid var(--readaria-accent);
  border-radius: 3px;
  color: var(--readaria-accent);
  font-size: 13px;
  font-weight: 800;
  text-decoration: none;
}

.article-audio {
  width: 100%;
  margin-top: 28px;
}

.page-state {
  display: grid;
  min-height: 65vh;
  place-content: center;
  padding: 24px;
  text-align: center;
}

.error-state {
  gap: 18px;
  color: var(--readaria-muted);
}

.error-state p {
  margin: 0;
}

.selfhost-bar {
  position: fixed;
  right: 0;
  bottom: 0;
  left: 0;
  box-sizing: border-box;
  padding: 12px 20px calc(12px + env(safe-area-inset-bottom));
  border-top: 1px solid var(--readaria-border);
  background: rgba(251, 247, 240, 0.96);
  backdrop-filter: blur(12px);
}

.selfhost-button {
  display: block;
  width: min(720px, 100%);
  box-sizing: border-box;
  margin: 0 auto;
  padding: 13px 18px;
  border-radius: 4px;
  background: var(--readaria-navy);
  color: var(--readaria-paper);
  font-size: 14px;
  font-weight: 800;
  text-align: center;
  text-decoration: none;
}

@media (min-width: 640px) {
  .article-content { padding-top: 48px; }
  .article-header { margin-top: 48px; }
}
</style>
