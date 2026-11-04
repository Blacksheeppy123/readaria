# Collapsible Mini-Pill Player Design Spec

## Overview

Replace the current fixed floating player bar with a **three-state collapsible mini-pill player** that can be manually expanded, collapsed to a thin indicator line, or hidden (stopped). This solves the occlusion problem where the current floating bar blocks sorting options and bottom text while keeping the audio controls always accessible.

## Problem Statement

- The current `UnifiedFloatingPlayer` is a fixed bar at the bottom of the screen
- It permanently occludes ~60px of content at the bottom
- Users cannot collapse it without stopping playback entirely (clicking ×)
- After closing, re-entering the player requires navigating to Listen page first
- This is especially problematic on Feed/Listen pages where bottom content is frequently interacted with

## Design Principles

1. **Read-first, audio-second**: Audio is an accompaniment feature; the UI should get out of the way when the user is focused on reading
2. **One-gesture access**: The player should always be reachable within a single swipe/tap, never more than two
3. **Zero learning cost**: The collapsed state should be visually discoverable; the interaction pattern should feel native to mobile
4. **State persistence**: Collapse/expand is a UI preference within a session, not a playback action

## State Machine

Three mutually exclusive states:

| State | Visual | Behavior |
|---|---|---|
| **Expanded** | Full mini bar (~52px height), title, play/pause, progress, × | Default when playback starts; can be swiped down to collapse |
| **Collapsed** | Thin indicator line (~5px height, 60% width, centered) | Audio continues; tap or swipe up to expand; no × button |
| **Hidden** | Nothing | Playback stopped or finished; re-enter from Listen page or start new playback |

```
Expanded  ←—— swipe up / tap ——  Collapsed  ←—— playback starts ——  Hidden
   │                               │                            ↑
   └── swipe down ─——→            └── playback ended / tap × ──┘
   └── tap content area ──→ PlayerView
```

### Route-Specific Visibility Matrix

The collapsible player follows the **same route visibility rules** as the current `UnifiedFloatingPlayer`. It is **not** a global always-on component.

| Route | Player Visible? | Collapsed Indicator Visible? | Rationale |
|---|---|---|---|
| `/feed`, `/listen`, `/me` (tabbar routes) | ✅ Yes | ✅ Yes | Primary routes where the player provides value |
| `/player` (full-screen player) | ❌ No | ❌ No | Full-screen player already occupies the screen; no floating bar |
| `/article-detail/:id` | ❌ No | ❌ No | Article detail has its own in-page `mini-player-bar` (lines 106-109 of `ArticleDetail.vue`); floating player would duplicate affordances |
| `/podcasts/:id` | ✅ Yes | ✅ Yes | Podcast detail page shows the player for quick access |
| Other routes | Follow `route.meta.hideTabbar` | Follow `route.meta.hideTabbar` | Default to visible unless explicitly hidden |

**Important**: The collapsed indicator's `bottom` positioning only differs when `route.meta.hideTabbar` is true AND the player is visible. Currently, `/player` and `article-detail` are the only `hideTabbar`-equivalent routes, and both hide the player entirely, so the `no-tabbar` positioning rule in practice only affects future routes.

### State Transition Rules

1. **Playback start** (`playArticle`, `playFromList`, podcast `play`) → always enters `Expanded`; `collapsed` resets to `false`
2. **Swipe down on Expanded** (threshold ≥ 40px, vertical > horizontal) → `Collapsed`
3. **Swipe up on Collapsed** (threshold ≥ 30px) or **tap Collapsed** → `Expanded`
4. **Tap Expanded content area** (not play/pause/×) → `PlayerView` (player hidden locally on that route only, playback continues)
5. **Tap × on Expanded** → stop playback → `Hidden`
6. **Playback naturally ends** → `Hidden`
7. **Route change to `/player` or `article-detail`** → player hides (via existing `isVisible` logic), but state is NOT reset; returning to a tabbar route restores the previous Expanded/Collapsed state

## Visual Design

### Expanded State

Identical to current `UnifiedFloatingPlayer` with these refinements:

- Height: `52px` (slightly reduced from current `60px` to be less intrusive)
- Position: `fixed`, above Tab Bar (`bottom: calc(56px + env(safe-area-inset-bottom, 0px))`)
- Border radius: `26px` (pill shape)
- Background: `rgba(255, 252, 248, 0.96)` with `backdrop-filter: blur(12px)`
- Box shadow: `0 8px 24px rgba(64, 45, 31, 0.12)`
- Left/right margin: `12px`
- Z-index: `1000`

