import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import BankingDashboard from './BankingDashboard'
import type { BankingContextType } from '../../pages/Banking'
import type { BankAccount } from '../../data/mockBankingData'

const navigateMock = vi.fn()
const openFeatureNotReadyModal = vi.fn()
const openBillPaymentModal = vi.fn()

vi.mock('react-router-dom', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router-dom')>()
  return {
    ...actual,
    useNavigate: () => navigateMock,
    useOutletContext: () => ({
      data: {
        accounts: [
          { id: 'acc-1', name: 'Vadesiz Hesap', type: 'checking', balance: 5000, currency: 'TRY', accountNumber: 'TR000001' } as BankAccount,
        ],
        totalAssets: 5000,
      },
      openFeatureNotReadyModal,
      openBillPaymentModal,
    } as Partial<BankingContextType>),
  }
})

beforeEach(() => {
  navigateMock.mockClear()
  openFeatureNotReadyModal.mockClear()
  openBillPaymentModal.mockClear()
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('BankingDashboard', () => {
  it('AccountHeroWidget üzerinden hesaplar ve transfer sayfalarına yönlendirir', () => {
    render(<BankingDashboard />)
    fireEvent.click(screen.getByText('TÜM HESAPLAR'))
    expect(navigateMock).toHaveBeenCalledWith('/banking/accounts')

    fireEvent.click(screen.getByText('ParaAktar'))
    expect(navigateMock).toHaveBeenCalledWith('/banking/transfer')
  })

  it('BankingMenu üzerinden hesaplar ve transfer sayfalarına yönlendirir', () => {
    render(<BankingDashboard />)
    fireEvent.click(screen.getByText('Hesaplarım'))
    expect(navigateMock).toHaveBeenCalledWith('/banking/accounts')

    fireEvent.click(screen.getByText('Para Transferleri'))
    expect(navigateMock).toHaveBeenCalledWith('/banking/transfer')
  })
})
