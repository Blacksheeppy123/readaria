<script setup>
defineOptions({ name: 'DesktopFeedManageView' })
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { showToast, showLoadingToast, closeToast, showConfirmDialog } from 'vant'
import { useFeedStore } from '@/stores/feedStore'
import { getFaviconUrl } from '@/config/recommendedFeeds'
import AddFeedPopup from '@/components/AddFeedPopup.vue'

const { t } = useI18n()
const router = useRouter()
const feedStore = useFeedStore()
const searchQuery = ref('')
const showAddPopup = ref(false)

let refreshTimer = null

onMounted(async () => {
  try { await feedStore.fetchFeeds() } catch { showToast(t('common.loadFailed')) }
  const first = await feedStore.fetchRefreshStatus()
  if (first !== null) {
    refreshTimer = setInterval(() => feedStore.fetchRefreshStatus(), 8000)
  }
})

onUnmounted(() => {
  if (refreshTimer) { clearInterval(refreshTimer); refreshTimer = null }
})

const filteredFeeds = computed(() => {
  if (!searchQuery.value.trim()) return feedStore.feeds
  const q = searchQuery.value.toLowerCase()
  return feedStore.feeds.filter(f =>
    f.feed_name.toLowerCase().includes(q) || f.feed_url.toLowerCase().includes(q)
  )
})

const lastSync = (feedId) => {
  const st = feedStore.refreshStatus[feedId]
  if (!st?.last_success_at) return '—'
  const d = new Date(st.last_success_at)
  return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

const statusText = (feedId) => {
  const st = feedStore.refreshStatus[feedId]
  if (st?.status === 'running') return t('feeds.statusRunning')
  if (st?.status === 'failed') return t('feeds.statusFailed')
  return ''
}

const onRefreshFeed = async (feed) => {
  try {
    await feedStore.refreshFeed(feed.id)
    showToast({ message: t('feeds.refreshSuccess'), icon: 'success' })
  } catch { showToast({ message: t('feeds.refreshFailed'), icon: 'fail' }) }
}

const onRefreshAll = async () => {
  const toast = showLoadingToast({ message: t('feeds.refreshing'), forbidClick: true, duration: 0 })
  try {
    await feedStore.refreshAll()
    closeToast()
    showToast({ message: t('feeds.refreshSuccess'), icon: 'success' })
  } catch {
    closeToast()
    showToast({ message: t('feeds.refreshFailed'), icon: 'fail' })
  }
}

const onDelete = async (feed) => {
  try {
    await showConfirmDialog({
      title: t('feeds.deleteConfirmTitle'),
      message: t('feeds.deleteConfirmMessage', { name: feed.feed_name })
    })
    await feedStore.removeFeed(feed.id)
    showToast({ message: t('feeds.deleteSuccess'), icon: 'success' })
  } catch (e) {
    if (e !== 'cancel') showToast({ message: t('feeds.deleteFailed'), icon: 'fail' })
  }
}

const goDiscover = () => router.push({ name: 'feed-discover' })
const viewFeedArticles = (feed) => router.push({ name: 'feed', query: { source: feed.id } })
</script>

<template>
  <div class="desktop-manage">
    <header class="manage-header">
      <h1 class="manage-title">{{ $t('feeds.title') }}</h1>
      <div class="manage-actions">
        <input v-model="searchQuery" class="manage-search" :placeholder="$t('desktop.searchFeeds')" />
        <button class="btn" @click="goDiscover">{{ $t('feeds.discoverTitle') }}</button>
        <button class="btn" @click="onRefreshAll">{{ $t('desktop.refreshAll') }}</button>
        <button class="btn primary" @click="showAddPopup = true">{{ $t('desktop.addFeed') }}</button>
      </div>
    </header>

    <div v-if="feedStore.feeds.length === 0" class="manage-empty">{{ $t('desktop.emptyFeeds') }}</div>

    <table v-else class="manage-table">
      <thead>
        <tr>
          <th></th>
          <th>{{ $t('feeds.title') }}</th>
          <th>URL</th>
          <th>{{ $t('desktop.lastSync') }}</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="feed in filteredFeeds" :key="feed.id">
          <td class="cell-favicon">
            <img :src="getFaviconUrl(feed.feed_url)" alt="" referrerpolicy="no-referrer" />
          </td>
          <td class="cell-name" @click="viewFeedArticles(feed)">{{ feed.feed_name }}</td>
          <td class="cell-url">{{ feed.feed_url }}</td>
          <td class="cell-sync">
            {{ lastSync(feed.id) }}
            <span v-if="statusText(feed.id)" class="cell-status">{{ statusText(feed.id) }}</span>
          </td>
          <td class="cell-ops">
            <button class="btn small" @click="onRefreshFeed(feed)">{{ $t('desktop.refresh') }}</button>
            <button class="btn small danger" @click="onDelete(feed)">{{ $t('desktop.delete') }}</button>
          </td>
        </tr>
      </tbody>
    </table>

    <AddFeedPopup v-if="showAddPopup" v-model:show="showAddPopup" @added="feedStore.fetchFeeds(true)" />
  </div>
</template>

<style scoped>
.desktop-manage {
  height: 100vh; overflow-y: auto;
  padding: 40px 48px; background: var(--readaria-paper);
}
.manage-header {
  display: flex; align-items: center; justify-content: space-between;
  gap: 16px; margin-bottom: 24px; flex-wrap: wrap;
}
.manage-title { font-family: var(--reading-serif); font-size: 26px; color: var(--readaria-ink); }
.manage-actions { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
.manage-search {
  padding: 8px 14px; border: 1px solid var(--readaria-border); border-radius: 8px;
  background: var(--readaria-surface); font-size: 13px; min-width: 200px;
}
.btn {
  padding: 8px 16px; border: 1px solid var(--readaria-border); border-radius: 8px;
  background: var(--readaria-surface); font-size: 13px; color: var(--readaria-ink); cursor: pointer;
}
.btn:hover { border-color: var(--readaria-accent); }
.btn.primary {
  background: var(--readaria-navy); border-color: var(--readaria-navy); color: var(--readaria-paper);
}
.btn.small { padding: 5px 12px; font-size: 12px; }
.btn.danger { color: #b5443a; }
.manage-empty { padding: 80px 0; text-align: center; color: var(--readaria-muted); }
.manage-table {
  width: 100%; border-collapse: collapse;
  background: var(--readaria-surface); border-radius: 12px; overflow: hidden;
  border: 1px solid var(--readaria-border);
}
.manage-table th {
  text-align: left; font-size: 12px; color: var(--readaria-muted);
  padding: 12px 16px; border-bottom: 1px solid var(--readaria-border); font-weight: 500;
}
.manage-table td {
  padding: 12px 16px; border-bottom: 1px solid var(--readaria-border);
  font-size: 14px; color: var(--readaria-ink); vertical-align: middle;
}
.manage-table tr:last-child td { border-bottom: 0; }
.cell-favicon img { width: 20px; height: 20px; border-radius: 4px; display: block; }
.cell-name { font-weight: 600; cursor: pointer; }
.cell-name:hover { color: var(--readaria-accent); }
.cell-url {
  max-width: 280px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  color: var(--readaria-muted); font-size: 12px;
}
.cell-sync { font-size: 12px; color: var(--readaria-muted); white-space: nowrap; }
.cell-status { margin-left: 6px; color: var(--readaria-accent); }
.cell-ops { white-space: nowrap; display: flex; gap: 8px; }
</style>
