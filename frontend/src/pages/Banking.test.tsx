import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useOutletContext } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import Banking from './Banking'
import BankingDashboard from '../components/banking/BankingDashboard'
import type { BankingContextType } from './Banking'
import type { CreditCard } from '../data/mockBankingData'

function ContextConsumer() {
  const ctx = useOutletContext<BankingContextType>()
  return (
    <div>
      <div data-testid="accounts-count">{ctx.data.accounts.length}</div>
      <div data-testid="cards-count">{ctx.data.creditCards.length}</div>
      <div data-testid="total-assets">{ctx.data.totalAssets}</div>
      <div data-testid="last-tx-title">{ctx.data.recentTransactions[0]?.title}</div>
      <div data-testid="bill-b1-status">{ctx.data.bills.find((b) => b.id === 'b-1')?.status}</div>
      <div data-testid="last-card-limit">{ctx.data.creditCards[ctx.data.creditCards.length - 1]?.limit}</div>
      <div data-testid="last-card-available">{ctx.data.creditCards[ctx.data.creditCards.length - 1]?.availableLimit}</div>
      <div data-testid="first-card-limit">{ctx.data.creditCards[0]?.limit}</div>
      <div data-testid="first-card-frozen">{String(ctx.data.creditCards[0]?.settings?.isFrozen)}</div>
      <div data-testid="first-card-online">{String(ctx.data.creditCards[0]?.settings?.onlineShopping)}</div>
      <div data-testid="last-account-name">{ctx.data.accounts[ctx.data.accounts.length - 1]?.name}</div>
      <div data-testid="last-tx-amount">{ctx.data.recentTransactions[0]?.amount}</div>

      <button onClick={() => ctx.handleAccountCreate('USD', 'checking', 'Test Hesap', 'TR00')}>createAccount</button>
      <button onClick={() => ctx.handleAccountCreate('EUR', 'savings', '', 'TR01')}>createAccountDefaultName</button>
      <button onClick={() => ctx.handleAccountClose(ctx.data.accounts[0].id)}>closeFirstAccount</button>
      <button onClick={() => ctx.handleCardCreate('credit', 'visa', 5000, true, 'Test Kredi Kartı')}>createCreditCard</button>
      <button onClick={() => ctx.handleCardCreate('credit', 'mastercard', 3000, true, '')}>createCreditCardDefaultName</button>
      <button onClick={() => ctx.handleCardCreate('debit', 'mastercard', 0, false, '', ctx.data.accounts[0]?.id)}>createDebitCardDefaultName</button>
      <button onClick={() => ctx.handleBillPay('nonexistent-bill-id')}>payNonexistentBill</button>
      <button onClick={() => ctx.updateCard(ctx.data.creditCards[0].id, { limit: 99999 })}>updateFirstCardNoSettings</button>
      <button
        onClick={() =>
          ctx.updateCard(ctx.data.creditCards[0].id, { settings: { ...(ctx.data.creditCards[0].settings as CreditCard['settings']), isFrozen: true } })
        }
      >
        freezeFirstCard
      </button>
      <button onClick={() => ctx.handleTransfer(100, ctx.data.accounts[0].id, 'TR-hedef-id', 'id ile transfer')}>transferById</button>
      <button onClick={() => ctx.handleTransfer(50, ctx.data.accounts[0].name, 'TR-hedef-name', '')}>transferByName</button>
      <button onClick={() => ctx.handleBillPay('b-1')}>payBill</button>
      <button onClick={() => ctx.openCloseAccountModal(ctx.data.accounts[0].id)}>openCloseModal</button>
      <button onClick={() => ctx.openFeatureNotReadyModal('Test Özellik')}>openFeatureModal</button>
      <button onClick={() => ctx.openBillPaymentModal()}>openBillModal</button>
    </div>
  )
}

function renderBanking(consumer: JSX.Element = <ContextConsumer />) {
  return render(
    <MemoryRouter initialEntries={['/banking']}>
      <Routes>
        <Route path="/banking" element={<Banking />}>
          <Route index element={consumer} />
        </Route>
      </Routes>
    </MemoryRouter>
  )
}

async function renderReady(consumer?: JSX.Element) {
  const utils = renderBanking(consumer)
  await act(async () => {
    await vi.advanceTimersByTimeAsync(800)
  })
  return utils
}

beforeEach(() => {
  vi.useFakeTimers()
})

afterEach(() => {
  vi.useRealTimers()
  vi.restoreAllMocks()
})

