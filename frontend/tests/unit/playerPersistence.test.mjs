import assert from 'node:assert/strict'
import test from 'node:test'

import {
  getMissingPlayableFields,
  serializePlaylist,
  shouldHydrateArticleForTts
} from '../../src/stores/playerPersistence.js'

test('serializePlaylist keeps identifiers needed to resume TTS playback', () => {
  const [saved] = serializePlaylist([
    {
      id: 118423,
      url: 'https://example.com/article',
      title: 'Article',
      summary: 'Short summary',
      content: 'Full text for playback',
      source: 'Example Feed',
      author: 'Reporter',
      published_at: '2026-06-09T00:00:00Z',
      updated_at: '2026-06-09T01:00:00Z',
      cover: 'https://example.com/cover.png'
    }
  ])

  assert.equal(saved.id, 118423)
  assert.equal(saved.content, undefined)
  assert.equal(saved.author, 'Reporter')
  assert.equal(saved.cover, 'https://example.com/cover.png')
})

test('shouldHydrateArticleForTts identifies restored metadata-only articles', () => {
  assert.equal(shouldHydrateArticleForTts({ id: 118423, url: 'https://example.com/article' }), false)
  assert.deepEqual(
    getMissingPlayableFields({ id: 118423, url: 'https://example.com/article' }),
    []
  )

  assert.equal(
    shouldHydrateArticleForTts({
      id: 118423,
      url: 'https://example.com/article',
      content: 'Ready for playback'
    }),
    false
  )
})
