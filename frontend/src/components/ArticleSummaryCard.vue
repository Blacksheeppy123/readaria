<script setup>
import { computed } from 'vue'

const props = defineProps({
  summary: { type: String, default: '' }
})

const cleanSummary = computed(() => {
  const withLineBreaks = (props.summary || '')
    .replace(/<br\b[^>]*>/gi, '\n')
    .replace(/<\/(?:address|article|aside|blockquote|dd|div|dl|dt|figcaption|figure|footer|form|h[1-6]|header|li|main|nav|ol|p|pre|section|table|tbody|td|tfoot|th|thead|tr|ul)\s*>/gi, '\n')
  const doc = new DOMParser().parseFromString(withLineBreaks, 'text/html')

  return (doc.body.textContent || '')
    .replace(/\r\n?/g, '\n')
    .replace(/ /g, ' ')
    .replace(/[ \t]*\n[ \t]*/g, '\n')
    .replace(/\n{3,}/g, '\n\n')
    .trim()
})
</script>

<template>
  <section class="article-summary" :aria-label="$t('articles.summary')">
    <div class="summary-label">{{ $t('articles.summary') }}</div>
    <div class="summary-content">{{ cleanSummary || $t('articles.noSummary') }}</div>
  </section>
</template>

<style scoped>
.article-summary {
  padding: 16px;
  background: rgba(255, 252, 248, 0.88);
  margin: 0 0 24px;
  border-radius: 22px;
  border: 1px solid var(--readaria-border);
  border-left: 4px solid var(--readaria-accent);
  box-shadow: 0 16px 34px rgba(66, 49, 33, 0.08);
}
.summary-label {
  font-size: 11px;
  font-weight: 600;
  color: #9a674f;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  margin-bottom: 8px;
}
.summary-content {
  font-size: 14px;
  line-height: 1.6;
  color: var(--readaria-ink);
  white-space: pre-line;
}
</style>
