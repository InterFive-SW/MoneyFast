/**
 * Chat sessions.
 *
 * Three properties carry this hook, and all three were broken before it:
 *
 * 1. A signed-in user's history comes from the SERVER. It used to come from a
 *    single unnamespaced localStorage key that survived logout, so on a shared
 *    browser the second person to sign in inherited the first person's chats.
 * 2. A turn that was not stored says so. An expired token yields 200-anonymous
 *    on the chat endpoints, so the session dropped without a single signal and
 *    nothing was being saved.
 * 3. Deleting reaches the server. It used to filter a local array while the
 *    row lived on forever.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { renderHook, act, waitFor } from '@testing-library/react'
import { useChatSessions, HISTORY_LOAD_ERROR, DELETE_ERROR } from './useChatSessions'
import { apiClient } from '../api/client'
import { ANON_KEY, LEGACY_KEY } from '../lib/chatStorage'

const CONVERSATION = {
  id: 'conv-1',
  thread_id: 't-1',
  title: 'THYAO ne durumda?',
  created_at: '2026-08-25T10:00:00Z',
  updated_at: '2026-08-25T10:05:00Z',
}

const DETAIL = {
  ...CONVERSATION,
  messages: [
    {
      id: 'm-1',
      role: 'user' as const,
      content: 'THYAO ne durumda?',
      created_at: '2026-08-25T10:00:00Z',
      disclosures: [],
    },
    {
      id: 'm-2',
      role: 'assistant' as const,
      content: 'THYAO bir havayolu şirketi.',
      created_at: '2026-08-25T10:00:01Z',
      disclosures: ['Yatırım tavsiyesi değildir.'],
    },
  ],
  has_more: false,
  context_topic: 'THYAO',
}

function answer(persistence = 'saved') {
  return {
    final_output: 'Cevap',
    disclosures: [],
    context_topic: null,
    persistence,
  }
}

beforeEach(() => {
  localStorage.clear()
  vi.spyOn(console, 'error').mockImplementation(() => {})
  vi.spyOn(apiClient, 'ensureFreshSession').mockResolvedValue('authenticated')
  vi.spyOn(apiClient, 'getConversations').mockResolvedValue({
    items: [CONVERSATION],
    total: 1,
    limit: 30,
    offset: 0,
  })
  vi.spyOn(apiClient, 'getConversation').mockResolvedValue(DETAIL)
  vi.spyOn(apiClient, 'deleteConversation').mockResolvedValue({
    thread_id: 't-1',
    status: 'deleted',
  })
  vi.spyOn(apiClient, 'renameConversation').mockResolvedValue(CONVERSATION)
  vi.spyOn(apiClient, 'streamChat').mockImplementation(async (_body, handlers) => {
    handlers.onStage?.('Yanıt yazılıyor...')
    handlers.onDone?.(answer())
    handlers.onSaved?.({ conversation_id: 'conv-1', persistence: 'saved' })
    return true
  })
  vi.spyOn(apiClient, 'post').mockResolvedValue(answer() as never)
})
afterEach(() => vi.restoreAllMocks())

/** `Array.prototype.at` needs ES2022; tsconfig targets lower. */
function lastMessage(messages: { id: string; text: string }[]) {
  return messages[messages.length - 1]
}

async function mounted() {
  const view = renderHook(() => useChatSessions())
  await waitFor(() => expect(apiClient.ensureFreshSession).toHaveBeenCalled())
  return view
}

