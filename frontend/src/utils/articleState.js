/**
 * 桌面端打开文章的统一入口：sessionStorage 缓存 + history state。
 * history state 必须是可结构化克隆的纯对象——Pinia/store 的响应式代理
 * 会让 pushState 抛 DataCloneError，Vue Router 降级为 location.assign 整页重载。
 */
export function openArticleInReader(router, article) {
  if (!article?.url) return
  const plain = JSON.parse(JSON.stringify(article))
  try {
    sessionStorage.setItem(`article_${encodeURIComponent(article.url)}`, JSON.stringify(plain))
  } catch (_) {}
  router.push({
    name: 'article-detail',
    params: { id: encodeURIComponent(article.url) },
    state: { article: plain }
  })
}
