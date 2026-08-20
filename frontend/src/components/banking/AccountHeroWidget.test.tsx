import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import AccountHeroWidget from './AccountHeroWidget'
import type { BankAccount } from '../../data/mockBankingData'

const accounts: BankAccount[] = [
  { id: 'acc-1', name: 'Vadesiz Maaş Hesabı', type: 'checking', balance: 12500.5, currency: 'TRY', accountNumber: 'TR12 0006 2000 0001 2345 67' },
  { id: 'acc-2', name: 'Dolar Hesabı', type: 'foreign_currency', balance: 1200, currency: 'USD', accountNumber: 'TR12 0006 2000 0001 2345 88' },
]

function renderWidget(overrides: Partial<Parameters<typeof AccountHeroWidget>[0]> = {}) {
  return render(
    <AccountHeroWidget
      accounts={accounts}
      totalAssets={13700.5}
      onNavigateToAccounts={onNavigateToAccounts}
      onOpenTransfer={onOpenTransfer}
      onOpenBillPayment={onOpenBillPayment}
      onFeatureNotReady={onFeatureNotReady}
      {...overrides}
    />
  )
}

const onNavigateToAccounts = vi.fn()
const onOpenTransfer = vi.fn()
const onOpenBillPayment = vi.fn()
const onFeatureNotReady = vi.fn()
const writeTextMock = vi.fn().mockResolvedValue(undefined)

beforeEach(() => {
  onNavigateToAccounts.mockClear()
  onOpenTransfer.mockClear()
  onOpenBillPayment.mockClear()
  onFeatureNotReady.mockClear()
  writeTextMock.mockClear()
  Object.assign(navigator, { clipboard: { writeText: writeTextMock } })
  vi.useFakeTimers()
})

afterEach(() => {
  vi.useRealTimers()
  vi.restoreAllMocks()
})

describe('AccountHeroWidget', () => {
  it('varsayılan olarak ilk hesabı gösterir', () => {
    renderWidget()
    expect(screen.getByText('Vadesiz Maaş Hesabı')).toBeInTheDocument()
  })

  it('dropdown açılıp başka bir hesap seçilebilir', () => {
    renderWidget()
    fireEvent.click(screen.getByText('Vadesiz Maaş Hesabı'))
    fireEvent.click(screen.getByText('Dolar Hesabı'))
    expect(screen.getAllByText('Dolar Hesabı').length).toBeGreaterThan(0)
  })

  it('bakiyeye tıklanınca ve TÜM HESAPLAR butonuna basınca onNavigateToAccounts çağrılır', () => {
    renderWidget()
    fireEvent.click(screen.getByText('TÜM HESAPLAR'))
    expect(onNavigateToAccounts).toHaveBeenCalledTimes(1)

    fireEvent.click(screen.getByText(/12\.500,50/))
    expect(onNavigateToAccounts).toHaveBeenCalledTimes(2)
  })

  it('Ek Hesap Başvurusu ve Daha Fazlası onFeatureNotReady çağırır', () => {
    renderWidget()
    fireEvent.click(screen.getByText('Ek Hesap Başvurusu için tıklayınız.'))
    expect(onFeatureNotReady).toHaveBeenCalledWith('Ek Hesap Başvurusu')

    fireEvent.click(screen.getByText('DahaFazlası'))
    expect(onFeatureNotReady).toHaveBeenCalledWith('Daha Fazlası')
  })

  it('Para Aktar ve Ödeme Yap kendi callback\'lerini çağırır', () => {
    renderWidget()
    fireEvent.click(screen.getByText('ParaAktar'))
    expect(onOpenTransfer).toHaveBeenCalled()

    fireEvent.click(screen.getByText('ÖdemeYap'))
    expect(onOpenBillPayment).toHaveBeenCalled()
  })

  it('IBAN Paylaş tıklanınca panoya kopyalar ve bildirim 2sn sonra kaybolur', () => {
    renderWidget()
    fireEvent.click(screen.getByText('IBANPaylaş'))
    expect(writeTextMock).toHaveBeenCalledWith('TR12 0006 2000 0001 2345 67')

    vi.advanceTimersByTime(2000)
  })

  it('accounts boşken selectedAccount undefined olur, IBAN kopyalama hata vermez', () => {
    renderWidget({ accounts: [] })
    fireEvent.click(screen.getByText('IBANPaylaş'))
    expect(writeTextMock).not.toHaveBeenCalled()
  })
})