// --------------------------------------------------------------------------
// Hydration
// --------------------------------------------------------------------------
describe('hydration', () => {
  it('loads a signed-in user’s sessions from the server', async () => {
    const { result } = await mounted()
    await waitFor(() => expect(result.current.sessions).toHaveLength(1))
    expect(result.current.sessions[0].title).toBe('THYAO ne durumda?')
    expect(result.current.sessions[0].origin).toBe('server')
  })

  it('opens the most recent conversation and loads its messages', async () => {
    const { result } = await mounted()
    await waitFor(() => expect(result.current.messages).toHaveLength(2))
    expect(result.current.activeSessionId).toBe('t-1')
    expect(result.current.messages[1].disclosures).toEqual([
      'Yatırım tavsiyesi değildir.',
    ])
    expect(result.current.activeContext).toBe('THYAO')
  })

  it('deletes the legacy key without ever reading it', async () => {
    /* The whole fix for the leak. We cannot tell who wrote that key, so the
       only safe read is none at all. */
    localStorage.setItem(LEGACY_KEY, JSON.stringify([{ id: 'someone-elses' }]))
    const { result } = await mounted()
    await waitFor(() => expect(localStorage.getItem(LEGACY_KEY)).toBeNull())
    expect(result.current.sessions.some((s) => s.id === 'someone-elses')).toBe(false)
  })

  it('purges the legacy key for an anonymous visitor too', async () => {
    vi.mocked(apiClient.ensureFreshSession).mockResolvedValue('anonymous')
    localStorage.setItem(LEGACY_KEY, JSON.stringify([{ id: 'someone-elses' }]))
    await mounted()
    await waitFor(() => expect(localStorage.getItem(LEGACY_KEY)).toBeNull())
  })

  it('reads local sessions for an anonymous visitor', async () => {
    vi.mocked(apiClient.ensureFreshSession).mockResolvedValue('anonymous')
    localStorage.setItem(
      ANON_KEY,
      JSON.stringify([
        { id: 'a-1', title: 'anonim', messages: [], updatedAt: '2026-08-25T10:00:00Z' },
      ]),
    )
    const { result } = await mounted()
    await waitFor(() => expect(result.current.sessions).toHaveLength(1))
    expect(result.current.sessions[0].title).toBe('anonim')
    expect(apiClient.getConversations).not.toHaveBeenCalled()
  })

  it('shows a notice instead of falling back to localStorage when the list fails', async () => {
    /* Falling back is precisely what would reintroduce cross-account leakage
       on a shared browser. */
    localStorage.setItem(ANON_KEY, JSON.stringify([{ id: 'a-1', messages: [] }]))
    vi.mocked(apiClient.getConversations).mockRejectedValue(new Error('boom'))
    const { result } = await mounted()
    await waitFor(() => expect(result.current.notice).toBe(HISTORY_LOAD_ERROR))
    expect(result.current.sessions).toEqual([])
  })

  it('keeps the session listed when its messages fail to load', async () => {
    vi.mocked(apiClient.getConversation).mockRejectedValue(new Error('boom'))
    const { result } = await mounted()
    await waitFor(() => expect(result.current.notice).toBe(HISTORY_LOAD_ERROR))
    expect(result.current.sessions).toHaveLength(1)
  })

  it('does not open anything when there are no conversations', async () => {
    vi.mocked(apiClient.getConversations).mockResolvedValue({
      items: [],
      total: 0,
      limit: 30,
      offset: 0,
    })
    const { result } = await mounted()
    await waitFor(() => expect(result.current.sessions).toEqual([]))
    expect(apiClient.getConversation).not.toHaveBeenCalled()
  })

  it('never writes a signed-in user’s conversations to localStorage', async () => {
    const { result } = await mounted()
    await waitFor(() => expect(result.current.sessions).toHaveLength(1))
    expect(localStorage.getItem(ANON_KEY)).toBeNull()
  })
})