Content layout (left to right):
1. Title text (ellipsis, flex: 1)
2. Play/pause icon (`pause-circle` / `play-circle`, 28px) or loading spinner
3. Progress bar (width 60px, height 2px)
4. × close icon (18px, right side)

### Collapsed State (Thin Indicator)

```
┌──────────────────────────────────────────┐
│                                          │
│        ━━━━━━━━━━━━━━━━━━━━━━━           │  ← 5px tall, 60% width,
│        ▲ pulsing glow animation          │     centered, pill radius
│                                          │     (color = content theme)
└──────────────────────────────────────────┘
         ↑ above Tab Bar (or safe area if no tabbar)
```

CSS specification:

```css
.collapsed-indicator {
  position: fixed;
  bottom: calc(56px + env(safe-area-inset-bottom, 0px));
  left: 20%;
  right: 20%;
  height: 5px;
  border-radius: 999px;
  background: var(--indicator-color); /* podcast: #9a674f, article: #c75b39 */
  opacity: 0.85;
  animation: pulse-flow 2s ease-in-out infinite;
  cursor: pointer;
  z-index: 1000;
}

@keyframes pulse-flow {
  0%, 100% { opacity: 0.55; box-shadow: 0 0 3px var(--indicator-color); }
  50% { opacity: 1; box-shadow: 0 0 10px var(--indicator-color); }
}

/* When audio is paused */
.collapsed-indicator.paused {
  animation: none;
  opacity: 0.4;
}
```

- **No-tabbar pages** (PlayerView, article-detail): `bottom: calc(8px + env(safe-area-inset-bottom, 0px))`
- **Theme color**: podcast uses `#9a674f`, article uses `#c75b39` — same as current theme mapping
- **Visual affordance**: On first-ever collapse, show a brief toast: "上滑展开 · 点击进全屏"

### Content Area Padding

The `.content` wrapper in `App.vue` must dynamically adjust `padding-bottom` based on player state:

| Player State | padding-bottom |
|---|---|
| Expanded | `calc(52px + 56px + env(safe-area-inset-bottom, 0px) + 8px)` |
| Collapsed | `calc(5px + 56px + env(safe-area-inset-bottom, 0px) + 4px)` |
| Hidden | `calc(56px + env(safe-area-inset-bottom, 0px) + 4px)` |

Transition: `padding-bottom 0.3s ease` for smooth resizing.

## Gesture Interaction

### Touch Handling (native, no library)

Use `touchstart`, `touchmove`, `touchend` on the player container.

```
touchstart:
  - record startX, startY, startTime
  - if state is Expanded: capture touch, prevent default on vertical drags
  - if state is Collapsed: capture touch

touchmove:
  - calculate deltaX, deltaY
  - if |deltaY| > |deltaX| and deltaY > 0 (swiping down) and state is Expanded:
    - apply translateY(deltaY) to player for direct manipulation feel
    - beyond threshold (40px), show "release to collapse" hint
  - if |deltaY| > |deltaX| and deltaY < 0 (swiping up) and state is Collapsed:
    - apply translateY(deltaY) to indicator for direct manipulation feel

touchend:
  - if state is Expanded and deltaY >= 40px:
    - transition to Collapsed
  - else if state is Expanded:
    - snap back to Expanded (spring animation)
  - if state is Collapsed and deltaY <= -30px:
    - transition to Expanded
  - else if state is Collapsed:
    - snap back to Collapsed (or interpret as tap → expand)
```

### Tap Handling

- **Collapsed indicator tapped** → expand to Expanded state (does NOT enter PlayerView)
- **Expanded content area tapped** (outside play/pause/×) → navigate to PlayerView
- **Expanded play/pause icon tapped** → toggle playback (stop propagation)
- **Expanded × icon tapped** → stop playback, hide player (stop propagation)

## Animation Specifications

### Expand → Collapse
- Player container `translateY(0)` → `translateY(calc(100% + 12px))` (slide down past bottom edge)
- Simultaneously, collapsed indicator fades in from `opacity: 0, scaleX(0)` → `opacity: 0.85, scaleX(1)`
- Duration: `300ms`
- Easing: `cubic-bezier(0.32, 0.72, 0, 1)` (iOS-style ease-out with slight overshoot)

### Collapse → Expand
- Collapsed indicator fades out: `opacity: 0.85, scaleX(1)` → `opacity: 0, scaleX(0)`
- Player container slides up from `translateY(100%)` → `translateY(0)`
- Duration: `300ms`
- Easing: `cubic-bezier(0.32, 0.72, 0, 1)`
- Small `scaleY(0.95 → 1.0)` on the bar for a subtle "pop" feel

