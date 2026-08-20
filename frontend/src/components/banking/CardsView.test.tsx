import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import CardsView from './CardsView'
import type { CreditCard } from '../../data/mockBankingData'
import type { BankingContextType } from '../../pages/Banking'

const navigateMock = vi.fn()
const updateCard = vi.fn()
const handleCardCreate = vi.fn()
let mockCards: CreditCard[]

vi.mock('react-router-dom', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router-dom')>()
  return {
    ...actual,
    useNavigate: () => navigateMock,
    useOutletContext: () => ({
      data: { creditCards: mockCards },
      updateCard,
      handleCardCreate,
    } as Partial<BankingContextType>),
  }
})

const physicalMastercard: CreditCard = {
  id: 'cc-1', name: 'Fiziksel Mastercard', brand: 'mastercard', cardNumber: '**** 1111',
  limit: 100000, currentDebt: 20000, availableLimit: 80000, dueDate: '2026-08-25',
  color: 'from-slate-800 to-slate-900', isDigital: false,
  settings: { onlineShopping: true, contactless: true, isFrozen: false },
}

const digitalVisaNoSettings: CreditCard = {
  id: 'cc-2', name: 'Dijital Visa', brand: 'visa', cardNumber: '**** 2222',
  limit: 0, currentDebt: 0, availableLimit: 0, dueDate: '2026-08-28',
  color: 'from-blue-900 to-brandBlue', isDigital: true,
}

const frozenOffCard: CreditCard = {
  id: 'cc-3', name: 'Kapalı Ayarlar Kartı', brand: 'mastercard', cardNumber: '**** 3333',
  limit: 50000, currentDebt: 1000, availableLimit: 49000, dueDate: '2026-09-01',
  color: 'from-slate-800 to-slate-900', isDigital: false,
  settings: { onlineShopping: false, contactless: false, isFrozen: true },
}

beforeEach(() => {
  navigateMock.mockClear()
  updateCard.mockClear()
  handleCardCreate.mockClear()
  mockCards = [physicalMastercard, digitalVisaNoSettings, frozenOffCard]
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('CardsView', () => {
  it('kart yoksa boş durum mesajını gösterir', () => {
    mockCards = []
    render(<CardsView />)
    expect(screen.getByText('Detaylarını görmek için soldan bir kart seçin.')).toBeInTheDocument()
  })

  it('varsayılan olarak ilk kartı seçer, dijital rozetini ve marka ikonlarını gösterir', () => {
    render(<CardsView />)
    expect(screen.getByText('3 Kart')).toBeInTheDocument()
    expect(screen.getByText('DİJİTAL')).toBeInTheDocument()
    expect(screen.getAllByText('Fiziksel Kart').length).toBeGreaterThan(0)
    expect(screen.getByText(/100\.000,00/)).toBeInTheDocument()
  })

  it('dijital kartı seçince NFC ikonu ve temassız ayarı gizlenir, limit bilgisi banka kartı mesajına döner', () => {
    render(<CardsView />)
    fireEvent.click(screen.getByText('Dijital Visa'))
    expect(screen.getByText('DİJİTAL KART')).toBeInTheDocument()
    expect(screen.getByText('Dijital Kart')).toBeInTheDocument()
    expect(screen.queryByText('Temassız Ödeme')).not.toBeInTheDocument()
    expect(screen.getByText('Banka kartınızın limiti doğrudan bağlı olduğu vadesiz hesabınızın bakiyesidir.')).toBeInTheDocument()
  })

  it('kapalı ayarlı karta geçince toggle\'lar kapalı görünür ve tıklanınca updateCard çağrılır', () => {
    render(<CardsView />)
    fireEvent.click(screen.getByText('Kapalı Ayarlar Kartı'))

    fireEvent.click(screen.getByText('İnternet Alışverişi').closest('.justify-between')!.querySelector('.cursor-pointer')!)
    expect(updateCard).toHaveBeenCalledWith('cc-3', { settings: { onlineShopping: true } })

    fireEvent.click(screen.getByText('Temassız Ödeme').closest('.justify-between')!.querySelector('.cursor-pointer')!)
    expect(updateCard).toHaveBeenCalledWith('cc-3', { settings: { contactless: true } })

    fireEvent.click(screen.getByText('Kartı Dondur').closest('.justify-between')!.querySelector('.cursor-pointer')!)
    expect(updateCard).toHaveBeenCalledWith('cc-3', { settings: { isFrozen: false } })
  })

  it('ayarlar tanımsız bir kartta toggle varsayılan açık davranır', () => {
    render(<CardsView />)
    fireEvent.click(screen.getByText('Dijital Visa'))
    fireEvent.click(screen.getByText('İnternet Alışverişi').closest('.justify-between')!.querySelector('.cursor-pointer')!)
    expect(updateCard).toHaveBeenCalledWith('cc-2', { settings: { onlineShopping: false } })
  })

  it('Menüye Dön ve Yeni Kart Başvurusu doğru rotalara yönlendirir', () => {
    render(<CardsView />)
    fireEvent.click(screen.getByText('Menüye Dön'))
    expect(navigateMock).toHaveBeenCalledWith('/banking')

    fireEvent.click(screen.getByText('Yeni Kart Başvurusu'))
    expect(navigateMock).toHaveBeenCalledWith('/banking/new-card')
  })

  it('Tüm Kart Ayarları modalı açar ve kapatılabilir', () => {
    const { container } = render(<CardsView />)
    fireEvent.click(screen.getByText('Tüm Kart Ayarları'))
    expect(screen.getByText('Kart Şifre Belirleme')).toBeInTheDocument()

    fireEvent.click(container.querySelector('.p-2.-ml-2')!)
    expect(screen.queryByText('Kart Şifre Belirleme')).not.toBeInTheDocument()
  })

  it('seçili kart listeden kaldırılırsa otomatik olarak son karta geçer', () => {
    const { rerender } = render(<CardsView />)
    fireEvent.click(screen.getByText('Dijital Visa'))
    expect(screen.getByText('DİJİTAL KART')).toBeInTheDocument()

    mockCards = [physicalMastercard, frozenOffCard]
    rerender(<CardsView />)
    expect(screen.getAllByText('Kapalı Ayarlar Kartı').length).toBeGreaterThan(0)
  })
})