// --------------------------------------------------------------------------
// Session management
// --------------------------------------------------------------------------
describe('session management', () => {
  it('starts a new empty session', async () => {
    const { result } = await mounted()
    await waitFor(() => expect(result.current.sessions).toHaveLength(1))
    act(() => result.current.createNewSession())
    expect(result.current.sessions).toHaveLength(2)
    expect(result.current.messages).toEqual([])
    expect(result.current.activeContext).toBeNull()
  })

  it('fetches messages the first time a session is opened', async () => {
    const older = { ...CONVERSATION, id: 'conv-2', thread_id: 't-2', title: 'eski' }
    vi.mocked(apiClient.getConversations).mockResolvedValue({
      items: [CONVERSATION, older], total: 2, limit: 30, offset: 0,
    })
    const { result } = await mounted()
    // Hydration opens only the most recent one; the other stays a stub.
    await waitFor(() => expect(result.current.sessions).toHaveLength(2))
    expect(result.current.sessions[1].messagesLoaded).toBe(false)

    await act(async () => result.current.loadSession('t-2'))
    await waitFor(() => expect(result.current.activeSessionId).toBe('t-2'))
    expect(apiClient.getConversation).toHaveBeenCalledWith('t-2')
    expect(apiClient.getConversation).toHaveBeenCalledTimes(2)
  })

  it('does not refetch a session whose messages are already loaded', async () => {
    const { result } = await mounted()
    await waitFor(() => expect(result.current.messages).toHaveLength(2))
    act(() => result.current.createNewSession())
    const localId = result.current.activeSessionId as string
    act(() => result.current.loadSession(localId))
    expect(apiClient.getConversation).toHaveBeenCalledTimes(1)
  })

  it('deletes on the server, not just in the array', async () => {
    const { result } = await mounted()
    await waitFor(() => expect(result.current.sessions).toHaveLength(1))
    await act(async () => { await result.current.deleteSession('t-1') })
    expect(apiClient.deleteConversation).toHaveBeenCalledWith('t-1')
    expect(result.current.sessions).toEqual([])
    expect(result.current.activeSessionId).toBeNull()
  })

  it('restores the row when the delete fails', async () => {
    /* Telling someone a conversation is gone and then having it reappear on
       the next load is worse than the delete failing loudly. */
    vi.mocked(apiClient.deleteConversation).mockRejectedValue(new Error('boom'))
    const { result } = await mounted()
    await waitFor(() => expect(result.current.sessions).toHaveLength(1))
    await act(async () => { await result.current.deleteSession('t-1') })
    expect(result.current.sessions).toHaveLength(1)
    expect(result.current.notice).toBe(DELETE_ERROR)
  })

  it('restores it to its place in the list, not to the end', async () => {
    const older = {
      ...CONVERSATION,
      id: 'conv-2',
      thread_id: 't-2',
      title: 'eski',
      updated_at: '2026-08-24T10:00:00Z',
    }
    vi.mocked(apiClient.getConversations).mockResolvedValue({
      items: [CONVERSATION, older], total: 2, limit: 30, offset: 0,
    })
    vi.mocked(apiClient.deleteConversation).mockRejectedValue(new Error('boom'))
    const { result } = await mounted()
    await waitFor(() => expect(result.current.sessions).toHaveLength(2))
    await act(async () => { await result.current.deleteSession('t-1') })
    expect(result.current.sessions.map((s) => s.id)).toEqual(['t-1', 't-2'])
  })

  it('does not call the server for a session that was never sent', async () => {
    /* A local session has no row; deleting it server-side would 404. */
    const { result } = await mounted()
    await waitFor(() => expect(result.current.sessions).toHaveLength(1))
    act(() => result.current.createNewSession())
    const localId = result.current.activeSessionId as string
    await act(async () => { await result.current.deleteSession(localId) })
    expect(apiClient.deleteConversation).not.toHaveBeenCalled()
  })

  it('ignores a delete for an id that is not there', async () => {
    const { result } = await mounted()
    await waitFor(() => expect(result.current.sessions).toHaveLength(1))
    await act(async () => { await result.current.deleteSession('nope') })
    expect(apiClient.deleteConversation).not.toHaveBeenCalled()
    expect(result.current.sessions).toHaveLength(1)
  })

  it('renames on the server', async () => {
    const { result } = await mounted()
    await waitFor(() => expect(result.current.sessions).toHaveLength(1))
    await act(async () => { await result.current.renameSession('t-1', 'Yeni ad') })
    expect(apiClient.renameConversation).toHaveBeenCalledWith('t-1', 'Yeni ad')
    expect(result.current.sessions[0].title).toBe('Yeni ad')
  })

  it('puts the old title back when the rename fails', async () => {
    vi.mocked(apiClient.renameConversation).mockRejectedValue(new Error('boom'))
    const { result } = await mounted()
    await waitFor(() => expect(result.current.sessions).toHaveLength(1))
    await act(async () => { await result.current.renameSession('t-1', 'Yeni ad') })
    expect(result.current.sessions[0].title).toBe('THYAO ne durumda?')
  })

  it('renames a local session without calling the server', async () => {
    const { result } = await mounted()
    await waitFor(() => expect(result.current.sessions).toHaveLength(1))
    act(() => result.current.createNewSession())
    const localId = result.current.activeSessionId as string
    await act(async () => { await result.current.renameSession(localId, 'Yerel') })
    expect(apiClient.renameConversation).not.toHaveBeenCalled()
  })

  it('ignores a rename for an id that is not there', async () => {
    const { result } = await mounted()
    await waitFor(() => expect(result.current.sessions).toHaveLength(1))
    await act(async () => { await result.current.renameSession('nope', 'x') })
    expect(apiClient.renameConversation).not.toHaveBeenCalled()
  })

  it('dismisses the context panel', async () => {
    const { result } = await mounted()
    await waitFor(() => expect(result.current.activeContext).toBe('THYAO'))
    act(() => result.current.dismissContext())
    expect(result.current.activeContext).toBeNull()
  })

  it('dismisses a notice', async () => {
    vi.mocked(apiClient.getConversations).mockRejectedValue(new Error('boom'))
    const { result } = await mounted()
    await waitFor(() => expect(result.current.notice).toBe(HISTORY_LOAD_ERROR))
    act(() => result.current.dismissNotice())
    expect(result.current.notice).toBeNull()
  })
})

