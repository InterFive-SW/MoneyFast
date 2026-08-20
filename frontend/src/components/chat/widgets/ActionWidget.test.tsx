import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import ActionWidget from './ActionWidget'
import { api } from '../../../api/client'
import type { ActionWidgetPayload } from '../../../types/chat'

const payload: ActionWidgetPayload = {
  message: 'THYAO için 10 adet alım işlemini onaylıyor musunuz?',
  confirmLabel: 'Onayla',
  cancelLabel: 'Vazgeç',
  actionId: 'a1',
  asset: 'THYAO',
  amount: 10,
  action: 'buy',
}

beforeEach(() => {
  vi.spyOn(console, 'error').mockImplementation(() => {})
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('ActionWidget', () => {
  it('mesajı ve onayla/vazgeç butonlarını render eder', () => {
    render(<ActionWidget payload={payload} />)
    expect(screen.getByText(payload.message)).toBeInTheDocument()
    expect(screen.getByText('Onayla')).toBeInTheDocument()
    expect(screen.getByText('Vazgeç')).toBeInTheDocument()
  })

  it('vazgeç butonuna basınca iptal durumunu gösterir', () => {
    render(<ActionWidget payload={payload} />)
    fireEvent.click(screen.getByText('Vazgeç'))
    expect(screen.getByText('İşlem sonlandırıldı.')).toBeInTheDocument()
    expect(screen.getByText('İşlem iptal edildi.')).toBeInTheDocument()
  })

  it('onaylayınca yüklenme durumunu gösterir, ardından başarı mesajı ve toast gösterir', async () => {
    vi.spyOn(api, 'confirmOrder').mockResolvedValue({ message: 'confirmed', status: 'confirmed' })
    render(<ActionWidget payload={payload} />)

    fireEvent.click(screen.getByText('Onayla'))
    expect(document.querySelector('.animate-spin')).not.toBeNull()

    await waitFor(() => expect(screen.getByText('İşlem yetkilendirildi.')).toBeInTheDocument())
    expect(screen.getByText('İşlem başarıyla onaylandı ve sıraya alındı.')).toBeInTheDocument()
  })

  it('onay başarısız olursa pending durumuna döner ve hata toast\'ı gösterir', async () => {
    vi.spyOn(api, 'confirmOrder').mockRejectedValue(new Error('network'))
    render(<ActionWidget payload={payload} />)

    fireEvent.click(screen.getByText('Onayla'))
    await waitFor(() => expect(screen.getByText('İşlem onaylanırken bir hata oluştu. Lütfen tekrar deneyiniz.')).toBeInTheDocument())
    expect(screen.getByText('Onayla')).toBeInTheDocument() // pending'e döndü, butonlar tekrar görünür
  })

  it('onay başarısız olduktan 5 saniye sonra hata toast\'ı kaybolur', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    vi.spyOn(api, 'confirmOrder').mockRejectedValue(new Error('network'))
    render(<ActionWidget payload={payload} />)

    fireEvent.click(screen.getByText('Onayla'))
    await waitFor(() => expect(screen.getByText('İşlem onaylanırken bir hata oluştu. Lütfen tekrar deneyiniz.')).toBeInTheDocument())

    vi.advanceTimersByTime(5000)
    await waitFor(() => expect(screen.queryByText('İşlem onaylanırken bir hata oluştu. Lütfen tekrar deneyiniz.')).not.toBeInTheDocument())

    vi.useRealTimers()
  })
})
