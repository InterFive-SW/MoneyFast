import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import TradeModal from './TradeModal'
import { apiClient } from '../../api/client'

beforeEach(() => {
  vi.spyOn(console, 'error').mockImplementation(() => {})
})

afterEach(() => {
  vi.restoreAllMocks()
})

function getCloseButton() {
  // Kapatma butonunun erişilebilir adı yok (yalnızca X ikonu) — ikonun kendine özgü
  // path çizgisiyle (M18 6 6 18...) bulup en yakın <button>'a çıkıyoruz.
  const path = document.querySelector('path[d="M18 6 6 18M6 6l12 12"]')!
  return path.closest('button')!
}

describe('TradeModal', () => {
  it('sembolü, fiyatı ve varsayılan tahmini tutarı gösterir', () => {
    render(<TradeModal symbol="THYAO" price={295.5} onClose={vi.fn()} />)
    expect(screen.getByText('THYAO')).toBeInTheDocument()
    expect(screen.getAllByText(/295,50/).length).toBeGreaterThan(0)
  })

  it('kapatma butonuna basınca onClose çağrılır', () => {
    const onClose = vi.fn()
    render(<TradeModal symbol="THYAO" price={295.5} onClose={onClose} />)
    fireEvent.click(getCloseButton())
    expect(onClose).toHaveBeenCalled()
  })

  it('Sat butonuna basınca aksiyon değişir, Al\'a dönünce eski hale gelir', () => {
    render(<TradeModal symbol="THYAO" price={295.5} onClose={vi.fn()} />)
    const satBtn = screen.getByText('Sat')
    fireEvent.click(satBtn)
    expect(satBtn.className).toContain('bg-rose-500')

    const alBtn = screen.getByText('Al')
    fireEvent.click(alBtn)
    expect(alBtn.className).toContain('bg-emerald-500')
  })

  it('adet 0 girilirse 1\'e sabitlenir', () => {
    render(<TradeModal symbol="THYAO" price={100} onClose={vi.fn()} />)
    const qtyInput = screen.getAllByRole('spinbutton')[0] as HTMLInputElement
    fireEvent.change(qtyInput, { target: { value: '0' } })
    expect(qtyInput.value).toBe('1')
  })

  it('adet artınca tahmini tutar güncellenir', () => {
    render(<TradeModal symbol="THYAO" price={100} onClose={vi.fn()} />)
    fireEvent.change(screen.getAllByRole('spinbutton')[0], { target: { value: '3' } })
    expect(screen.getByText(/300,00/)).toBeInTheDocument()
  })

  it('limit emri açılınca limit fiyat alanı görünür ve tahmini tutarı etkiler', () => {
    render(<TradeModal symbol="THYAO" price={100} onClose={vi.fn()} />)
    fireEvent.click(screen.getByText('Limit Emri').nextElementSibling!)
    const limitInput = screen.getAllByRole('spinbutton')[1] as HTMLInputElement
    fireEvent.change(limitInput, { target: { value: '90' } })
    expect(screen.getByText(/90,00/)).toBeInTheDocument()
  })

  it('onaylayınca başarılı akış: iki API çağrısı yapılır ve başarı ekranı gösterilir', async () => {
    vi.spyOn(apiClient, 'post')
      .mockResolvedValueOnce({ order_id: 'ORD-1', status: 'proposed' })
      .mockResolvedValueOnce({ message: 'Emriniz alındı.', status: 'confirmed' })

    render(<TradeModal symbol="THYAO" price={100} onClose={vi.fn()} />)
    fireEvent.click(screen.getByText('ONAYLA'))

    expect(screen.getByText('Gönderiliyor...')).toBeInTheDocument()
    await waitFor(() => expect(screen.getByText('Emriniz İletildi')).toBeInTheDocument())
    expect(screen.getByText('Emriniz alındı.')).toBeInTheDocument()

    fireEvent.click(screen.getByText('Kapat'))
  })

  it('onaylama başarısız olursa hata mesajı gösterir', async () => {
    vi.spyOn(apiClient, 'post').mockRejectedValue(new Error('network'))

    render(<TradeModal symbol="THYAO" price={100} onClose={vi.fn()} />)
    fireEvent.click(screen.getByText('ONAYLA'))

    await waitFor(() => expect(screen.getByText('Emir iletilemedi, lütfen tekrar deneyin.')).toBeInTheDocument())
  })
})