// --------------------------------------------------------------------------
// Sending
// --------------------------------------------------------------------------
describe('sending a message', () => {
  it('appends the question and the answer', async () => {
    const { result } = await mounted()
    await waitFor(() => expect(result.current.messages).toHaveLength(2))
    await act(async () => { await result.current.handleSendMessage('selam') })
    expect(result.current.messages.map((m) => m.text)).toEqual([
      'THYAO ne durumda?',
      'THYAO bir havayolu şirketi.',
      'selam',
      'Cevap',
    ])
    expect(result.current.isTyping).toBe(false)
  })

  it('opens a session and titles it from the first message', async () => {
    vi.mocked(apiClient.getConversations).mockResolvedValue({
      items: [], total: 0, limit: 30, offset: 0,
    })
    const { result } = await mounted()
    await waitFor(() => expect(result.current.sessions).toEqual([]))
    await act(async () => { await result.current.handleSendMessage('portföyüm ne durumda?') })
    expect(result.current.sessions[0].title).toBe('portföyüm ne durumda?')
  })

  it('truncates a long first message into the title', async () => {
    vi.mocked(apiClient.getConversations).mockResolvedValue({
      items: [], total: 0, limit: 30, offset: 0,
    })
    const { result } = await mounted()
    await waitFor(() => expect(result.current.sessions).toEqual([]))
    await act(async () => { await result.current.handleSendMessage('u'.repeat(80)) })
    expect(result.current.sessions[0].title).toHaveLength(33)
    expect(result.current.sessions[0].title.endsWith('...')).toBe(true)
  })

  it('sends the prior turns and the thread id', async () => {
    const { result } = await mounted()
    await waitFor(() => expect(result.current.messages).toHaveLength(2))
    await act(async () => { await result.current.handleSendMessage('peki ya o?') })
    const body = vi.mocked(apiClient.streamChat).mock.calls[0][0] as any
    expect(body.thread_id).toBe('t-1')
    expect(body.conversation_history).toEqual([
      { role: 'user', content: 'THYAO ne durumda?' },
      { role: 'assistant', content: 'THYAO bir havayolu şirketi.' },
    ])
  })

  it('refreshes the session before every turn', async () => {
    /* An expired token returns 200-anonymous on the chat endpoints, so
       authedFetch's 401-driven refresh never fires on this path. */
    const { result } = await mounted()
    await waitFor(() => expect(result.current.messages).toHaveLength(2))
    vi.mocked(apiClient.ensureFreshSession).mockClear()
    await act(async () => { await result.current.handleSendMessage('selam') })
    expect(apiClient.ensureFreshSession).toHaveBeenCalled()
  })

  it('reports the stage labels while the graph runs', async () => {
    const seen: (string | undefined)[] = []
    vi.mocked(apiClient.streamChat).mockImplementation(async (_b, handlers) => {
      handlers.onStage?.('Talebiniz sınıflandırılıyor...')
      seen.push('Talebiniz sınıflandırılıyor...')
      handlers.onDone?.(answer())
      return true
    })
    const { result } = await mounted()
    await act(async () => { await result.current.handleSendMessage('selam') })
    expect(seen).toEqual(['Talebiniz sınıflandırılıyor...'])
    expect(result.current.currentThought).toBeUndefined()
  })

  it('falls back to the buffered endpoint when the stream cannot be established', async () => {
    vi.mocked(apiClient.streamChat).mockResolvedValue(false)
    const { result } = await mounted()
    await act(async () => { await result.current.handleSendMessage('selam') })
    expect(apiClient.post).toHaveBeenCalled()
    expect(lastMessage(result.current.messages)?.text).toBe('Cevap')
  })

  it('falls back when the stream reports done but delivers nothing', async () => {
    vi.mocked(apiClient.streamChat).mockResolvedValue(true)
    const { result } = await mounted()
    await act(async () => { await result.current.handleSendMessage('selam') })
    expect(apiClient.post).toHaveBeenCalled()
  })

  it('sets the context topic from the answer', async () => {
    vi.mocked(apiClient.streamChat).mockImplementation(async (_b, handlers) => {
      handlers.onDone?.({ ...answer(), context_topic: 'ASELS' })
      return true
    })
    const { result } = await mounted()
    await act(async () => { await result.current.handleSendMessage('ASELS?') })
    expect(result.current.activeContext).toBe('ASELS')
  })

  it('marks the answer for the typewriter', async () => {
    const { result } = await mounted()
    await act(async () => { await result.current.handleSendMessage('selam') })
    expect(result.current.justAnsweredId).toBe(lastMessage(result.current.messages)?.id)
  })

  it('shows an error bubble when the request fails outright', async () => {
    vi.mocked(apiClient.streamChat).mockResolvedValue(false)
    vi.mocked(apiClient.post).mockRejectedValue(new Error('offline'))
    const { result } = await mounted()
    await act(async () => { await result.current.handleSendMessage('selam') })
    expect(lastMessage(result.current.messages)?.text).toContain('bağlanamıyorum')
    expect(result.current.isTyping).toBe(false)
  })

  it('starts a fresh session when the active id no longer exists', async () => {
    const { result } = await mounted()
    await waitFor(() => expect(result.current.sessions).toHaveLength(1))
    await act(async () => { await result.current.deleteSession('t-1') })
    await act(async () => { await result.current.handleSendMessage('selam') })
    expect(result.current.sessions).toHaveLength(1)
    expect(result.current.messages).toHaveLength(2)
  })
})

