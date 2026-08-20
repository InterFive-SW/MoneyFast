import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import NewCardWizard from './NewCardWizard'
import type { BankAccount } from '../../data/mockBankingData'
import type { BankingContextType } from '../../pages/Banking'

const navigateMock = vi.fn()
const handleCardCreate = vi.fn()
let mockAccounts: BankAccount[]

vi.mock('react-router-dom', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router-dom')>()
  return {
    ...actual,
    useNavigate: () => navigateMock,
    useOutletContext: () => ({
      data: { accounts: mockAccounts },
      handleCardCreate,
    } as Partial<BankingContextType>),
  }
})

const accounts: BankAccount[] = [
  { id: 'acc-1', name: 'Vadesiz Maaş Hesabı', type: 'checking', balance: 12500.5, currency: 'TRY', accountNumber: 'TR120006200000012345' },
  { id: 'acc-2', name: 'Birikim Hesabı', type: 'savings', balance: 130000, currency: 'TRY', accountNumber: 'TR120006200009876543' },
]

beforeEach(() => {
  navigateMock.mockClear()
  handleCardCreate.mockClear()
  mockAccounts = accounts
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('NewCardWizard', () => {
  it('1. adımda geri tıklanınca /banking/cards\'a yönlendirir', () => {
    render(<NewCardWizard />)
    fireEvent.click(screen.getAllByRole('button')[0])
    expect(navigateMock).toHaveBeenCalledWith('/banking/cards')
  })

  it('kart tipi seçilmeden Devam Et devre dışı kalır', () => {
    render(<NewCardWizard />)
    expect(screen.getByText('Devam Et')).toBeDisabled()
    fireEvent.click(screen.getByText('Kredi Kartı'))
    expect(screen.getByText('Devam Et')).toBeEnabled()
  })

  it('kredi kartı akışı: isim, fiziksel+visa, limit ayarı ile tamamlanır', () => {
    render(<NewCardWizard />)
    fireEvent.click(screen.getByText('Kredi Kartı'))
    fireEvent.click(screen.getByText('Devam Et'))

    expect(screen.getByText('Devam Et')).toBeDisabled()
    fireEvent.change(screen.getByPlaceholderText('Örn: İnternet Alışveriş Kartım'), { target: { value: 'Alışveriş Kartım' } })
    expect(screen.getByText('Devam Et')).toBeEnabled()

    fireEvent.click(screen.getByText('Fiziksel Kart'))
    fireEvent.click(screen.getByText('Visa'))
    fireEvent.click(screen.getByText('Devam Et'))

    expect(screen.getByText('Limit Belirleme')).toBeInTheDocument()
    fireEvent.change(screen.getByRole('slider'), { target: { value: '25000' } })
    expect(screen.getByText('25.000 ₺')).toBeInTheDocument()

    fireEvent.click(screen.getByText('Başvuruyu Tamamla'))
    expect(handleCardCreate).toHaveBeenCalledWith('credit', 'visa', 25000, false, 'Alışveriş Kartım', undefined)
    expect(screen.getByText('Kart Başvurunuz Alınmıştır')).toBeInTheDocument()
    expect(screen.getByText(/Fiziksel kart başvurunuz alınmıştır/)).toBeInTheDocument()

    fireEvent.click(screen.getByText('Kartlarıma Dön'))
    expect(navigateMock).toHaveBeenCalledWith('/banking/cards')
  })

  it('banka kartı akışı: hesap seçimi ile tamamlanır, dijital başarı mesajı gösterilir', () => {
    render(<NewCardWizard />)
    fireEvent.click(screen.getByText('Banka Kartı'))
    fireEvent.click(screen.getByText('Devam Et'))

    fireEvent.change(screen.getByPlaceholderText('Örn: İnternet Alışveriş Kartım'), { target: { value: 'Günlük Kart' } })
    fireEvent.click(screen.getByText('Dijital Kart'))
    fireEvent.click(screen.getByText('Mastercard'))
    fireEvent.click(screen.getByText('Devam Et'))

    expect(screen.getByText('Hesap Seçimi')).toBeInTheDocument()
    fireEvent.click(screen.getByText('Birikim Hesabı'))
    fireEvent.click(screen.getByText('Başvuruyu Tamamla'))

    expect(handleCardCreate).toHaveBeenCalledWith('debit', 'mastercard', 0, true, 'Günlük Kart', 'acc-2')
    expect(screen.getByText(/Dijital kartınız anında oluşturuldu/)).toBeInTheDocument()
  })

  it('hesap yokken banka kartı adımı Başvuruyu Tamamla devre dışı kalır', () => {
    mockAccounts = []
    render(<NewCardWizard />)
    fireEvent.click(screen.getByText('Banka Kartı'))
    fireEvent.click(screen.getByText('Devam Et'))
    fireEvent.change(screen.getByPlaceholderText('Örn: İnternet Alışveriş Kartım'), { target: { value: 'Kart' } })
    fireEvent.click(screen.getByText('Devam Et'))
    expect(screen.getByText('Başvuruyu Tamamla')).toBeDisabled()
  })

  it('2. adımda Geri butonu 1. adıma döner', () => {
    render(<NewCardWizard />)
    fireEvent.click(screen.getByText('Kredi Kartı'))
    fireEvent.click(screen.getByText('Devam Et'))
    fireEvent.click(screen.getByText('Geri'))
    expect(screen.getByText('Kart Tipini Seçin')).toBeInTheDocument()
  })

  it('stepper üzerinden tamamlanmış bir adıma geri dönülebilir, ileri adıma tıklamak etkisiz kalır', () => {
    render(<NewCardWizard />)
    fireEvent.click(screen.getByText('Kredi Kartı'))
    fireEvent.click(screen.getByText('Devam Et'))
    fireEvent.change(screen.getByPlaceholderText('Örn: İnternet Alışveriş Kartım'), { target: { value: 'Kart' } })
    fireEvent.click(screen.getByText('Devam Et'))
    expect(screen.getByText('Limit Belirleme')).toBeInTheDocument()

    // step 3'teyken, tamamlanmış step 1'e (KART TİPİ) tıklamak geri dönmeli
    fireEvent.click(screen.getByText('KART TİPİ'))
    expect(screen.getByText('Kart Tipini Seçin')).toBeInTheDocument()

    // step 1'deyken, henüz gelinmemiş step 3'e (LİMİT / HESAP SEÇİMİ) tıklamak etkisiz kalmalı
    fireEvent.click(screen.getByText('LİMİT / HESAP SEÇİMİ'))
    expect(screen.getByText('Kart Tipini Seçin')).toBeInTheDocument()
  })
})
