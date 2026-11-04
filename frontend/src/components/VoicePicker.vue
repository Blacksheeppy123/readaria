<template>
  <van-popup
    :show="show"
    position="bottom"
    round
    safe-area-inset-bottom
    teleport="body"
    @update:show="$emit('update:show', $event)"
    @closed="stopPreview"
  >
    <div class="voice-picker">
      <div class="voice-picker__header">
        <span class="voice-picker__title">{{ title }}</span>
        <van-icon name="cross" class="voice-picker__close" @click="$emit('update:show', false)" />
      </div>
      <div class="voice-picker__list">
        <div
          v-for="option in options"
          :key="optionKey(option)"
          class="voice-option"
          :class="{ 'voice-option--active': isSelected(option) }"
          @click="select(option)"
        >
          <div class="voice-option__info">
            <div class="voice-option__name">
              {{ option.name }}
              <van-tag v-if="option.id === null" type="primary" plain>{{ t('me.voiceDefaultTag') }}</van-tag>
            </div>
            <div class="voice-option__desc">{{ option.description }}</div>
          </div>
          <van-icon
            v-if="isSelected(option)"
            name="success"
            class="voice-option__check"
          />
          <van-button
            class="voice-option__preview"
            size="small"
            round
            plain
            type="primary"
            :icon="previewingKey === optionKey(option) ? 'stop' : 'play'"
            :loading="previewLoadingKey === optionKey(option)"
            @click.stop="togglePreview(option)"
          >
            {{ t('me.voicePreview') }}
          </van-button>
        </div>
      </div>
    </div>
  </van-popup>
</template>

<script setup>
import { computed, ref, onBeforeUnmount } from 'vue'
import { useI18n } from 'vue-i18n'
import { showToast } from 'vant'
import { previewTtsVoice } from '@/api/tts'

const props = defineProps({
  show: { type: Boolean, default: false },
  title: { type: String, default: '' },
  lang: { type: String, required: true }, // 'zh' | 'en'
  voices: { type: Array, default: () => [] }, // 目录中该语言的音色数组
  modelValue: { type: String, default: null } // 当前选中音色 id，null = 默认
})

const emit = defineEmits(['update:show', 'select'])

const { t } = useI18n()

// 「默认」行 + 目录音色行
const options = computed(() => {
  const defaultVoice = props.voices.find(v => v.is_default)
  const defaultOption = {
    id: null,
    name: t('me.voiceDefault'),
    description: defaultVoice
      ? `${defaultVoice.name} · ${defaultVoice.description}`
      : '',
    sample_text: defaultVoice?.sample_text || props.voices[0]?.sample_text || ''
  }
  return [defaultOption, ...props.voices]
})

const optionKey = (option) => option.id || '__default__'
const isSelected = (option) => (option.id || null) === (props.modelValue || null)

const select = (option) => {
  emit('select', option.id || null)
}

// ---- 试听 ----
const previewingKey = ref(null)
const previewLoadingKey = ref(null)
let audioEl = null
let audioUrl = null
// 单调递增序号：stopPreview 递增使进行中的试听请求返回时失效（修复关弹层后仍发声的竞态）
let previewSeq = 0

function stopPreview() {
  previewSeq++
  if (audioEl) {
    try { audioEl.pause() } catch (_) { /* noop */ }
    audioEl = null
  }
  if (audioUrl) {
    URL.revokeObjectURL(audioUrl)
    audioUrl = null
  }
  previewingKey.value = null
  previewLoadingKey.value = null
}

async function togglePreview(option) {
  const key = optionKey(option)
  if (previewingKey.value === key) {
    stopPreview()
    return
  }
  stopPreview()
  const seq = previewSeq
  previewLoadingKey.value = key
  try {
    // 试听走专用端点：固定示例文本（永久缓存）、不消耗用户 TTS 配额
    const blob = await previewTtsVoice({
      voice: option.id || 'default', // 默认行传 'default'，后端解析为该语言默认音色
      lang: props.lang
    })
    if (seq !== previewSeq) return // 弹层已关闭或已被新试听取代
    audioUrl = URL.createObjectURL(blob)
    audioEl = new Audio(audioUrl)
    audioEl.onended = stopPreview
    audioEl.onerror = stopPreview
    previewingKey.value = key
    await audioEl.play()
  } catch (e) {
    if (seq !== previewSeq) return
    console.error('[VoicePicker] preview failed:', e)
    showToast(t('me.voicePreviewFailed'))
  } finally {
    if (seq === previewSeq) {
      previewLoadingKey.value = null
    }
  }
}

onBeforeUnmount(stopPreview)
</script>

<style scoped>
.voice-picker {
  padding: 16px 0 8px;
  max-height: 70vh;
  display: flex;
  flex-direction: column;
}

.voice-picker__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 16px 12px;
  border-bottom: 1px solid var(--van-border-color);
}

.voice-picker__title {
  font-size: 16px;
  font-weight: 600;
}

.voice-picker__close {
  font-size: 20px;
  color: var(--van-gray-6);
}

.voice-picker__list {
  overflow-y: auto;
}

.voice-option {
  display: flex;
  align-items: center;
  padding: 12px 16px;
  cursor: pointer;
}

.voice-option:active {
  background: var(--van-active-color);
}

.voice-option--active .voice-option__name {
  color: var(--van-primary-color);
  font-weight: 600;
}

.voice-option__info {
  flex: 1;
  min-width: 0;
}

.voice-option__name {
  font-size: 15px;
  display: flex;
  align-items: center;
  gap: 6px;
}

.voice-option__desc {
  font-size: 12px;
  color: var(--van-gray-6);
  margin-top: 2px;
}

.voice-option__check {
  color: var(--van-primary-color);
  font-size: 18px;
  margin: 0 8px;
}

.voice-option__preview {
  flex-shrink: 0;
}
</style>