// --------------------------------------------------------------------------
// Persistence notices
// --------------------------------------------------------------------------
describe('persistence notices', () => {
  function withPersistence(persistence: string) {
    vi.mocked(apiClient.streamChat).mockImplementation(async (_b, handlers) => {
      handlers.onDone?.(answer(persistence))
      handlers.onSaved?.({ conversation_id: null, persistence })
      return true
    })
  }

  it('says nothing when the turn was stored', async () => {
    const { result } = await mounted()
    await act(async () => { await result.current.handleSendMessage('selam') })
    expect(result.current.notice).toBeNull()
  })

  it('says nothing to a genuinely anonymous visitor', async () => {
    /* They never had history to lose, so there is nothing to warn about. */
    withPersistence('anonymous')
    const { result } = await mounted()
    await act(async () => { await result.current.handleSendMessage('selam') })
    expect(result.current.notice).toBeNull()
  })

  it('warns when the session expired mid-conversation', async () => {
    withPersistence('session_expired')
    const { result } = await mounted()
    await act(async () => { await result.current.handleSendMessage('selam') })
    expect(result.current.notice).toContain('Oturumunuz sona erdi')
  })

  it('warns, in different words, when the write failed', async () => {
    /* record_turn swallows database errors so the answer survives. With
       server-side history that means the model will not see this turn. */
    withPersistence('failed')
    const { result } = await mounted()
    await act(async () => { await result.current.handleSendMessage('selam') })
    expect(result.current.notice).toContain('kaydedilemedi')
    expect(result.current.notice).not.toContain('Oturumunuz')
  })

  it('reads the status from the buffered response too', async () => {
    vi.mocked(apiClient.streamChat).mockResolvedValue(false)
    vi.mocked(apiClient.post).mockResolvedValue(answer('session_expired') as never)
    const { result } = await mounted()
    await act(async () => { await result.current.handleSendMessage('selam') })
    expect(result.current.notice).toContain('Oturumunuz sona erdi')
  })

  it('tolerates a buffered response with no status at all', async () => {
    vi.mocked(apiClient.streamChat).mockResolvedValue(false)
    vi.mocked(apiClient.post).mockResolvedValue({ final_output: 'Cevap' } as never)
    const { result } = await mounted()
    await act(async () => { await result.current.handleSendMessage('selam') })
    expect(result.current.notice).toBeNull()
  })

  it('promotes a local session to a server one once it is stored', async () => {
    /* Only then is there a row for delete and rename to address. */
    vi.mocked(apiClient.getConversations).mockResolvedValue({
      items: [], total: 0, limit: 30, offset: 0,
    })
    const { result } = await mounted()
    await waitFor(() => expect(result.current.sessions).toEqual([]))
    await act(async () => { await result.current.handleSendMessage('selam') })
    expect(result.current.sessions[0].origin).toBe('server')
  })

  it('leaves an unsaved session local', async () => {
    vi.mocked(apiClient.getConversations).mockResolvedValue({
      items: [], total: 0, limit: 30, offset: 0,
    })
    withPersistence('session_expired')
    const { result } = await mounted()
    await waitFor(() => expect(result.current.sessions).toEqual([]))
    await act(async () => { await result.current.handleSendMessage('selam') })
    expect(result.current.sessions[0].origin).toBe('local')
  })
})

