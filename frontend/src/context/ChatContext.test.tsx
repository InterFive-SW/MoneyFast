import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ChatProvider, useChat } from './ChatContext'
import { api } from '../api/client'

const STORAGE_KEY = 'moneyfast_chat_sessions'

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (error: unknown) => void
  const promise = new Promise<T>((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

function TestConsumer() {
  const {
    sessions, activeSessionId, messages, isTyping, currentThought, activeContext,
    handleSendMessage, createNewSession, loadSession, deleteSession,
  } = useChat()

  return (
    <div>
      <span data-testid="sessionCount">{sessions.length}</span>
      <span data-testid="activeSessionId">{activeSessionId ?? ''}</span>
      <span data-testid="messageCount">{messages.length}</span>
      <span data-testid="isTyping">{String(isTyping)}</span>
      <span data-testid="currentThought">{currentThought ?? ''}</span>
      <span data-testid="activeContext">{activeContext ?? ''}</span>
      <span data-testid="lastMessageText">{messages[messages.length - 1]?.text ?? ''}</span>
      <span data-testid="activeTitle">{sessions.find((s) => s.id === activeSessionId)?.title ?? ''}</span>
      <button onClick={createNewSession}>yeni-oturum</button>
      <button onClick={() => handleSendMessage('kısa mesaj')}>gonder-kisa</button>
      <button onClick={() => handleSendMessage('a'.repeat(40))}>gonder-uzun</button>
      {sessions.map((s) => (
        <button key={s.id} onClick={() => loadSession(s.id)}>{`yukle-${s.id}`}</button>
      ))}
      {sessions.map((s) => (
        <button key={s.id} onClick={() => deleteSession(s.id)}>{`sil-${s.id}`}</button>
      ))}
    </div>
  )
}

function BadConsumer() {
  useChat()
  return null
}

function renderChat() {
  return render(<ChatProvider><TestConsumer /></ChatProvider>)
}

beforeEach(() => {
  localStorage.clear()
  vi.spyOn(console, 'error').mockImplementation(() => {})
})

afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
  vi.useRealTimers()
})

describe('useChat', () => {
  it('ChatProvider dışında kullanılırsa hata fırlatır', () => {
    expect(() => render(<BadConsumer />)).toThrow('useChat must be used within a ChatProvider')
  })
})

describe('ChatProvider — başlangıç yükleme (localStorage)', () => {
  it('localStorage boşsa hiç oturum olmadan başlar', () => {
    renderChat()
    expect(screen.getByTestId('sessionCount').textContent).toBe('0')
    expect(screen.getByTestId('activeSessionId').textContent).toBe('')
  })

  it('localStorage\'da geçerli oturumlar varsa yüklenir ve en son güncellenen aktif olur', () => {
    const older = { id: 'old', title: 'Eski', messages: [], updatedAt: new Date('2026-01-01').toISOString() }
    const newer = {
      id: 'new',
      title: 'Yeni',
      messages: [{ id: 'm1', text: 'merhaba', sender: 'user', timestamp: new Date('2026-06-01').toISOString() }],
      updatedAt: new Date('2026-06-01').toISOString(),
    }
    localStorage.setItem(STORAGE_KEY, JSON.stringify([older, newer]))

    renderChat()

    expect(screen.getByTestId('sessionCount').textContent).toBe('2')
    expect(screen.getByTestId('activeSessionId').textContent).toBe('new')
    expect(screen.getByTestId('messageCount').textContent).toBe('1')
  })

  it('localStorage\'daki veri bozuksa (geçersiz JSON) hatayı loglar ve boş başlar', () => {
    localStorage.setItem(STORAGE_KEY, '{bozuk-json')
    renderChat()
    expect(screen.getByTestId('sessionCount').textContent).toBe('0')
    expect(console.error).toHaveBeenCalled()
  })
})

describe('ChatProvider — persistence', () => {
  it('oturum oluşturulunca localStorage\'a yazılır', () => {
    renderChat()
    fireEvent.click(screen.getByText('yeni-oturum'))
    expect(localStorage.getItem(STORAGE_KEY)).not.toBeNull()
  })

  it('tüm oturumlar silinince localStorage anahtarı kaldırılır', () => {
    renderChat()
    fireEvent.click(screen.getByText('yeni-oturum'))
    const sessionId = screen.getByTestId('activeSessionId').textContent!
    fireEvent.click(screen.getByText(`sil-${sessionId}`))
    expect(localStorage.getItem(STORAGE_KEY)).toBeNull()
  })
})

