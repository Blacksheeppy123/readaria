<script setup>
import { ref } from 'vue'
import {
  clearDemoCredentials,
  DEFAULT_DEMO_BASE_URL,
  loadDemoCredentials,
  saveDemoCredentials,
} from './storage'

const saved = loadDemoCredentials()
const apiKey = ref(saved.apiKey)
const baseUrl = ref(saved.baseUrl)
const message = ref(saved.apiKey ? 'A key is saved in this browser.' : '')

function save() {
  const credentials = saveDemoCredentials(apiKey.value, baseUrl.value)
  apiKey.value = credentials.apiKey
  baseUrl.value = credentials.baseUrl
  message.value = credentials.apiKey
    ? 'Saved locally. It will only be sent with your demo summary requests.'
    : 'Add an API key to enable interactive summaries.'
}

function clear() {
  clearDemoCredentials()
  apiKey.value = ''
  baseUrl.value = DEFAULT_DEMO_BASE_URL
  message.value = 'Local demo credentials cleared.'
}
</script>

<template>
  <section class="byok-panel" aria-labelledby="byok-title">
    <div class="byok-heading">
      <div>
        <p class="eyebrow">Interactive mode</p>
        <h2 id="byok-title">Bring your own key</h2>
      </div>
      <span class="local-badge">Browser only</span>
    </div>

    <div class="field-grid">
      <label>
        <span>OpenAI-compatible API key</span>
        <input
          v-model="apiKey"
          type="password"
          placeholder="sk-…"
          autocomplete="off"
          autocapitalize="off"
          spellcheck="false"
        >
      </label>
      <label>
        <span>Base URL</span>
        <input
          v-model="baseUrl"
          type="url"
          :placeholder="DEFAULT_DEMO_BASE_URL"
          autocomplete="off"
          spellcheck="false"
        >
      </label>
    </div>

    <div class="byok-actions">
      <button type="button" class="primary-action" @click="save">Save in this browser</button>
      <button type="button" class="secondary-action" @click="clear">Clear</button>
    </div>
    <p class="privacy-note">Never sent to Readaria except as a per-request header. It is not written to our database or application logs.</p>
    <p v-if="message" class="status-message" role="status">{{ message }}</p>
  </section>
</template>

<style scoped>
.byok-panel {
  padding: 24px;
  border: 1px solid rgba(27, 41, 58, 0.16);
  border-radius: 4px;
  background: rgba(255, 255, 255, 0.52);
}

.byok-heading,
.byok-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.eyebrow {
  margin: 0 0 4px;
  color: var(--readaria-accent);
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 0.14em;
  text-transform: uppercase;
}

h2 {
  margin: 0;
  font-family: Georgia, 'Times New Roman', serif;
  font-size: 25px;
  font-weight: 500;
}

.local-badge {
  padding: 5px 9px;
  border: 1px solid rgba(27, 41, 58, 0.2);
  border-radius: 999px;
  font-size: 11px;
  font-weight: 700;
}

.field-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 14px;
  margin: 22px 0 16px;
}

label > span {
  display: block;
  margin-bottom: 7px;
  font-size: 12px;
  font-weight: 700;
}

input {
  box-sizing: border-box;
  width: 100%;
  padding: 11px 12px;
  border: 1px solid rgba(27, 41, 58, 0.25);
  border-radius: 3px;
  background: var(--readaria-paper);
  color: var(--readaria-navy);
  font: inherit;
  font-size: 14px;
}

input:focus {
  outline: 2px solid var(--readaria-accent);
  outline-offset: 1px;
}

.byok-actions {
  justify-content: flex-start;
}

button {
  padding: 10px 15px;
  border-radius: 3px;
  font: inherit;
  font-size: 13px;
  font-weight: 700;
  cursor: pointer;
}

.primary-action {
  border: 1px solid var(--readaria-navy);
  background: var(--readaria-navy);
  color: var(--readaria-paper);
}

.secondary-action {
  border: 1px solid rgba(27, 41, 58, 0.28);
  background: transparent;
  color: var(--readaria-navy);
}

.privacy-note,
.status-message {
  margin: 14px 0 0;
  color: rgba(27, 41, 58, 0.7);
  font-size: 12px;
  line-height: 1.6;
}

.status-message {
  color: var(--readaria-navy);
  font-weight: 700;
}

@media (max-width: 640px) {
  .byok-panel { padding: 19px; }
  .field-grid { grid-template-columns: 1fr; }
}
</style>
