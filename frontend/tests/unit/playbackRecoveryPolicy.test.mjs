import assert from 'node:assert/strict'
import test from 'node:test'

import {
  classifyPause,
  shouldAutoResumeAfterPause,
  shouldResumeOnForeground,
  isPlaybackStagnant,
  shouldPreserveAsPaused,
  shouldPrefetchNextTrack
} from '../../src/services/tts/playbackRecoveryPolicy.js'

// ==================== classifyPause ====================

test('classifyPause: manual pause wins over ended', () => {
  assert.equal(classifyPause({ manualPause: true, ended: false }), 'manual')
  assert.equal(classifyPause({ manualPause: true, ended: true }), 'manual')
})

test('classifyPause: internal transition beats manual flag is impossible; internal requires !manualPause', () => {
  assert.equal(classifyPause({ internalTransition: true, manualPause: false }), 'internal')
  assert.equal(classifyPause({ internalTransition: true, manualPause: true }), 'manual')
})

test('classifyPause: natural end', () => {
  assert.equal(classifyPause({ ended: true }), 'ended')
})

test('classifyPause: system/interruption pause is unintended', () => {
  assert.equal(classifyPause({}), 'unintended')
})

// ==================== shouldAutoResumeAfterPause ====================

test('shouldAutoResumeAfterPause: only unintended + visible + online', () => {
  assert.equal(shouldAutoResumeAfterPause({ classification: 'unintended', visibilityState: 'visible', online: true }), true)
  assert.equal(shouldAutoResumeAfterPause({ classification: 'manual', visibilityState: 'visible', online: true }), false)
  assert.equal(shouldAutoResumeAfterPause({ classification: 'internal', visibilityState: 'visible', online: true }), false)
  assert.equal(shouldAutoResumeAfterPause({ classification: 'ended', visibilityState: 'visible', online: true }), false)
})

test('shouldAutoResumeAfterPause: hidden app must not steal audio focus', () => {
  assert.equal(shouldAutoResumeAfterPause({ classification: 'unintended', visibilityState: 'hidden', online: true }), false)
})

test('shouldAutoResumeAfterPause: offline blocks resume', () => {
  assert.equal(shouldAutoResumeAfterPause({ classification: 'unintended', visibilityState: 'visible', online: false }), false)
})

// ==================== shouldResumeOnForeground ====================

test('shouldResumeOnForeground: resumes wedged session on return', () => {
  assert.equal(shouldResumeOnForeground({
    hasSession: true, elementStopped: true, online: true
  }), true)
})

test('shouldResumeOnForeground: respects manual pause and natural end', () => {
  assert.equal(shouldResumeOnForeground({ manualPause: true, hasSession: true, elementStopped: true }), false)
  assert.equal(shouldResumeOnForeground({ suppressAutoResume: true, hasSession: true, elementStopped: true }), false)
})

test('shouldResumeOnForeground: no-op without session, while playing, or offline', () => {
  assert.equal(shouldResumeOnForeground({ hasSession: false, elementStopped: true }), false)
  assert.equal(shouldResumeOnForeground({ hasSession: true, elementStopped: false }), false)
  assert.equal(shouldResumeOnForeground({ hasSession: true, elementStopped: true, online: false }), false)
})

// ==================== isPlaybackStagnant ====================

test('isPlaybackStagnant: detects frozen clock while "playing"', () => {
  assert.equal(isPlaybackStagnant({
    paused: false, ended: false, hasSession: true,
    currentTime: 120.01, lastTime: 120.02, online: true
  }), true)
})

test('isPlaybackStagnant: advancing clock is healthy', () => {
  assert.equal(isPlaybackStagnant({
    paused: false, hasSession: true,
    currentTime: 125.5, lastTime: 120.0, online: true
  }), false)
})

test('isPlaybackStagnant: excluded states never trigger', () => {
  const base = { currentTime: 100, lastTime: 100, hasSession: true }
  assert.equal(isPlaybackStagnant({ ...base, paused: true }), false)
  assert.equal(isPlaybackStagnant({ ...base, ended: true, paused: false }), false)
  assert.equal(isPlaybackStagnant({ ...base, paused: false, manualPause: true }), false)
  assert.equal(isPlaybackStagnant({ ...base, paused: false, internalTransition: true }), false)
  assert.equal(isPlaybackStagnant({ ...base, paused: false, seeking: true }), false)
  assert.equal(isPlaybackStagnant({ ...base, paused: false, recovering: true }), false)
  assert.equal(isPlaybackStagnant({ ...base, paused: false, online: false }), false)
  assert.equal(isPlaybackStagnant({ ...base, paused: false, hasSession: false }), false)
})

// ==================== shouldPreserveAsPaused ====================

test('shouldPreserveAsPaused: mid-track wedge is preserved', () => {
  assert.equal(shouldPreserveAsPaused({ currentTime: 120, totalTime: 600 }), true)
})

test('shouldPreserveAsPaused: not started / finished / unknown duration clears', () => {
  assert.equal(shouldPreserveAsPaused({ currentTime: 0, totalTime: 600 }), false)
  assert.equal(shouldPreserveAsPaused({ currentTime: 600, totalTime: 600 }), false)
  assert.equal(shouldPreserveAsPaused({ currentTime: 100, totalTime: 0 }), false)
})

// ==================== shouldPrefetchNextTrack ====================

test('shouldPrefetchNextTrack: triggers near track end', () => {
  assert.equal(shouldPrefetchNextTrack({
    currentTime: 540, totalTime: 600, hasNext: true, now: 100000
  }), true)
})

test('shouldPrefetchNextTrack: not before threshold', () => {
  assert.equal(shouldPrefetchNextTrack({
    currentTime: 100, totalTime: 600, hasNext: true, now: 100000
  }), false)
})

test('shouldPrefetchNextTrack: blocked when no next / done / in flight', () => {
  const base = { currentTime: 590, totalTime: 600, now: 100000 }
  assert.equal(shouldPrefetchNextTrack({ ...base, hasNext: false }), false)
  assert.equal(shouldPrefetchNextTrack({ ...base, hasNext: true, prefetched: true }), false)
  assert.equal(shouldPrefetchNextTrack({ ...base, hasNext: true, inFlight: true }), false)
})

test('shouldPrefetchNextTrack: respects retry interval after failed attempt', () => {
  assert.equal(shouldPrefetchNextTrack({
    currentTime: 590, totalTime: 600, hasNext: true,
    lastAttemptAt: 95000, now: 100000, retryMs: 10000
  }), false)
  assert.equal(shouldPrefetchNextTrack({
    currentTime: 590, totalTime: 600, hasNext: true,
    lastAttemptAt: 89000, now: 100000, retryMs: 10000
  }), true)
})

test('shouldPrefetchNextTrack: unknown duration never triggers', () => {
  assert.equal(shouldPrefetchNextTrack({
    currentTime: 9999, totalTime: 0, hasNext: true, now: 100000
  }), false)
})