### Snap-back (insufficient swipe)
- Return to original position with spring easing
- Duration: `200ms`
- Easing: `cubic-bezier(0.68, -0.3, 0.32, 1.3)` (spring overshoot)

## First-Time Onboarding

- **Trigger**: First time user swipes down to collapse (detected via `localStorage`)
- **Key**: `readaria_player_collapsed_hint_shown`
- **UI**: A small floating label above the collapsed indicator:
  - Text: "上滑展开 · 点击进全屏"
  - Style: `background: rgba(0,0,0,0.7); color: white; padding: 6px 12px; border-radius: 12px; font-size: 12px;`
  - Position: `bottom: calc(68px + env(safe-area-inset-bottom, 0px))`
  - Animation: fade in (200ms), hold 2.5s, fade out (300ms)

## Technical Architecture

### Collapse State Ownership

The `collapsed` state is **purely a UI concern** of the floating player and is kept **local to `UnifiedFloatingPlayer.vue`** as a `ref(false)` — it does NOT live in `playerStore` or `podcastPlayerStore`.

**Rationale**: The floating player is a shared surface for both article TTS (`playerStore`) and podcast playback (`podcastPlayerStore`). Keeping `collapsed` in either store would create coupling and leave the other playback type without a defined state owner. Since collapse/expand is about the *widget's visual state* (not playback behavior), local component state is the cleanest boundary.

**Reset rules** (via `watch` on store refs):
- `playerStore.currentArticle` changes → `collapsed = false` (new article playback starts expanded)
- `podcastPlayerStore.currentPodcast` changes → `collapsed = false` (new podcast playback starts expanded)
- Component unmount/remount → `collapsed` resets to `false` (acceptable; session-only state)

**NOT reset by**:
- `stop()` → player becomes Hidden anyway
- `restoreProgress()` → app boot leaves player in Hidden state; user must explicitly resume
- Route navigation within tabbar routes → collapsed state persists

### Files Changed

#### `UnifiedFloatingPlayer.vue` — Major refactor

The component becomes a three-state renderer:

```vue
<template>
  <Transition name="player-slide">
    <!-- Expanded state -->
    <div
      v-if="isExpanded"
      class="player-expanded"
      @touchstart="onTouchStart"
      @touchmove="onTouchMove"
      @touchend="onTouchEnd"
      @click="goToPlayer"
    >
      <!-- ... existing content ... -->
    </div>
  </Transition>

  <Transition name="indicator-fade">
    <!-- Collapsed state -->
    <div
      v-if="isCollapsed"
      class="player-collapsed"
      :class="{ paused: isPaused }"
      @touchstart="onTouchStart"
      @touchmove="onTouchMove"
      @touchend="onTouchEnd"
      @click="expandPlayer"
    >
      <div class="collapsed-line" />
    </div>
  </Transition>
</template>
```

#### `App.vue` changes

App.vue derives bottom padding from the **same visibility predicate** used by `UnifiedFloatingPlayer`, not just the collapse state. This avoids adding unnecessary whitespace on routes that hide the player.

```vue
<script setup>
// ... existing imports ...
import { usePlayerStore } from '@/stores/playerStore'
import { usePodcastPlayerStore } from '@/stores/podcastPlayerStore'

const playerStore = usePlayerStore()
const podcastPlayer = usePodcastPlayerStore()

const isPlayerVisibleOnRoute = computed(() => {
  // Mirrors UnifiedFloatingPlayer.vue isVisible logic
  const articleActive = playerStore.isPlaying || playerStore.isPaused || playerStore.isLoadingAudio || playerStore.isActivatingFallback
  const podcastActive = podcastPlayer.isPlaying || podcastPlayer.isPaused || podcastPlayer.isLoading

  if (route.path === '/player') return false
  if (route.name === 'article-detail') return false
  return articleActive || podcastActive
})

const playerOffsetClass = computed(() => {
  if (!isPlayerVisibleOnRoute.value) return 'player-hidden'
  // collapsed state communicated via custom property or class from UnifiedFloatingPlayer
  // Option A: emit('update:offset', ...) from child
  // Option B: use a lightweight shared ref
  return isCollapsed.value ? 'player-collapsed' : 'player-expanded'
})
</script>

<template>
  <div class="app-container">
    <div class="content" :class="playerOffsetClass">
      <keep-alive include="FeedView,ListenView">
        <router-view />
      </keep-alive>
    </div>

    <UnifiedFloatingPlayer @offset-change="onPlayerOffsetChange" />
    <!-- ... rest ... -->
  </div>
</template>
```