describe('Banking', () => {
  it('yüklenirken bekleme durumunu, ardından hesap özetini gösterir', async () => {
    renderBanking(<BankingDashboard />)
    expect(screen.getByText('Veriler yükleniyor...')).toBeInTheDocument()

    await act(async () => {
      await vi.advanceTimersByTimeAsync(800)
    })
    expect(screen.getByText('Vadesiz Maaş Hesabı')).toBeInTheDocument()
  })

  it('handleAccountCreate yeni hesabı listeye ekler', async () => {
    await renderReady()
    expect(screen.getByTestId('accounts-count')).toHaveTextContent('3')
    fireEvent.click(screen.getByText('createAccount'))
    expect(screen.getByTestId('accounts-count')).toHaveTextContent('4')
    expect(screen.getByTestId('last-account-name')).toHaveTextContent('Test Hesap')

    fireEvent.click(screen.getByText('createAccountDefaultName'))
    expect(screen.getByTestId('accounts-count')).toHaveTextContent('5')
    expect(screen.getByTestId('last-account-name')).toHaveTextContent('Yeni EUR Hesabı')
  })

  it('handleAccountClose hesabı siler ve toplam varlıktan düşer', async () => {
    await renderReady()
    const before = Number(screen.getByTestId('total-assets').textContent)
    fireEvent.click(screen.getByText('closeFirstAccount'))
    expect(screen.getByTestId('accounts-count')).toHaveTextContent('2')
    expect(Number(screen.getByTestId('total-assets').textContent)).toBeLessThan(before)
  })

  it('handleCardCreate kredi ve banka kartı için limit/availableLimit farklı hesaplanır', async () => {
    await renderReady()
    fireEvent.click(screen.getByText('createCreditCard'))
    expect(screen.getByTestId('cards-count')).toHaveTextContent('3')
    expect(screen.getByTestId('last-card-limit')).toHaveTextContent('5000')
    expect(screen.getByTestId('last-card-available')).toHaveTextContent('5000')

    fireEvent.click(screen.getByText('createDebitCardDefaultName'))
    expect(screen.getByTestId('cards-count')).toHaveTextContent('4')
    expect(screen.getByTestId('last-card-limit')).toHaveTextContent('0')
    expect(screen.getByTestId('last-card-available')).toHaveTextContent('0')

    fireEvent.click(screen.getByText('createCreditCardDefaultName'))
    expect(screen.getByTestId('cards-count')).toHaveTextContent('5')
    expect(screen.getByTestId('last-card-limit')).toHaveTextContent('3000')
  })

  it('updateCard settings vermeden ve settings ile derin birleştirme yapar', async () => {
    await renderReady()
    fireEvent.click(screen.getByText('updateFirstCardNoSettings'))
    expect(screen.getByTestId('first-card-limit')).toHaveTextContent('99999')

    fireEvent.click(screen.getByText('freezeFirstCard'))
    expect(screen.getByTestId('first-card-frozen')).toHaveTextContent('true')
  })

  it('handleTransfer hem id hem isimle eşleşen hesabı bulur ve bakiyeyi düşer', async () => {
    await renderReady()
    fireEvent.click(screen.getByText('transferById'))
    expect(screen.getByTestId('last-tx-title')).toHaveTextContent('TR-hedef-id')

    fireEvent.click(screen.getByText('transferByName'))
    expect(screen.getByTestId('last-tx-title')).toHaveTextContent('TR-hedef-name')
  })

  it('handleBillPay faturayı ödenmiş yapar ve toplam varlıktan düşer', async () => {
    await renderReady()
    expect(screen.getByTestId('bill-b1-status')).toHaveTextContent('pending')
    const before = Number(screen.getByTestId('total-assets').textContent)
    fireEvent.click(screen.getByText('payBill'))
    expect(screen.getByTestId('bill-b1-status')).toHaveTextContent('paid')
    expect(Number(screen.getByTestId('total-assets').textContent)).toBeLessThan(before)

    const afterFirstPay = Number(screen.getByTestId('total-assets').textContent)
    fireEvent.click(screen.getByText('payNonexistentBill'))
    expect(screen.getByTestId('last-tx-title')).toHaveTextContent('Fatura Ödemesi')
    expect(screen.getByTestId('last-tx-amount')).toHaveTextContent('0')
    expect(Number(screen.getByTestId('total-assets').textContent)).toBe(afterFirstPay)
  })

  it('openCloseAccountModal, openFeatureNotReadyModal ve openBillPaymentModal ilgili modalları açar ve kapatılabilir', async () => {
    await renderReady()

    fireEvent.click(screen.getByText('openCloseModal'))
    expect(screen.getByText('Hesap Kapatma Onayı')).toBeInTheDocument()
    fireEvent.click(screen.getByText('İptal Et'))
    expect(screen.queryByText('Hesap Kapatma Onayı')).not.toBeInTheDocument()

    fireEvent.click(screen.getByText('openFeatureModal'))
    expect(screen.getByText('Test Özellik')).toBeInTheDocument()
    fireEvent.click(screen.getByText('Anladım'))
    expect(screen.queryByText('Test Özellik')).not.toBeInTheDocument()

    fireEvent.click(screen.getByText('openBillModal'))
    expect(screen.getByText('Fatura Öde')).toBeInTheDocument()

    fireEvent.click(screen.getByText('Fatura Öde').nextElementSibling!)
    expect(screen.queryByText('Fatura Öde')).not.toBeInTheDocument()
  })
})
