<script setup>
defineOptions({ name: 'ShortcutHelpOverlay' })
defineEmits(['close'])
</script>

<template>
  <div class="shortcut-overlay" @click.self="$emit('close')">
    <div class="shortcut-card">
      <h3>{{ $t('desktop.shortcutsTitle') }}</h3>
      <div class="shortcut-row"><span class="keys"><kbd>j</kbd><kbd>k</kbd> / <kbd>↓</kbd><kbd>↑</kbd></span><span>{{ $t('desktop.shortcutNavigate') }}</span></div>
      <div class="shortcut-row"><span class="keys"><kbd>Enter</kbd></span><span>{{ $t('desktop.shortcutOpen') }}</span></div>
      <div class="shortcut-row"><span class="keys"><kbd>s</kbd></span><span>{{ $t('desktop.shortcutSave') }}</span></div>
      <div class="shortcut-row"><span class="keys"><kbd>1</kbd><kbd>2</kbd><kbd>3</kbd></span><span>{{ $t('desktop.shortcutSections') }}</span></div>
      <div class="shortcut-row"><span class="keys"><kbd>f</kbd></span><span>{{ $t('desktop.shortcutImmersive') }}</span></div>
      <div class="shortcut-row"><span class="keys"><kbd>Esc</kbd></span><span>{{ $t('desktop.shortcutExit') }}</span></div>
      <div class="shortcut-row"><span class="keys"><kbd>?</kbd></span><span>{{ $t('desktop.shortcutHelp') }}</span></div>
    </div>
  </div>
</template>

<style scoped>
.shortcut-overlay {
  position: fixed; inset: 0; background: rgba(23, 33, 48, 0.35);
  display: flex; align-items: center; justify-content: center; z-index: 2000;
}
.shortcut-card {
  background: var(--readaria-surface); border-radius: 16px; padding: 24px 28px;
  min-width: 340px; box-shadow: 0 24px 60px rgba(23, 33, 48, 0.25);
}
.shortcut-card h3 { font-family: var(--reading-serif); margin-bottom: 16px; }
.shortcut-row {
  display: flex; align-items: center; gap: 14px; padding: 8px 0;
  font-size: 14px; color: var(--readaria-ink);
}
.keys { display: inline-flex; gap: 4px; min-width: 110px; }
kbd {
  background: var(--readaria-paper); border: 1px solid var(--readaria-border);
  border-bottom-width: 2px; border-radius: 6px; padding: 2px 8px;
  font-family: inherit; font-size: 12px;
}
</style>
