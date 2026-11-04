<script setup>
defineOptions({ name: 'DesktopSidebar' })
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useUserStore } from '@/stores/userStore'
import { useFeedStore } from '@/stores/feedStore'
import { useDesktopArticleStore } from '@/stores/desktopArticleStore'
import { useBreakpoint } from '@/composables/useBreakpoint'
import { isTypingTarget } from '@/utils/keyboard'
import { getFaviconUrl } from '@/config/recommendedFeeds'
import ShortcutHelpOverlay from './ShortcutHelpOverlay.vue'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()
const feedStore = useFeedStore()
const desktopArticleStore = useDesktopArticleStore()
const { isDesktop } = useBreakpoint()
const helpVisible = ref(false)

const sections = [
  { key: 'feeds', labelKey: 'desktop.navFeeds', routeName: 'feed', icon: '📖' },
  { key: 'saved', labelKey: 'desktop.navSaved', routeName: 'saved', icon: '🔖' },
  { key: 'manage', labelKey: 'desktop.navManage', routeName: 'feed-manage', icon: '⚙️' }
]

const activeSection = computed(() => {
  if (['feed', 'article-detail', 'feed-discover'].includes(route.name)) return 'feeds'
  if (route.name === 'saved') return 'saved'
  if (route.name === 'feed-manage') return 'manage'
  return null
})

const go = (name, ev) => {
  // 鼠标点击后主动失焦，避免焦点驻留在按钮上拦截后续快捷键/回车
  ev?.currentTarget?.blur()
  if (route.name !== name) router.push({ name })
}

const onLogout = async (ev) => {
  ev?.currentTarget?.blur()
  await userStore.logout()
  router.replace({ name: 'login' })
}

// 侧栏源筛选：阅读/文章页就地筛选中栏；其他页面先回 /feed 再筛选
const onSelectFeed = async (feedId, ev) => {
  ev?.currentTarget?.blur()
  if (!['feed', 'article-detail'].includes(route.name)) {
    await router.push({ name: 'feed' })
  }
  // UI interactions should not leak a rejected refresh into the global error handler.
  await desktopArticleStore.selectFeed(feedId).catch(() => {}) // feedId=null 即全部来源
}

// SELECT 聚焦时方向键属于下拉框本身；BUTTON 不屏蔽——靠点击后 blur 避免回车双触发
const onKeydown = (e) => {
  if (!isDesktop.value || e.metaKey || e.ctrlKey || e.altKey) return
  if (e.key === 'Escape' && helpVisible.value) {
    e.preventDefault()
    helpVisible.value = false
    return
  }
  if (isTypingTarget(e.target)) return
  if (e.key === '1') go('feed')
  else if (e.key === '2') go('saved')
  else if (e.key === '3') go('feed-manage')
  else if (e.key === '?') helpVisible.value = !helpVisible.value
}

onMounted(() => {
  window.addEventListener('keydown', onKeydown)
  // 侧栏是桌面端源筛选的唯一入口，任何页面落地都要保证源列表可用（feedStore 有缓存，开销低）
  if (feedStore.feeds.length === 0) {
    feedStore.fetchFeeds().catch(() => {})
  }
})
onUnmounted(() => window.removeEventListener('keydown', onKeydown))
</script>

<template>
  <aside class="desktop-sidebar">
    <div class="sidebar-brand">Readaria</div>
    <nav class="sidebar-nav">
      <button
        v-for="s in sections"
        :key="s.key"
        class="sidebar-item"
        :class="{ active: activeSection === s.key }"
        @click="go(s.routeName, $event)"
      >
        <span class="sidebar-icon">{{ s.icon }}</span>
        <span>{{ $t(s.labelKey) }}</span>
      </button>
    </nav>
    <div class="sidebar-feeds">
      <div class="feeds-header">{{ $t('desktop.feeds') }}</div>
      <button
        class="sidebar-item feed-item"
        :class="{ active: desktopArticleStore.selectedFeedId === null }"
        @click="onSelectFeed(null, $event)"
      >
        <span class="feed-favicon feed-all-icon">◎</span>
        <span class="feed-name">{{ $t('desktop.allFeeds') }}</span>
      </button>
      <button
        v-for="feed in feedStore.feeds"
        :key="feed.id"
        class="sidebar-item feed-item"
        :class="{ active: desktopArticleStore.selectedFeedId === feed.id }"
        @click="onSelectFeed(feed.id, $event)"
      >
        <img class="feed-favicon" :src="getFaviconUrl(feed.feed_url)" alt="" referrerpolicy="no-referrer" />
        <span class="feed-name">{{ feed.feed_name }}</span>
      </button>
    </div>
    <div class="sidebar-footer">
      <div class="sidebar-user" :title="userStore.user?.email || ''">
        {{ userStore.user?.username || userStore.user?.email || '—' }}
      </div>
      <button class="sidebar-item" @click="onLogout($event)">{{ $t('desktop.logout') }}</button>
    </div>
    <ShortcutHelpOverlay v-if="helpVisible" @close="helpVisible = false" />
  </aside>
</template>

<style scoped>
.desktop-sidebar {
  width: var(--desktop-sidebar-width);
  flex-shrink: 0;
  height: 100vh;
  display: flex;
  flex-direction: column;
  background: var(--readaria-stone);
  padding: 20px 12px 12px;
}
.sidebar-brand {
  font-family: var(--reading-serif);
  font-size: 20px;
  font-weight: 700;
  color: var(--readaria-ink);
  padding: 0 10px 20px;
}
.sidebar-nav { display: flex; flex-direction: column; gap: 4px; }
.sidebar-feeds {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  margin-top: 16px;
  border-top: 1px solid var(--readaria-border);
  padding-top: 12px;
  display: flex; flex-direction: column; gap: 2px;
}
.feeds-header {
  padding: 0 10px 6px;
  font-size: 11px; font-weight: 600; letter-spacing: 0.08em;
  color: var(--readaria-muted); text-transform: uppercase;
}
.feed-item { padding: 7px 10px; font-size: 13px; }
.feed-favicon { width: 18px; height: 18px; border-radius: 4px; flex-shrink: 0; }
.feed-all-icon {
  display: inline-flex; align-items: center; justify-content: center;
  font-size: 13px; color: var(--readaria-accent);
}
.feed-name {
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.sidebar-item {
  display: flex; align-items: center; gap: 10px;
  width: 100%; padding: 10px; border: 0; border-radius: 10px;
  background: transparent; font-size: 14px; color: var(--readaria-ink);
  text-align: left; cursor: pointer;
}
.sidebar-item:hover { background: var(--readaria-accent-soft); }
.sidebar-item.active {
  background: var(--readaria-accent-soft);
  color: var(--readaria-accent);
  font-weight: 600;
}
.sidebar-icon { width: 20px; text-align: center; }
.sidebar-footer {
  border-top: 1px solid var(--readaria-border);
  padding-top: 10px;
  display: flex; flex-direction: column; gap: 4px;
}
.sidebar-user {
  padding: 6px 10px; font-size: 13px; color: var(--readaria-muted);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
</style>
