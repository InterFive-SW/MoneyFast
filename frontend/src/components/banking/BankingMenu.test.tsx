import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import BankingMenu, { renderNewBadge } from './BankingMenu'

const navigateMock = vi.fn()
vi.mock('react-router-dom', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router-dom')>()
  return { ...actual, useNavigate: () => navigateMock }
})

function renderMenu() {
  return render(
    <BankingMenu
      onNavigateToAccounts={onNavigateToAccounts}
      onOpenTransfer={onOpenTransfer}
      onOpenBillPayment={onOpenBillPayment}
      onFeatureNotReady={onFeatureNotReady}
    />
  )
}

const onNavigateToAccounts = vi.fn()
const onOpenTransfer = vi.fn()
const onOpenBillPayment = vi.fn()
const onFeatureNotReady = vi.fn()

beforeEach(() => {
  navigateMock.mockClear()
  onNavigateToAccounts.mockClear()
  onOpenTransfer.mockClear()
  onOpenBillPayment.mockClear()
  onFeatureNotReady.mockClear()
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('BankingMenu', () => {
  it('Hesaplarım tıklanınca onNavigateToAccounts çağrılır', () => {
    renderMenu()
    fireEvent.click(screen.getByText('Hesaplarım'))
    expect(onNavigateToAccounts).toHaveBeenCalled()
  })

  it('Para Transferleri tıklanınca onOpenTransfer çağrılır', () => {
    renderMenu()
    fireEvent.click(screen.getByText('Para Transferleri'))
    expect(onOpenTransfer).toHaveBeenCalled()
  })

  it('Kartlarım tıklanınca /banking/cards\'a yönlendirir', () => {
    renderMenu()
    fireEvent.click(screen.getByText('Kartlarım'))
    expect(navigateMock).toHaveBeenCalledWith('/banking/cards')
  })

  it('Krediler tıklanınca onFeatureNotReady çağrılır', () => {
    renderMenu()
    fireEvent.click(screen.getByText('Krediler'))
    expect(onFeatureNotReady).toHaveBeenCalledWith('Krediler')
  })

  it('Ödemeler tıklanınca onOpenBillPayment çağrılır', () => {
    renderMenu()
    fireEvent.click(screen.getByText('Ödemeler'))
    expect(onOpenBillPayment).toHaveBeenCalled()
  })

  it('Yatırım ve Borsa tıklanınca /investment\'a yönlendirir', () => {
    renderMenu()
    fireEvent.click(screen.getByText('Yatırım ve Borsa'))
    expect(navigateMock).toHaveBeenCalledWith('/investment')
  })

  it('Kayıtlı İşlemlerim tıklanınca onFeatureNotReady çağrılır', () => {
    renderMenu()
    fireEvent.click(screen.getByText('Kayıtlı İşlemlerim'))
    expect(onFeatureNotReady).toHaveBeenCalledWith('Kayıtlı İşlemlerim')
  })
})

describe('renderNewBadge', () => {
  it('isNew false ise null döner', () => {
    expect(renderNewBadge(false)).toBeNull()
  })

  it('isNew true ise Yeni etiketini döner', () => {
    render(<div>{renderNewBadge(true)}</div>)
    expect(screen.getByText('Yeni')).toBeInTheDocument()
  })
})
