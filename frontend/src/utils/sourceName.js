const INTERNAL_HOSTS = ['localhost', '127.0.0.1', 'rsshub', 'wechat2rss']

export const normalizeUrlForMatch = (url) => {
  try {
    const u = new URL(url)
    let path = u.pathname
    if (path !== '/' && path.endsWith('/')) path = path.slice(0, -1)
    return `${u.hostname.toLowerCase()}${path}${u.search}`
  } catch {
    return url
  }
}

export const resolveSourceName = (feeds, sourceUrl) => {
  if (!sourceUrl) return null

  // 1) exact match
  let feed = feeds.find(f => f.feed_url === sourceUrl)
  if (feed) return feed.feed_name

  // 2) normalized match (ignore protocol, trailing slash, host case)
  const normalizedSource = normalizeUrlForMatch(sourceUrl)
  feed = feeds.find(f => normalizeUrlForMatch(f.feed_url) === normalizedSource)
  if (feed) return feed.feed_name

  // 3) pathname fallback (internal/Docker addresses only)
  try {
    const sourceUrlObj = new URL(sourceUrl)
    if (!INTERNAL_HOSTS.includes(sourceUrlObj.hostname)) return null
    const sourcePath = sourceUrlObj.pathname.replace(/\/$/, '') || '/'
    feed = feeds.find(f => {
      try {
        const feedPath = new URL(f.feed_url).pathname.replace(/\/$/, '') || '/'
        return feedPath === sourcePath
      } catch { return false }
    })
    if (feed) return feed.feed_name
  } catch {}

  return null
}