describe('createNewSession', () => {
  it('crypto.randomUUID varsa onu kullanır', () => {
    renderChat()
    fireEvent.click(screen.getByText('yeni-oturum'))
    expect(screen.getByTestId('sessionCount').textContent).toBe('1')
    expect(screen.getByTestId('activeSessionId').textContent).not.toBe('')
  })

  it('crypto.randomUUID yoksa Date.now() tabanlı id üretir', () => {
    vi.stubGlobal('crypto', {})
    renderChat()
    fireEvent.click(screen.getByText('yeni-oturum'))
    expect(screen.getByTestId('sessionCount').textContent).toBe('1')
    expect(screen.getByTestId('activeSessionId').textContent).not.toBe('')
  })
})

describe('loadSession / deleteSession', () => {
  it('loadSession aktif oturumu değiştirir', () => {
    renderChat()
    fireEvent.click(screen.getByText('yeni-oturum'))
    const first = screen.getByTestId('activeSessionId').textContent!
    fireEvent.click(screen.getByText('yeni-oturum'))
    const second = screen.getByTestId('activeSessionId').textContent!
    expect(second).not.toBe(first)

    fireEvent.click(screen.getByText(`yukle-${first}`))
    expect(screen.getByTestId('activeSessionId').textContent).toBe(first)
  })

  it('aktif olmayan bir oturum silinirse aktif oturum değişmez', () => {
    renderChat()
    fireEvent.click(screen.getByText('yeni-oturum'))
    const first = screen.getByTestId('activeSessionId').textContent!
    fireEvent.click(screen.getByText('yeni-oturum'))
    const second = screen.getByTestId('activeSessionId').textContent!

    fireEvent.click(screen.getByText(`sil-${first}`))
    expect(screen.getByTestId('activeSessionId').textContent).toBe(second)
    expect(screen.getByTestId('sessionCount').textContent).toBe('1')
  })

  it('aktif oturum silinirse activeSessionId sıfırlanır', () => {
    renderChat()
    fireEvent.click(screen.getByText('yeni-oturum'))
    const active = screen.getByTestId('activeSessionId').textContent!
    fireEvent.click(screen.getByText(`sil-${active}`))
    expect(screen.getByTestId('activeSessionId').textContent).toBe('')
  })
})

