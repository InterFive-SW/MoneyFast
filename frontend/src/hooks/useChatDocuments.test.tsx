/**
 * Sohbete yüklenen belgeler.
 *
 * En önemli iddia silmenin İYİMSER OLMAMASI: silme başarısız olduğunda belge
 * hâlâ aranabilir durumdadır ve onu listeden düşürmek, kullanıcıya
 * sildiğini söylemek olur.
 */
import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { apiClient } from '../api/client'
import { DELETE_ERROR, LOAD_ERROR, formatSize, useChatDocuments } from './useChatDocuments'

const DOC = {
  id: 'doc-1', filename: 'bilanco.pdf', kind: 'PDF', size_bytes: 2048,
  units: 12, char_count: 4096, truncated: false,
  created_at: '2026-08-31T10:00:00Z',
}

function mockList(documents = [DOC], accepted = ['.pdf', '.csv']) {
  return vi.spyOn(apiClient, 'getChatDocuments').mockResolvedValue({
    documents, accepted, max_bytes: 10 * 1024 * 1024,
  })
}

const file = (name = 'a.pdf') => new File(['x'], name, { type: 'application/pdf' })

describe('useChatDocuments', () => {
  afterEach(() => vi.restoreAllMocks())

  it('yüklenmiş belgeleri açılışta getirir', async () => {
    mockList()
    const { result } = renderHook(() => useChatDocuments())
    await waitFor(() => expect(result.current.documents).toHaveLength(1))
    expect(result.current.maxBytes).toBe(10 * 1024 * 1024)
  })

  it('kabul edilen uzantıları sunucudan alır', async () => {
    /* Elle yazılmış bir kopya ayrışırsa, seçilebilen ama reddedilen bir
       dosya olur. */
    mockList([], ['.pdf', '.xlsx', '.txt'])
    const { result } = renderHook(() => useChatDocuments())
    await waitFor(() => expect(result.current.accepted).toEqual(['.pdf', '.xlsx', '.txt']))
  })

  it('sunucu liste vermezse yerleşik listeye düşer', async () => {
    mockList([], [])
    const { result } = renderHook(() => useChatDocuments())
    await waitFor(() => expect(result.current.accepted).toContain('.pdf'))
  })

  it('liste alınamazsa söyler', async () => {
    vi.spyOn(apiClient, 'getChatDocuments').mockRejectedValue(new Error('boom'))
    const { result } = renderHook(() => useChatDocuments())
    await waitFor(() => expect(result.current.error).toBe(LOAD_ERROR))
  })

  it('yüklenen belgeyi listenin başına koyar', async () => {
    /* Liste yeniden eskiye; yeniden çekmeye gerek kalmıyor. */
    mockList()
    const created = { ...DOC, id: 'doc-2', filename: 'yeni.csv' }
    vi.spyOn(apiClient, 'uploadChatDocument').mockResolvedValue(created)
    const { result } = renderHook(() => useChatDocuments())
    await waitFor(() => expect(result.current.documents).toHaveLength(1))

    await act(async () => { await result.current.upload(file(), 't1') })

    expect(result.current.documents[0].id).toBe('doc-2')
  })

  it('sohbet kimliğini yükleme ile birlikte geçirir', async () => {
    mockList([])
    const upload = vi.spyOn(apiClient, 'uploadChatDocument').mockResolvedValue(DOC)
    const { result } = renderHook(() => useChatDocuments())

    await act(async () => { await result.current.upload(file(), 'thread-9') })

    expect(upload).toHaveBeenCalledWith(expect.any(File), 'thread-9')
  })

  it('sunucunun kendi hata mesajını korur', async () => {
    /* "Bu dosya türü okunamıyor" ile "dosya çok büyük" farklı şeyler ve
       kullanıcının yapacağı şey de farklı. */
    mockList([])
    vi.spyOn(apiClient, 'uploadChatDocument').mockRejectedValue(
      new Error('Dosya 10 MB sınırını aşıyor.'),
    )
    const { result } = renderHook(() => useChatDocuments())

    let ok: boolean | undefined
    await act(async () => { ok = await result.current.upload(file()) })

    expect(ok).toBe(false)
    expect(result.current.error).toContain('10 MB')
  })

  it('hata mesajı olmayan bir başarısızlıkta da bir şey söyler', async () => {
    mockList([])
    vi.spyOn(apiClient, 'uploadChatDocument').mockRejectedValue('kim bilir')
    const { result } = renderHook(() => useChatDocuments())

    await act(async () => { await result.current.upload(file()) })

    expect(result.current.error).toBeTruthy()
  })

  it('silinen belgeyi listeden çıkarır', async () => {
    mockList()
    vi.spyOn(apiClient, 'deleteChatDocument').mockResolvedValue(undefined)
    const { result } = renderHook(() => useChatDocuments())
    await waitFor(() => expect(result.current.documents).toHaveLength(1))

    await act(async () => { await result.current.remove('doc-1') })

    expect(result.current.documents).toHaveLength(0)
  })

  it('silme başarısızsa belgeyi listede BIRAKIR', async () => {
    /* Belge hâlâ aranabilir durumda; listeden düşürmek kullanıcıya
       sildiğini söylemek olurdu. */
    mockList()
    vi.spyOn(apiClient, 'deleteChatDocument').mockRejectedValue(new Error('503'))
    const { result } = renderHook(() => useChatDocuments())
    await waitFor(() => expect(result.current.documents).toHaveLength(1))

    await act(async () => { await result.current.remove('doc-1') })

    expect(result.current.documents).toHaveLength(1)
    expect(result.current.error).toBeTruthy()
  })

  it('mesajsız bir silme hatasında da bir şey söyler', async () => {
    mockList()
    vi.spyOn(apiClient, 'deleteChatDocument').mockRejectedValue('kim bilir')
    const { result } = renderHook(() => useChatDocuments())
    await waitFor(() => expect(result.current.documents).toHaveLength(1))

    await act(async () => { await result.current.remove('doc-1') })

    expect(result.current.error).toBe(DELETE_ERROR)
  })

  it('hata kapatılabilir', async () => {
    vi.spyOn(apiClient, 'getChatDocuments').mockRejectedValue(new Error('boom'))
    const { result } = renderHook(() => useChatDocuments())
    await waitFor(() => expect(result.current.error).toBe(LOAD_ERROR))

    act(() => result.current.dismissError())

    expect(result.current.error).toBeNull()
  })

  it('yükleme sürerken bunu bildirir', async () => {
    mockList([])
    let release: (value: typeof DOC) => void = () => {}
    vi.spyOn(apiClient, 'uploadChatDocument').mockReturnValue(
      new Promise((resolve) => { release = resolve }),
    )
    const { result } = renderHook(() => useChatDocuments())

    let pending: Promise<boolean>
    act(() => { pending = result.current.upload(file()) })
    await waitFor(() => expect(result.current.uploading).toBe(true))

    await act(async () => { release(DOC); await pending })
    expect(result.current.uploading).toBe(false)
  })

  it('yeniden yükleme listeyi tazeler', async () => {
    const list = mockList()
    const { result } = renderHook(() => useChatDocuments())
    await waitFor(() => expect(result.current.documents).toHaveLength(1))

    await act(async () => { await result.current.reload() })

    expect(list.mock.calls.length).toBeGreaterThan(1)
  })
})

describe('formatSize', () => {
  it('bayt, kilobayt ve megabaytı ayırır', () => {
    expect(formatSize(512)).toBe('512 B')
    expect(formatSize(2048)).toBe('2 KB')
    expect(formatSize(3 * 1024 * 1024)).toBe('3.0 MB')
  })
})