// --------------------------------------------------------------------------
// Edge cases
// --------------------------------------------------------------------------
describe('edge cases', () => {
  it('falls back to a timestamp id where crypto.randomUUID is unavailable', async () => {
    /* Older Safari and any non-secure origin. An undefined id would collapse
       every session onto the same React key. */
    vi.stubGlobal('crypto', {})
    try {
      const { result } = await mounted()
      await waitFor(() => expect(result.current.sessions).toHaveLength(1))
      act(() => result.current.createNewSession())
      expect(result.current.activeSessionId).toMatch(/^\d+$/)
    } finally {
      vi.unstubAllGlobals()
    }
  })

  it('titles an untitled conversation rather than showing a blank row', async () => {
    vi.mocked(apiClient.getConversations).mockResolvedValue({
      items: [{ ...CONVERSATION, title: null }], total: 1, limit: 30, offset: 0,
    })
    const { result } = await mounted()
    await waitFor(() => expect(result.current.sessions).toHaveLength(1))
    expect(result.current.sessions[0].title).toBe('Yeni Sohbet')
  })

  it('tolerates a stored message with no disclosures field', async () => {
    vi.mocked(apiClient.getConversation).mockResolvedValue({
      ...DETAIL,
      messages: [{ ...DETAIL.messages[0], disclosures: undefined as never }],
      context_topic: null,
    })
    const { result } = await mounted()
    await waitFor(() => expect(result.current.messages).toHaveLength(1))
    expect(result.current.messages[0].disclosures).toEqual([])
    expect(result.current.activeContext).toBeNull()
  })

  it('uses `text` when the answer has no `final_output`', async () => {
    /* The buffered endpoint and the stream have differed on this key before. */
    vi.mocked(apiClient.streamChat).mockImplementation(async (_b, handlers) => {
      handlers.onDone?.({ text: 'Alternatif alan', disclosures: [] })
      return true
    })
    const { result } = await mounted()
    await act(async () => { await result.current.handleSendMessage('selam') })
    expect(lastMessage(result.current.messages)?.text).toBe('Alternatif alan')
  })

  it('says so rather than rendering an empty bubble when neither is present', async () => {
    vi.mocked(apiClient.streamChat).mockImplementation(async (_b, handlers) => {
      handlers.onDone?.({ disclosures: [] })
      return true
    })
    const { result } = await mounted()
    await act(async () => { await result.current.handleSendMessage('selam') })
    expect(lastMessage(result.current.messages)?.text).toBe('Yanıt alınamadı.')
  })

  it('keeps a server-supplied message id when there is one', async () => {
    vi.mocked(apiClient.streamChat).mockImplementation(async (_b, handlers) => {
      handlers.onDone?.({ id: 'srv-1', final_output: 'Cevap', disclosures: [] })
      return true
    })
    const { result } = await mounted()
    await act(async () => { await result.current.handleSendMessage('selam') })
    expect(lastMessage(result.current.messages)?.id).toBe('srv-1')
  })
})

