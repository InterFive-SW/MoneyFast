import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import CardSettingsModal from './CardSettingsModal'
import type { CreditCard } from '../../data/mockBankingData'

const digitalCard: CreditCard = {
  id: 'cc-1', name: 'Dijital Kart', brand: 'visa', cardNumber: '**** 1234',
  limit: 100000, currentDebt: 20000, availableLimit: 80000, dueDate: '2026-08-25',
  color: 'from-slate-800 to-slate-900', isDigital: true, settings: { onlineShopping: true, contactless: true, isFrozen: false },
}

const physicalCard: CreditCard = {
  id: 'cc-2', name: 'Fiziksel Kart', brand: 'mastercard', cardNumber: '**** 5678',
  limit: 0, currentDebt: 0, availableLimit: 0, dueDate: '2026-08-25',
  color: 'from-slate-800 to-slate-900', isDigital: false, settings: { onlineShopping: true, contactless: true, isFrozen: true },
}

beforeEach(() => {
  vi.useFakeTimers()
})

afterEach(() => {
  vi.useRealTimers()
  vi.restoreAllMocks()
})

describe('CardSettingsModal', () => {
  it('kapalıyken veya kart yokken hiçbir şey render etmez', () => {
    const { container: c1 } = render(<CardSettingsModal isOpen={false} onClose={vi.fn()} card={digitalCard} updateCard={vi.fn()} />)
    expect(c1).toBeEmptyDOMElement()

    const { container: c2 } = render(<CardSettingsModal isOpen={true} onClose={vi.fn()} card={null} updateCard={vi.fn()} />)
    expect(c2).toBeEmptyDOMElement()
  })

  it('dijital kart için Fiziksel Kart Talebi ve Kart Limit İndirimi seçenekleri gösterilir', () => {
    render(<CardSettingsModal isOpen={true} onClose={vi.fn()} card={digitalCard} updateCard={vi.fn()} />)
    expect(screen.getByText('Fiziksel Kart Talebi')).toBeInTheDocument()
    expect(screen.getByText('Kart Limit İndirimi')).toBeInTheDocument()
  })

  it('fiziksel kart (limit 0, isDigital false) için o seçenekler gösterilmez', () => {
    render(<CardSettingsModal isOpen={true} onClose={vi.fn()} card={physicalCard} updateCard={vi.fn()} />)
    expect(screen.queryByText('Fiziksel Kart Talebi')).not.toBeInTheDocument()
    expect(screen.queryByText('Kart Limit İndirimi')).not.toBeInTheDocument()
  })

  it('X butonu ve backdrop tıklaması onClose çağırır', () => {
    const onClose1 = vi.fn()
    const { container, unmount } = render(<CardSettingsModal isOpen={true} onClose={onClose1} card={digitalCard} updateCard={vi.fn()} />)
    fireEvent.click(container.querySelector('.p-2.-ml-2')!)
    expect(onClose1).toHaveBeenCalled()
    unmount()

    const onClose2 = vi.fn()
    const { container: c2 } = render(<CardSettingsModal isOpen={true} onClose={onClose2} card={digitalCard} updateCard={vi.fn()} />)
    fireEvent.click(c2.querySelector('.absolute.inset-0.bg-black\\/60')!)
    expect(onClose2).toHaveBeenCalled()
  })

  it('PIN belirleme: geçersiz uzunluk, aynı rakam, artan/azalan sıra ve geçerli şifre akışları', () => {
    render(<CardSettingsModal isOpen={true} onClose={vi.fn()} card={digitalCard} updateCard={vi.fn()} />)
    fireEvent.click(screen.getByText('Kart Şifre Belirleme'))
    const input = screen.getByPlaceholderText('****')

    fireEvent.change(input, { target: { value: '12' } })
    fireEvent.click(screen.getByText('Onayla'))
    expect(screen.getByText('Şifre 4 haneli rakamlardan oluşmalıdır.')).toBeInTheDocument()

    fireEvent.change(input, { target: { value: '1111' } })
    fireEvent.click(screen.getByText('Onayla'))
    expect(screen.getByText('Şifre ardışık aynı rakamlardan (örn: 1111) oluşamaz.')).toBeInTheDocument()

    fireEvent.change(input, { target: { value: '1234' } })
    fireEvent.click(screen.getByText('Onayla'))
    expect(screen.getByText('Şifre ardışık rakamlardan (örn: 1234, 9876) oluşamaz.')).toBeInTheDocument()

    fireEvent.change(input, { target: { value: '9876' } })
    fireEvent.click(screen.getByText('Onayla'))
    expect(screen.getByText('Şifre ardışık rakamlardan (örn: 1234, 9876) oluşamaz.')).toBeInTheDocument()

    fireEvent.change(input, { target: { value: '1357' } })
    fireEvent.click(screen.getByText('Onayla'))
    expect(screen.getByText('Kart şifreniz başarıyla güncellendi.')).toBeInTheDocument()
    vi.advanceTimersByTime(2000)
  })

  it('acil durum: kart dondurma ve blokeyi kaldırma updateCard çağırır', () => {
    const updateCard = vi.fn()
    render(<CardSettingsModal isOpen={true} onClose={vi.fn()} card={digitalCard} updateCard={updateCard} />)
    fireEvent.click(screen.getByText('Acil Durum İşlemleri'))
    expect(screen.getByText('Kartınızı geçici olarak kullanıma kapatmak istiyor musunuz?')).toBeInTheDocument()
    fireEvent.click(screen.getByText('Onayla'))
    expect(updateCard).toHaveBeenCalledWith('cc-1', { settings: { isFrozen: true } })
    expect(screen.getByText('Kartınız donduruldu.')).toBeInTheDocument()
  })

  it('acil durum: dondurulmuş kart için blokeyi kaldırma metnini gösterir', () => {
    const updateCard = vi.fn()
    render(<CardSettingsModal isOpen={true} onClose={vi.fn()} card={physicalCard} updateCard={updateCard} />)
    fireEvent.click(screen.getByText('Acil Durum İşlemleri'))
    expect(screen.getByText('Kartınızın geçici blokesini kaldırmak istiyor musunuz?')).toBeInTheDocument()
    fireEvent.click(screen.getByText('Onayla'))
    expect(updateCard).toHaveBeenCalledWith('cc-2', { settings: { isFrozen: false } })
    expect(screen.getByText('Kart blokesi kaldırıldı.')).toBeInTheDocument()
  })

  it('fiziksel kart talebi updateCard çağırır', () => {
    const updateCard = vi.fn()
    render(<CardSettingsModal isOpen={true} onClose={vi.fn()} card={digitalCard} updateCard={updateCard} />)
    fireEvent.click(screen.getByText('Fiziksel Kart Talebi'))
    fireEvent.click(screen.getByText('Onayla'))
    expect(updateCard).toHaveBeenCalledWith('cc-1', { isDigital: false })
    expect(screen.getByText('Fiziksel kart talebiniz alınmıştır.')).toBeInTheDocument()
  })

  it('kart yenileme talebi başarı mesajı gösterir', () => {
    render(<CardSettingsModal isOpen={true} onClose={vi.fn()} card={digitalCard} updateCard={vi.fn()} />)
    fireEvent.click(screen.getByText('Kart Yenileme İşlemleri'))
    fireEvent.click(screen.getByText('Onayla'))
    expect(screen.getByText('Kart yenileme talebiniz başarıyla alındı.')).toBeInTheDocument()
  })

  it('limit indirimi: geçersiz (boş/çok yüksek) ve geçerli değer akışları', () => {
    const updateCard = vi.fn()
    render(<CardSettingsModal isOpen={true} onClose={vi.fn()} card={digitalCard} updateCard={updateCard} />)
    fireEvent.click(screen.getByText('Kart Limit İndirimi'))
    const input = screen.getByPlaceholderText('Örn: 5000')

    fireEvent.click(screen.getByText('Onayla'))
    expect(screen.getByText(/Geçersiz limit/)).toBeInTheDocument()

    fireEvent.change(input, { target: { value: '200000' } })
    fireEvent.click(screen.getByText('Onayla'))
    expect(screen.getByText(/Geçersiz limit/)).toBeInTheDocument()

    fireEvent.change(input, { target: { value: '50000' } })
    fireEvent.click(screen.getByText('Onayla'))
    expect(updateCard).toHaveBeenCalledWith('cc-1', { limit: 50000, availableLimit: 30000 })
    expect(screen.getByText("Kart limitiniz 50000 TL'ye düşürülmüştür.")).toBeInTheDocument()
  })

  it('İptal butonu alt diyaloğu kapatır', () => {
    render(<CardSettingsModal isOpen={true} onClose={vi.fn()} card={digitalCard} updateCard={vi.fn()} />)
    fireEvent.click(screen.getByText('Kart Yenileme İşlemleri'))
    fireEvent.click(screen.getByText('İptal'))
    expect(screen.queryByText('İptal')).not.toBeInTheDocument()
  })

  it('alt diyalog backdrop tıklaması diyaloğu kapatır', () => {
    const { container } = render(<CardSettingsModal isOpen={true} onClose={vi.fn()} card={digitalCard} updateCard={vi.fn()} />)
    fireEvent.click(screen.getByText('Kart Yenileme İşlemleri'))
    fireEvent.click(container.querySelector('.z-\\[60\\] .absolute.inset-0')!)
    expect(screen.queryByText('İptal')).not.toBeInTheDocument()
  })
})
