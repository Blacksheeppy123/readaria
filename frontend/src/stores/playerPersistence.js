export const serializePlaylist = (articles = []) => (
  articles.map(article => ({
    id: article.id,
    url: article.url,
    title: article.title,
    summary: article.summary,
    source: article.source,
    author: article.author,
    published_at: article.published_at,
    updated_at: article.updated_at,
    cover: article.cover
  }))
)

export const getMissingPlayableFields = (article) => {
  if (!article) return ['article']

  const missing = []
  if (!article.id) missing.push('id')

  return missing
}

export const shouldHydrateArticleForTts = (article) => (
  Boolean(article?.url && getMissingPlayableFields(article).length > 0)
)
