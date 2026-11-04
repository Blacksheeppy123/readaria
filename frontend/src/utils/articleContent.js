import DOMPurify from 'dompurify'

/**
 * 文章正文净化：img 懒加载字段修复、协议相对地址补全、防 referrer 泄漏、XSS 白名单过滤。
 * 与 ArticleDetail.vue 的内联逻辑保持一致（该视图暂不动，避免移动端回归）。
 */
export function sanitizeArticleContent(content) {
  if (!content) return ''
  let html = String(content)

  // 纯文本 → 段落
  if (!html.includes('<')) {
    html = html.split('\n').map((p) => `<p>${p}</p>`).join('')
  }

  // 1) data-src/lazy-src 等 → src
  html = html.replace(/<img([^>]*?)(data-src|data-original|data-url|lazy-src)=("|')([^"']+)("|')/gi, (
    _m, pre, _attr, q1, url, q2
  ) => `<img${pre}src=${q1}${url}${q2}`)

  // 2) 协议相对地址 //example.com → https://example.com
  html = html.replace(/<img([^>]*?)src=("|')\/\/([^"']+)("|')/gi, (
    _m, pre, q1, hostpath, q2
  ) => `<img${pre}src=${q1}https://${hostpath}${q2}`)

  // 3) img 加 no-referrer + 懒加载
  html = html.replace(/<img(?![^>]*referrerpolicy)([^>]*)>/gi, '<img referrerpolicy="no-referrer" loading="lazy"$1>')

  // 4) XSS 白名单
  return DOMPurify.sanitize(html, { ADD_ATTR: ['referrerpolicy', 'loading', 'target'] })
}

/** 估算阅读时长（分钟）：CJK 约 400 字/分钟 */
export function estimateReadingMinutes(content) {
  if (!content) return 1
  const text = String(content).replace(/<[^>]*>/g, '').trim()
  return Math.max(1, Math.round(text.length / 400))
}

/** 摘要去标签截断 */
export function plainExcerpt(text, maxLength = 120) {
  if (!text) return ''
  const plain = String(text).replace(/<[^>]*>/g, '').trim()
  return plain.length <= maxLength ? plain : plain.substring(0, maxLength) + '…'
}
