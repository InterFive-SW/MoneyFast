/**
 * The anonymous chat store.
 *
 * The property under test is a privacy one: the legacy key is deleted and
 * never read. It was not namespaced per user and survived logout, so on a
 * shared browser the second person to sign in inherited the first person's
 * conversations.
 */
import { beforeEach, describe, expect, it } from 'vitest'
import type { ChatMessage, ChatSession } from '../types/chat'
import {
  ANON_KEY,
  LEGACY_KEY,
  clearChatStorage,
  purgeLegacyChatSessions,
  readAnonSessions,
  trimForRequest,
  writeAnonSessions,
} from './chatStorage'

function message(text: string, sender: 'user' | 'ai' = 'user'): ChatMessage {
  return { id: `m-${text}`, text, sender, timestamp: new Date('2026-08-25T10:00:00Z') }
}

function session(id = 's-1'): ChatSession {
  return {
    id,
    title: 'THYAO',
    messages: [message('soru'), message('cevap', 'ai')],
    updatedAt: new Date('2026-08-25T10:00:00Z'),
  }
}

beforeEach(() => localStorage.clear())

describe('purgeLegacyChatSessions', () => {
  it('deletes the legacy key', () => {
    localStorage.setItem(LEGACY_KEY, JSON.stringify([session()]))
    purgeLegacyChatSessions()
    expect(localStorage.getItem(LEGACY_KEY)).toBeNull()
  })

  it('is safe when the key was never there', () => {
    expect(() => purgeLegacyChatSessions()).not.toThrow()
  })

  it('leaves the anonymous store alone', () => {
    writeAnonSessions([session()])
    purgeLegacyChatSessions()
    expect(readAnonSessions()).toHaveLength(1)
  })
})

describe('readAnonSessions', () => {
  it('is empty when nothing was stored', () => {
    expect(readAnonSessions()).toEqual([])
  })

  it('revives Date fields, which JSON round-tripping flattens to strings', () => {
    writeAnonSessions([session()])
    const [restored] = readAnonSessions()
    expect(restored.updatedAt).toBeInstanceOf(Date)
    expect(restored.messages[0].timestamp).toBeInstanceOf(Date)
  })

  it('returns an empty list rather than throwing on corrupt JSON', () => {
    /* A broken store must not take the chat down with it, and there is
       nothing in it worth recovering by hand. */
    localStorage.setItem(ANON_KEY, '{not json')
    expect(readAnonSessions()).toEqual([])
  })

  it('returns an empty list when the stored value is not an array', () => {
    localStorage.setItem(ANON_KEY, '{"sessions": []}')
    expect(readAnonSessions()).toEqual([])
  })

  it('tolerates a session with no messages array', () => {
    localStorage.setItem(
      ANON_KEY,
      JSON.stringify([{ id: 's', title: 't', updatedAt: '2026-08-25T10:00:00Z' }]),
    )
    expect(readAnonSessions()[0].messages).toEqual([])
  })

  it('never reads the legacy key', () => {
    localStorage.setItem(LEGACY_KEY, JSON.stringify([session('someone-elses')]))
    expect(readAnonSessions()).toEqual([])
  })
})

describe('writeAnonSessions', () => {
  it('stores what readAnonSessions can restore', () => {
    writeAnonSessions([session()])
    expect(readAnonSessions()[0].title).toBe('THYAO')
  })

  it('removes the key entirely when the last session is deleted', () => {
    writeAnonSessions([session()])
    writeAnonSessions([])
    expect(localStorage.getItem(ANON_KEY)).toBeNull()
  })
})

describe('clearChatStorage', () => {
  it('removes both the anonymous store and the legacy key', () => {
    localStorage.setItem(LEGACY_KEY, '[]')
    writeAnonSessions([session()])
    clearChatStorage()
    expect(localStorage.getItem(LEGACY_KEY)).toBeNull()
    expect(localStorage.getItem(ANON_KEY)).toBeNull()
  })
})

describe('trimForRequest', () => {
  it('maps the UI sender onto the wire role', () => {
    expect(trimForRequest([message('soru'), message('cevap', 'ai')])).toEqual([
      { role: 'user', content: 'soru' },
      { role: 'assistant', content: 'cevap' },
    ])
  })

  it('keeps only the newest messages', () => {
    const many = Array.from({ length: 30 }, (_, i) => message(`m${i}`))
    const trimmed = trimForRequest(many)
    expect(trimmed).toHaveLength(20)
    expect(trimmed[trimmed.length - 1].content).toBe('m29')
  })

  it('caps a single oversized message', () => {
    const [trimmed] = trimForRequest([message('x'.repeat(5000))])
    expect(trimmed.content).toHaveLength(2000)
  })

  it('is empty for an empty conversation', () => {
    expect(trimForRequest([])).toEqual([])
  })
})