describe('unmounting mid-hydration', () => {
  /** A promise this test resolves by hand, so unmount can happen first. */
  function deferred<T>() {
    let resolve!: (value: T) => void
    let reject!: (reason?: unknown) => void
    const promise = new Promise<T>((res, rej) => { resolve = res; reject = rej })
    return { promise, resolve, reject }
  }

  it('does not touch state after the session check resolves late', async () => {
    /* Navigating away mid-hydration used to warn about setting state on an
       unmounted component, and worse, could overwrite a newer mount. */
    const gate = deferred<'authenticated' | 'anonymous'>()
    vi.mocked(apiClient.ensureFreshSession).mockReturnValue(gate.promise)
    const { unmount } = renderHook(() => useChatSessions())
    unmount()
    await act(async () => { gate.resolve('authenticated'); await gate.promise })
    expect(apiClient.getConversations).not.toHaveBeenCalled()
  })

  it('does not apply a conversation list that arrives after unmount', async () => {
    const gate = deferred<any>()
    vi.mocked(apiClient.getConversations).mockReturnValue(gate.promise)
    const { unmount, result } = renderHook(() => useChatSessions())
    await waitFor(() => expect(apiClient.getConversations).toHaveBeenCalled())
    unmount()
    await act(async () => {
      gate.resolve({ items: [CONVERSATION], total: 1, limit: 30, offset: 0 })
      await gate.promise
    })
    expect(result.current.sessions).toEqual([])
  })

  it('does not raise a notice for a failure that arrives after unmount', async () => {
    const gate = deferred<any>()
    vi.mocked(apiClient.getConversations).mockReturnValue(gate.promise)
    const { unmount, result } = renderHook(() => useChatSessions())
    await waitFor(() => expect(apiClient.getConversations).toHaveBeenCalled())
    unmount()
    await act(async () => {
      gate.reject(new Error('boom'))
      await gate.promise.catch(() => {})
    })
    expect(result.current.notice).toBeNull()
  })
})
