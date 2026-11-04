<script setup>
defineOptions({ name: 'DesktopFeedDiscoverView' })
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { showToast } from 'vant'
import { useFeedStore } from '@/stores/feedStore'
import { recommendedFeeds, getFaviconUrl } from '@/config/recommendedFeeds'
import AddFeedPopup from '@/components/AddFeedPopup.vue'

const { t, locale } = useI18n()
const feedStore = useFeedStore()
const subscribingFeeds = ref(new Set())
const searchQuery = ref('')
const showAddPopup = ref(false)

onMounted(async () => {
  // Without this, a direct /feed/discover visit treats every existing feed as
  // unsubscribed until another view happens to populate the shared store.
  if (feedStore.feeds.length === 0) {
    try { await feedStore.fetchFeeds() } catch (_) {}
  }
})

const normalizeUrl = (url) => url?.replace(/\/$/, '') || url
const existingUrls = computed(() => new Set(feedStore.feeds.map(f => normalizeUrl(f.feed_url))))
const isSubscribed = (url) => existingUrls.value.has(normalizeUrl(url))

const getCategoryLabel = (cat) => {
  const lang = locale.value === 'zh' ? 'zh' : 'en'
  return cat.label[lang] || cat.label.en
}

const filteredCategories = computed(() => {
  if (!searchQuery.value.trim()) return recommendedFeeds
  const q = searchQuery.value.toLowerCase()
  return recommendedFeeds
    .map(cat => ({
      ...cat,
      feeds: cat.feeds.filter(f =>
        f.name.toLowerCase().includes(q) || (f.desc && f.desc.toLowerCase().includes(q))
      )
    }))
    .filter(cat => cat.feeds.length > 0)
})

const subscribeOne = async (feed) => {
  if (subscribingFeeds.value.has(feed.url) || isSubscribed(feed.url)) return
  subscribingFeeds.value.add(feed.url)
  try {
    await feedStore.createFeed({ feed_name: feed.name, feed_url: feed.url })
    showToast({ message: t('feeds.addSuccess'), icon: 'success' })
  } catch {
    showToast({ message: t('feeds.addFailed'), icon: 'fail' })
  } finally {
    subscribingFeeds.value.delete(feed.url)
  }
}
</script>

<template>
  <div class="desktop-discover">
    <header class="discover-header">
      <h1 class="discover-title">{{ $t('feeds.discoverTitle') }}</h1>
      <div class="discover-actions">
        <input v-model="searchQuery" class="discover-search" :placeholder="$t('desktop.searchFeeds')" />
        <button class="btn primary" @click="showAddPopup = true">{{ $t('desktop.addFeed') }}</button>
      </div>
    </header>

    <section v-for="cat in filteredCategories" :key="getCategoryLabel(cat)" class="discover-category">
      <h2 class="category-title">{{ getCategoryLabel(cat) }}</h2>
      <div class="category-grid">
        <div v-for="feed in cat.feeds" :key="feed.url" class="feed-card">
          <img class="feed-favicon" :src="getFaviconUrl(feed.url)" alt="" referrerpolicy="no-referrer" />
          <div class="feed-info">
            <div class="feed-name">{{ feed.name }}</div>
            <div class="feed-desc">{{ feed.desc }}</div>
          </div>
          <button
            class="btn small"
            :disabled="isSubscribed(feed.url) || subscribingFeeds.has(feed.url)"
            @click="subscribeOne(feed)"
          >
            {{ isSubscribed(feed.url) ? '✓' : $t('desktop.addFeed') }}
          </button>
        </div>
      </div>
    </section>

    <AddFeedPopup v-if="showAddPopup" v-model:show="showAddPopup" @added="feedStore.fetchFeeds(true)" />
  </div>
</template>

<style scoped>
.desktop-discover {
  height: 100vh; overflow-y: auto; padding: 40px 48px; background: var(--readaria-paper);
}
.discover-header {
  display: flex; align-items: center; justify-content: space-between;
  gap: 16px; margin-bottom: 28px; flex-wrap: wrap;
}
.discover-title { font-family: var(--reading-serif); font-size: 26px; color: var(--readaria-ink); }
.discover-actions { display: flex; gap: 10px; }
.discover-search {
  padding: 8px 14px; border: 1px solid var(--readaria-border); border-radius: 8px;
  background: var(--readaria-surface); font-size: 13px; min-width: 220px;
}
.btn {
  padding: 8px 16px; border: 1px solid var(--readaria-border); border-radius: 8px;
  background: var(--readaria-surface); font-size: 13px; color: var(--readaria-ink); cursor: pointer;
}
.btn.primary { background: var(--readaria-navy); border-color: var(--readaria-navy); color: var(--readaria-paper); }
.btn.small { padding: 6px 14px; font-size: 12px; }
.btn:disabled { opacity: 0.5; cursor: default; }
.discover-category { margin-bottom: 28px; }
.category-title {
  font-size: 14px; font-weight: 600; color: var(--readaria-muted); margin-bottom: 12px;
}
.category-grid {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 12px;
}
.feed-card {
  display: flex; align-items: center; gap: 12px;
  padding: 14px 16px; background: var(--readaria-surface);
  border: 1px solid var(--readaria-border); border-radius: 12px;
}
.feed-favicon { width: 28px; height: 28px; border-radius: 6px; flex-shrink: 0; }
.feed-info { flex: 1; min-width: 0; }
.feed-name { font-size: 14px; font-weight: 600; color: var(--readaria-ink); }
.feed-desc {
  font-size: 12px; color: var(--readaria-muted);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
</style>