describe('handleSendMessage', () => {
  it('hiç aktif oturum yokken kısa mesaj gönderilirse yeni oturum oluşturulur, başlık kısaltılmaz', async () => {
    vi.spyOn(api, 'post').mockResolvedValue({ text: 'yanıt', id: 'ai-1' })
    renderChat()

    fireEvent.click(screen.getByText('gonder-kisa'))

    await waitFor(() => expect(screen.getByTestId('isTyping').textContent).toBe('false'))
    expect(screen.getByTestId('sessionCount').textContent).toBe('1')
    expect(screen.getByTestId('activeTitle').textContent).toBe('kısa mesaj')
    expect(screen.getByTestId('messageCount').textContent).toBe('2') // kullanıcı + AI
    expect(screen.getByTestId('lastMessageText').textContent).toBe('yanıt')
  })

  it('30 karakterden uzun ilk mesaj başlığı "..." ile kısaltır', async () => {
    vi.spyOn(api, 'post').mockResolvedValue({ text: 'yanıt', id: 'ai-2' })
    renderChat()

    fireEvent.click(screen.getByText('gonder-uzun'))

    await waitFor(() => expect(screen.getByTestId('isTyping').textContent).toBe('false'))
    const title = screen.getByTestId('activeTitle').textContent!
    expect(title.endsWith('...')).toBe(true)
    expect(title.length).toBe(33) // 30 karakter + '...'
  })

  it('aynı oturuma ikinci mesaj gönderilince başlık değişmez', async () => {
    vi.spyOn(api, 'post').mockResolvedValue({ text: 'yanıt', id: 'ai-3' })
    renderChat()

    fireEvent.click(screen.getByText('gonder-kisa'))
    await waitFor(() => expect(screen.getByTestId('isTyping').textContent).toBe('false'))
    const titleAfterFirst = screen.getByTestId('activeTitle').textContent

    fireEvent.click(screen.getByText('gonder-uzun'))
    await waitFor(() => expect(screen.getByTestId('messageCount').textContent).toBe('4'))
    expect(screen.getByTestId('activeTitle').textContent).toBe(titleAfterFirst)
  })

  it('birden fazla oturum varken sadece aktif olan güncellenir, diğeri değişmeden kalır', async () => {
    vi.spyOn(api, 'post').mockResolvedValue({ text: 'yanıt', id: 'ai-4' })
    renderChat()

    fireEvent.click(screen.getByText('yeni-oturum'))
    const first = screen.getByTestId('activeSessionId').textContent!
    fireEvent.click(screen.getByText('yeni-oturum'))

    fireEvent.click(screen.getByText('gonder-kisa'))
    await waitFor(() => expect(screen.getByTestId('isTyping').textContent).toBe('false'))

    fireEvent.click(screen.getByText(`yukle-${first}`))
    expect(screen.getByTestId('messageCount').textContent).toBe('0')
  })

  it('backend context_topic dönerse activeContext güncellenir', async () => {
    vi.spyOn(api, 'post').mockResolvedValue({ text: 'yanıt', id: 'ai-5', context_topic: 'portfoy' })
    renderChat()

    fireEvent.click(screen.getByText('gonder-kisa'))

    await waitFor(() => expect(screen.getByTestId('activeContext').textContent).toBe('portfoy'))
  })

  it('backend ne final_output ne de text dönerse varsayılan hata metni gösterilir', async () => {
    vi.spyOn(api, 'post').mockResolvedValue({ id: 'ai-bos' })
    renderChat()

    fireEvent.click(screen.getByText('gonder-kisa'))

    await waitFor(() => expect(screen.getByTestId('lastMessageText').textContent).toBe('Yanıt alınamadı.'))
  })

  it('backend id dönmezse ve crypto mevcutsa crypto.randomUUID ile id üretilir', async () => {
    vi.spyOn(api, 'post').mockResolvedValue({ text: 'id\'siz ama crypto var' })
    renderChat()

    fireEvent.click(screen.getByText('gonder-kisa'))

    await waitFor(() => expect(screen.getByTestId('lastMessageText').textContent).toBe('id\'siz ama crypto var'))
  })

  it('backend id dönmezse ve crypto yoksa Date.now() tabanlı id üretilir', async () => {
    vi.stubGlobal('crypto', {})
    vi.spyOn(api, 'post').mockResolvedValue({ text: 'id\'siz yanıt' })
    renderChat()

    fireEvent.click(screen.getByText('gonder-kisa'))

    await waitFor(() => expect(screen.getByTestId('lastMessageText').textContent).toBe('id\'siz yanıt'))
  })

  it('backend isteği başarısız olursa kullanıcıya hata mesajı gösterilir (crypto olmadan da)', async () => {
    vi.stubGlobal('crypto', {})
    vi.spyOn(api, 'post').mockRejectedValue(new Error('sunucu çökük'))
    renderChat()

    fireEvent.click(screen.getByText('gonder-kisa'))

    await waitFor(() => expect(screen.getByTestId('isTyping').textContent).toBe('false'))
    expect(screen.getByTestId('lastMessageText').textContent).toContain('bağlanamıyorum')
    expect(console.error).toHaveBeenCalledWith('AI Error:', expect.any(Error))
  })

  it('hata durumunda birden fazla oturum varken sadece aktif olan güncellenir', async () => {
    vi.spyOn(api, 'post').mockRejectedValue(new Error('sunucu çökük'))
    renderChat()

    fireEvent.click(screen.getByText('yeni-oturum'))
    const first = screen.getByTestId('activeSessionId').textContent!
    fireEvent.click(screen.getByText('yeni-oturum'))

    fireEvent.click(screen.getByText('gonder-kisa'))
    await waitFor(() => expect(screen.getByTestId('isTyping').textContent).toBe('false'))

    fireEvent.click(screen.getByText(`yukle-${first}`))
    expect(screen.getByTestId('messageCount').textContent).toBe('0')
  })

  it('yanıt gecikirse "düşünme" adımları sırayla ilerler ve süre dolunca durur', async () => {
    vi.useFakeTimers()
    const pending = deferred<{ text: string; id: string }>()
    vi.spyOn(api, 'post').mockReturnValue(pending.promise)

    renderChat()

    await act(async () => {
      fireEvent.click(screen.getByText('gonder-kisa'))
    })

    expect(screen.getByTestId('isTyping').textContent).toBe('true')

    // 5 kez (4000ms) ilerleterek 4 düşünme adımını da tüketip interval'in
    // "step < thoughts.length" false dalına da uğramasını sağla
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5 * 800)
    })
    expect(screen.getByTestId('currentThought').textContent).toBe('Yanıt oluşturuluyor...')

    await act(async () => {
      pending.resolve({ text: 'geç yanıt', id: 'ai-6' })
      await vi.advanceTimersByTimeAsync(0)
    })

    expect(screen.getByTestId('isTyping').textContent).toBe('false')
    expect(screen.getByTestId('currentThought').textContent).toBe('')
    expect(screen.getByTestId('lastMessageText').textContent).toBe('geç yanıt')
  })
})
