export const isDemoMode = import.meta.env.VITE_DEMO_MODE === 'true'
export const demoApiBaseUrl = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '')
