import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import AccountsView from './AccountsView'
import type { BankAccount } from '../../data/mockBankingData'
import type { BankingContextType } from '../../pages/Banking'

const navigateMock = vi.fn()
const openCloseAccountModal = vi.fn()
let mockAccounts: BankAccount[]

vi.mock('react-router-dom', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router-dom')>()
  return {
    ...actual,
    useNavigate: () => navigateMock,
    useOutletContext: () => ({
      data: { accounts: mockAccounts },
      openCloseAccountModal,
    } as Partial<BankingContextType>),
  }
})

const checking: BankAccount = { id: 'acc-1', name: 'Vadesiz Maaş Hesabı', type: 'checking', balance: 12500.5, currency: 'TRY', accountNumber: 'TR120006200000012345' }
const savings: BankAccount = { id: 'acc-2', name: 'Birikim Hesabı', type: 'savings', balance: 130000, currency: 'TRY', accountNumber: 'TR120006200009876543' }
const foreign: BankAccount = { id: 'acc-3', name: 'Dolar Hesabı', type: 'foreign_currency', balance: 1200, currency: 'USD', accountNumber: 'TR120006200001234588' }

beforeEach(() => {
  navigateMock.mockClear()
  openCloseAccountModal.mockClear()
  mockAccounts = [checking, savings, foreign]
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('AccountsView', () => {
  it('varsayılan olarak ilk hesabı seçer ve detaylarını gösterir', () => {
    render(<AccountsView />)
    expect(screen.getByText('3 Hesap')).toBeInTheDocument()
    expect(screen.getAllByText('Vadesiz Maaş Hesabı').length).toBeGreaterThan(0)
  })

  it('hesap yoksa boş durum mesajını gösterir', () => {
    mockAccounts = []
    render(<AccountsView />)
    expect(screen.getByText('Detaylarını görmek için soldan bir hesap seçin.')).toBeInTheDocument()
  })

  it('vadeli hesap seçilince Vadeli rozeti ve faiz bilgisi gösterilir', () => {
    render(<AccountsView />)
    fireEvent.click(screen.getByText('Birikim Hesabı'))
    expect(screen.getByText('Faiz Oranı')).toBeInTheDocument()
    expect(screen.getAllByText('Vadeli').length).toBeGreaterThan(0)
  })

  it('döviz hesabı seçilince Döviz hesap türünü gösterir', () => {
    render(<AccountsView />)
    fireEvent.click(screen.getByText('Dolar Hesabı'))
    expect(screen.getByText('Döviz')).toBeInTheDocument()
  })

  it('Menüye Dön, Yeni Hesap Aç, Hesap Hareketleri ve Hesap Kapama butonları doğru aksiyonları tetikler', () => {
    render(<AccountsView />)

    fireEvent.click(screen.getByText('Menüye Dön'))
    expect(navigateMock).toHaveBeenCalledWith('/banking')

    fireEvent.click(screen.getByText('Yeni Hesap Aç'))
    expect(navigateMock).toHaveBeenCalledWith('/banking/new-account')

    fireEvent.click(screen.getByText('Hesap Hareketleri'))
    expect(navigateMock).toHaveBeenCalledWith('/banking/accounts/acc-1/transactions')

    fireEvent.click(screen.getByText('Hesap Kapama'))
    expect(openCloseAccountModal).toHaveBeenCalledWith('acc-1')
  })

  it('yeni hesap eklendiğinde otomatik olarak seçilir', () => {
    mockAccounts = [checking]
    const { rerender } = render(<AccountsView />)
    expect(screen.getByText('1 Hesap')).toBeInTheDocument()

    mockAccounts = [checking, savings]
    rerender(<AccountsView />)
    expect(screen.getByText('Faiz Oranı')).toBeInTheDocument()
  })
})
