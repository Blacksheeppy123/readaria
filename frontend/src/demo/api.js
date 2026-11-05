import { demoApiBaseUrl } from './config'
import { loadDemoCredentials } from './storage'

async function parseResponse(response) {
  const data = await response.json().catch(() => ({}))
  if (!response.ok) {
    const error = new Error(data.detail || `Demo request failed (${response.status})`)
    error.status = response.status
    throw error
  }
  return data
}

export async function fetchDemoContent() {
  const response = await fetch(`${demoApiBaseUrl}/api/demo/content`)
  return parseResponse(response)
}

export async function fetchDemoArticles() {
  const response = await fetch(`${demoApiBaseUrl}/api/demo/articles`)
  return parseResponse(response)
}

export async function fetchDemoArticle(demoId) {
  const response = await fetch(`${demoApiBaseUrl}/api/demo/articles/${encodeURIComponent(demoId)}`)
  return parseResponse(response)
}

export async function createDemoSummary(article) {
  const { apiKey, baseUrl } = loadDemoCredentials()
  if (!apiKey) {
    const error = new Error('Add your API key above to use interactive mode.')
    error.status = 400
    throw error
  }

  // Use native fetch rather than the shared Axios client: visitor credentials
  // must not enter global API logging/interceptors.
  const response = await fetch(`${demoApiBaseUrl}/api/demo/summary`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Demo-Api-Key': apiKey,
      'X-Demo-Base-Url': baseUrl,
    },
    body: JSON.stringify({ content: article.content }),
  })
  return parseResponse(response)
}
