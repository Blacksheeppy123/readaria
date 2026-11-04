const KEY_STORAGE = 'readaria_demo_key'
const BASE_URL_STORAGE = 'readaria_demo_base_url'

export const DEFAULT_DEMO_BASE_URL = 'https://api.openai.com/v1'

export function loadDemoCredentials() {
  return {
    apiKey: localStorage.getItem(KEY_STORAGE) || '',
    baseUrl: localStorage.getItem(BASE_URL_STORAGE) || DEFAULT_DEMO_BASE_URL,
  }
}

export function saveDemoCredentials(apiKey, baseUrl) {
  const normalizedKey = apiKey.trim()
  const normalizedBaseUrl = baseUrl.trim() || DEFAULT_DEMO_BASE_URL
  if (normalizedKey) {
    localStorage.setItem(KEY_STORAGE, normalizedKey)
  } else {
    localStorage.removeItem(KEY_STORAGE)
  }
  localStorage.setItem(BASE_URL_STORAGE, normalizedBaseUrl)
  return { apiKey: normalizedKey, baseUrl: normalizedBaseUrl }
}

export function clearDemoCredentials() {
  localStorage.removeItem(KEY_STORAGE)
  localStorage.removeItem(BASE_URL_STORAGE)
}
