/**
 * The anonymous chat store.
 *
 * The property under test is a privacy one: the legacy key is deleted and
 * never read. It was not namespaced per user and survived logout, so on a
 * shared browser the second person to sign in inherited the first person's
 * conversations.
 */
import { beforeEach, describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import type { ChatMessage, ChatSession } from '../types/chat'
import MessageBubble from '../components/chat/MessageBubble'
import {
  ANON_KEY,
  LEGACY_KEY,
  clearChatStorage,
  purgeLegacyChatSessions,
  readAnonSessions,
  trimForRequest,
  writeAnonSessions,
} from './chatStorage'
import { normalizeCitations } from './researchCitations'

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

describe('anonymous citation round-trip', () => {
  const citationWire = {
    evidence_id: '1ac7a52713bdf683e6be98a05ae4dfe6',
    platform: 'x' as const,
    handle: 'kap_bildirimleri',
    display_name: 'KAP Bildirimleri',
    published_at: '2026-08-27T09:00:00+00:00',
    post_url: 'https://x.com/kap_bildirimleri/status/123',
    kap_url: 'https://kap.org.tr/tr/Bildirim/1',
    verification_status: 'officially_verified' as const,
    source_type: 'disclosure_aggregator' as const,
    excerpt: 'Kısa güvenli özet',
    matched_symbols: ['ASELS'],
  }

  it('revives publishedAt as Date and keeps KAP/X links after localStorage', () => {
    const safe = normalizeCitations([citationWire])
    expect(safe[0].publishedAt).toBeInstanceOf(Date)

    const stored: ChatSession = {
      id: 'anon-1',
      title: 'ASELS',
      updatedAt: new Date('2026-08-27T10:00:00Z'),
      messages: [
        {
          id: 'u-1',
          text: 'ASELS haber?',
          sender: 'user',
          timestamp: new Date('2026-08-27T10:00:00Z'),
        },
        {
          id: 'a-1',
          text: 'Araştırma özeti',
          sender: 'ai',
          timestamp: new Date('2026-08-27T10:00:01Z'),
          citations: safe,
        },
      ],
    }

    expect(() => writeAnonSessions([stored])).not.toThrow()
    const [restored] = readAnonSessions()
    expect(restored.messages[0].citations).toBeUndefined()
    expect(restored.messages[1].citations).toHaveLength(1)
    const revived = restored.messages[1].citations![0]
    expect(revived.publishedAt).toBeInstanceOf(Date)
    expect(revived.publishedAt!.toISOString()).toBe(
      new Date(citationWire.published_at).toISOString(),
    )
    expect(revived.kapUrl).toBe(citationWire.kap_url)
    expect(revived.postUrl).toBe(citationWire.post_url)

    expect(() =>
      render(<MessageBubble message={restored.messages[1]} />),
    ).not.toThrow()
    expect(screen.getByRole('heading', { name: 'Kaynaklar' })).toBeInTheDocument()
    expect(
      screen.getByRole('link', { name: 'KAP bildirimini görüntüle' }),
    ).toHaveAttribute('href', citationWire.kap_url)
  })

  it('drops tampered localStorage citation links without losing the message', () => {
    const safe = normalizeCitations([citationWire])
    writeAnonSessions([
      {
        id: 'anon-2',
        title: 't',
        updatedAt: new Date('2026-08-27T10:00:00Z'),
        messages: [
          {
            id: 'u-1',
            text: 'soru',
            sender: 'user',
            timestamp: new Date('2026-08-27T10:00:00Z'),
          },
          {
            id: 'a-1',
            text: 'cevap kalır',
            sender: 'ai',
            timestamp: new Date('2026-08-27T10:00:01Z'),
            citations: safe,
          },
        ],
      },
    ])

    const raw = JSON.parse(localStorage.getItem(ANON_KEY)!)
    raw[0].messages[1].citations[0].postUrl = 'https://x.com.evil.example/a/status/1'
    raw[0].messages[1].citations[0].kapUrl = 'https://kap.org.tr.evil.example/x'
    localStorage.setItem(ANON_KEY, JSON.stringify(raw))

    const [restored] = readAnonSessions()
    expect(restored.messages[1].text).toBe('cevap kalır')
    expect(restored.messages[1].citations ?? []).toEqual([])
    expect(restored.messages[0].citations).toBeUndefined()
  })

  it('keeps old anonymous sessions without citations loadable', () => {
    writeAnonSessions([session()])
    const [restored] = readAnonSessions()
    expect(restored.messages).toHaveLength(2)
    expect(restored.messages.every((m) => !m.citations?.length)).toBe(true)
  })

  it('does not let a user message acquire citations from storage', () => {
    const safe = normalizeCitations([citationWire])
    writeAnonSessions([
      {
        id: 'anon-3',
        title: 't',
        updatedAt: new Date('2026-08-27T10:00:00Z'),
        messages: [
          {
            id: 'u-1',
            text: 'soru',
            sender: 'user',
            timestamp: new Date('2026-08-27T10:00:00Z'),
            citations: safe,
          },
        ],
      },
    ])
    const [restored] = readAnonSessions()
    expect(restored.messages[0].sender).toBe('user')
    expect(restored.messages[0].citations).toBeUndefined()
  })

  it('filters non-string disclosures and tolerates odd message shapes', () => {
    localStorage.setItem(
      ANON_KEY,
      JSON.stringify([
        {
          id: 's',
          title: 't',
          updatedAt: '2026-08-27T10:00:00Z',
          messages: [
            {
              id: 42,
              text: null,
              sender: 'robot',
              timestamp: 'not-a-date',
              disclosures: ['ok', 3, null, 'two'],
            },
            null,
            5,
            {
              id: null,
              text: 'x',
              sender: 'ai',
              timestamp: 1_725_000_000_000,
              disclosures: 'nope',
            },
            {
              id: 'd',
              text: 'with date',
              sender: 'ai',
              timestamp: new Date('2026-08-27T09:00:00Z').toISOString(),
            },
          ],
        },
      ]),
    )
    // Inject a live Date instance (JSON cannot) via a write-then-mutate path.
    const parsed = JSON.parse(localStorage.getItem(ANON_KEY)!)
    parsed[0].messages.push({
      id: 'live-date',
      text: 'd',
      sender: 'ai',
      timestamp: new Date('2026-08-27T11:00:00Z'),
      disclosures: [],
    })
    // Force reviveMessage(non-object) and reviveMessage(null) via direct map input
    // by writing a session that readAnonSessions will parse — null/5 already above.
    localStorage.setItem(ANON_KEY, JSON.stringify(parsed))

    const [restored] = readAnonSessions()
    expect(restored.messages[0].id).toBe('42')
    expect(restored.messages[0].text).toBe('')
    expect(restored.messages[0].sender).toBe('ai')
    expect(restored.messages[0].disclosures).toEqual(['ok', 'two'])
    expect(restored.messages[0].timestamp).toEqual(new Date(0))
    // null → empty object defaults; number 5 → same
    expect(restored.messages[1].sender).toBe('ai')
    expect(restored.messages[2].sender).toBe('ai')
    expect(restored.messages[3].id).toBe('')
    expect(restored.messages[3].disclosures).toEqual([])
    expect(restored.messages[3].timestamp).toBeInstanceOf(Date)
  })
})
