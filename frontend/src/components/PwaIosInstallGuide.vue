<template>
  <van-popup
    v-model:show="show"
    round
    position="bottom"
    :style="{ maxHeight: '55%' }"
    class="pwa-ios-guide-popup"
  >
    <div class="pwa-ios-guide">
      <div class="pwa-ios-guide-header">
        <img src="/pwa-192x192.png" class="pwa-ios-guide-icon" alt="Readaria" />
        <div class="pwa-ios-guide-title">{{ $t('pwa.iosGuideTitle') }}</div>
        <button class="pwa-ios-guide-close" @click="close">
          <van-icon name="cross" />
        </button>
      </div>
      <div class="pwa-ios-guide-steps">
        <div class="pwa-ios-step">
          <div class="pwa-ios-step-number">1</div>
          <div class="pwa-ios-step-content">
            <div class="pwa-ios-step-text">{{ $t('pwa.iosGuideStep1') }}</div>
            <div class="pwa-ios-step-icon">
              <van-icon name="share-o" size="22" />
            </div>
          </div>
        </div>
        <div class="pwa-ios-step-divider"></div>
        <div class="pwa-ios-step">
          <div class="pwa-ios-step-number">2</div>
          <div class="pwa-ios-step-content">
            <div class="pwa-ios-step-text">{{ $t('pwa.iosGuideStep2') }}</div>
            <div class="pwa-ios-step-icon">
              <van-icon name="plus" size="22" />
            </div>
          </div>
        </div>
      </div>
      <van-button
        round
        block
        type="primary"
        class="pwa-ios-guide-done"
        @click="close"
      >
        {{ $t('pwa.iosGuideDone') }}
      </van-button>
    </div>
  </van-popup>
</template>

<script setup>
import { computed } from 'vue'
import { usePwaStore } from '@/stores/pwaStore'

const pwaStore = usePwaStore()

const show = computed({
  get: () => pwaStore.showIosGuide,
  set: (value) => {
    if (!value) pwaStore.dismissIosGuide()
  },
})

const close = () => {
  pwaStore.dismissIosGuide()
}
</script>

<style scoped>
.pwa-ios-guide-popup :deep(.van-popup) {
  background: var(--van-background-2, #fff);
}

.pwa-ios-guide {
  padding: 20px 24px 28px;
}

.pwa-ios-guide-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 24px;
  padding-bottom: 16px;
  border-bottom: 1px solid var(--van-border-color, #ebedf0);
}

.pwa-ios-guide-icon {
  width: 40px;
  height: 40px;
  border-radius: 9px;
}

.pwa-ios-guide-title {
  flex: 1;
  font-size: 18px;
  font-weight: 600;
  color: var(--van-text-color, #323233);
}

.pwa-ios-guide-close {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  border: none;
  background: var(--van-gray-2, #f2f3f5);
  color: var(--van-gray-6, #969799);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
}

.pwa-ios-guide-steps {
  margin-bottom: 24px;
}

.pwa-ios-step {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 12px 0;
}

.pwa-ios-step-number {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: var(--readaria-navy);
  color: white;
  font-size: 14px;
  font-weight: 600;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.pwa-ios-step-content {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.pwa-ios-step-text {
  font-size: 15px;
  color: var(--van-text-color, #323233);
  line-height: 1.4;
}

.pwa-ios-step-icon {
  color: var(--readaria-navy);
  flex-shrink: 0;
}

.pwa-ios-step-divider {
  margin-left: 42px;
  height: 1px;
  background: var(--van-border-color, #ebedf0);
}

.pwa-ios-guide-done {
  font-weight: 600;
}

:deep(.pwa-ios-guide-done.van-button--primary) {
  background: var(--readaria-navy);
  border-color: var(--readaria-navy);
}
</style>