```css
.content {
  /* Base: only tabbar safe area */
  padding-bottom: calc(56px + env(safe-area-inset-bottom, 0px) + 4px);
  transition: padding-bottom 0.3s ease;
}

/* Player visible + Expanded */
.content.player-expanded {
  padding-bottom: calc(52px + 56px + env(safe-area-inset-bottom, 0px) + 8px);
}

/* Player visible + Collapsed */
.content.player-collapsed {
  padding-bottom: calc(5px + 56px + env(safe-area-inset-bottom, 0px) + 4px);
}

/* Player hidden on this route — no extra padding */
.content.player-hidden {
  padding-bottom: calc(56px + env(safe-area-inset-bottom, 0px) + 4px);
}
```

**Coordination with per-view padding**: Some views (e.g. `ListenView.vue:314`) already define their own `padding-bottom`. The global `.content` padding should be the *source of truth*, and per-view padding should be removed or aligned. The spec assumes `App.vue` owns the bottom offset, and views use `padding-bottom: 0` (relying on the parent `.content` scroll container).

### Files Modified

| File | Change Type | Description |
|---|---|---|
| `frontend/src/components/UnifiedFloatingPlayer.vue` | Major refactor | Add three-state rendering, local `collapsed` ref, touch gesture handling, CSS transitions, emit offset changes to parent |
| `frontend/src/App.vue` | Minor edit | Add dynamic padding-bottom derived from visibility predicate + emitted offset from child |
| `frontend/src/views/ListenView.vue` | Minor edit | Remove or align redundant `padding-bottom` with new global offset |
| `frontend/src/views/FeedView.vue` | Minor edit | Remove or align redundant `padding-bottom` with new global offset (if present) |

## Accessibility

- **Screen readers**: The collapsed indicator must have `aria-label="播放器已收起，上滑展开"` and `role="button"`
- **Focus management**: When expanding, focus should remain on the player (no focus trap needed since it's not a modal)
- **Reduced motion**: Respect `prefers-reduced-motion: reduce` — disable pulse animation and use instant transitions

## Testing Considerations

1. **Swipe threshold accuracy**: Test on both iOS Safari and Android Chrome — touch sensitivity varies
2. **Scroll conflict**: Ensure player swipe gestures don't interfere with page scroll when user is scrolling past the player
3. **Safe area handling**: Test on iPhone with Dynamic Island and devices with physical home buttons
4. **State persistence across navigation**: Collapsed state should persist when user navigates between Feed/Listen/Me
5. **Orientation change**: Player should remain correctly positioned after rotation
6. **Theme switching**: Ensure collapsed indicator color correctly follows podcast/article theme

## Lifecycle Rules (Explicit)

### `collapsed` State Lifecycle

| Event | `collapsed` Behavior | Rationale |
|---|---|---|
| **App cold start** | N/A (player starts Hidden) | `restoreProgress()` restores metadata only, not playback state |
| **User taps "Resume" in ListenView** | `false` (Expanded) | User explicitly chose to resume; show controls |
| **`playArticle()` called** | `false` (Expanded) | New playback should surface controls |
| **`playFromList()` called** | `false` (Expanded) | Same as above |
| **Podcast `play()` called** | `false` (Expanded) | Same as above |
| **`stop()` called** | N/A → Hidden | Player widget unmounts; state irrelevant |
| **Playback ends naturally** | N/A → Hidden | Same as above |
| **User swipes down** | `true` (Collapsed) | Manual user action |
| **Route change (tabbar ↔ tabbar)** | Preserved | Reading Feed then switching to Listen should keep collapsed state |
| **Route change to `/player`** | Preserved (but hidden) | Returning from PlayerView restores prior state |
| **Route change to `article-detail`** | Preserved (but hidden) | Returning from article restores prior state |

### Persistence

- **`collapsed` is memory-only**, NEVER written to `localStorage` or `sessionStorage`
- No cross-session memory; each app session starts fresh
- This is intentional: collapse is a per-session reading-mode preference, not a user setting

## Open Questions / Future Work

1. Should we auto-collapse after N seconds of inactivity (user not interacting with player)? → **Not in v1**, keep it manual
2. Desktop behavior? → Keep Expanded always (no collapse on desktop — mouse users don't have swipe gestures); collapse is touch-only
