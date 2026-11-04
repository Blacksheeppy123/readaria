import request from './request'

/**
 * 获取 onboarding starter pack feeds（后端 validated 列表）
 * @param {string} language - 语言代码
 */
export function getOnboardingStarterPack(language = 'en') {
  return request({
    url: '/api/v1/onboarding/starter-pack',
    method: 'get',
    params: { language }
  })
}

export function resetOnboardingStarterPack(language = 'en', options = {}) {
  const silent = !!options.silent
  return request({
    url: '/api/v1/onboarding/starter-pack/reset',
    method: 'post',
    params: { language },
    silent,
    headers: silent ? { 'X-Silent': '1' } : undefined
  })
}

export function activateOnboardingStarterPack(language = 'en', options = {}) {
  const silent = !!options.silent
  return request({
    url: '/api/v1/onboarding/starter-pack/activate',
    method: 'post',
    params: { language },
    silent,
    preserveEnvelope: true,
    headers: silent ? { 'X-Silent': '1' } : undefined
  })
}

/**
 * 创建 onboarding experience 播客（Magic Moment）
 * @param {string} language - 用户语言
 */
export function createExperiencePodcast(language = 'zh', options = {}) {
  const silent = !!options.silent
  return request({
    url: '/api/v1/onboarding/experience-podcast',
    method: 'post',
    params: { language },
    silent,
    headers: silent ? { 'X-Silent': '1' } : undefined
  })
}
