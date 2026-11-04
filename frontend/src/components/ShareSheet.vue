<script setup>
import { computed } from 'vue'
import { showToast } from 'vant'
import { useI18n } from 'vue-i18n'

const props = defineProps({
  show: { type: Boolean, default: false },
  title: { type: String, default: '' },
  url: { type: String, default: '' },
  type: { type: String, default: 'article' }, // 'article' | 'podcast'
  description: { type: String, default: '' },
  stories: { type: Array, default: () => [] }
})

const emit = defineEmits(['update:show'])

const { t } = useI18n()

const visible = computed({
  get: () => props.show,
  set: (val) => emit('update:show', val)
})

const shareText = computed(() => {
  if (props.type === 'podcast') {
    const title = props.title || t('sharePodcast.dailyDigest')
    const tagline = t('share.podcastTagline', 'AI-curated news briefing')
    return `${title}｜${tagline}`
  }
  return t('share.articleText', 'Check out this article on Readaria')
})

const actions = computed(() => [
  { name: t('share.copyLink', 'Copy Link'), icon: 'link-o', key: 'copy' },
  { name: t('share.systemShare', 'Share...'), icon: 'share-o', key: 'share' }
])

const onSelect = (action) => {
  if (action.key === 'copy') {
    copyLink()
  } else if (action.key === 'share') {
    systemShare()
  }
}

const copyLink = async () => {
  if (!props.url) return
  try {
    await navigator.clipboard.writeText(props.url)
    showToast(t('share.copySuccess', 'Link copied!'))
  } catch {
    showToast(t('share.copyFailed', 'Copy failed'))
  }
  visible.value = false
}

const systemShare = async () => {
  if (!props.url) return
  if (navigator.share) {
    try {
      await navigator.share({
        title: props.title,
        text: shareText.value,
        url: props.url
      })
    } catch (err) {
      if (err.name !== 'AbortError') {
        copyLink()
      }
    }
  } else {
    copyLink()
  }
  visible.value = false
}
</script>

<template>
  <van-action-sheet
    v-model:show="visible"
    :actions="actions"
    :cancel-text="$t('common.cancel', 'Cancel')"
    close-on-click-action
    @select="onSelect"
  >
    <template #description>
      <div class="share-preview">
        <p class="share-title">{{ title }}</p>
        <p class="share-url">{{ url }}</p>
      </div>
    </template>
  </van-action-sheet>
</template>

<style scoped>
.share-preview {
  padding: 16px 20px;
  text-align: center;
  border-bottom: 1px solid var(--readaria-border);
}
.share-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--readaria-ink);
  margin: 0 0 6px 0;
  line-height: 1.4;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.share-url {
  font-size: 12px;
  color: var(--readaria-muted);
  margin: 0;
  word-break: break-all;
  line-height: 1.4;
  display: -webkit-box;
  -webkit-line-clamp: 1;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
</style>
