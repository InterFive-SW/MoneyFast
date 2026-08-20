import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import AccountsSummaryWidget from './AccountsSummaryWidget'
import type { BankAccount } from '../../data/mockBankingData'

const accounts: BankAccount[] = [
  { id: 'acc-1', name: 'Vadesiz Maaş Hesabı', type: 'checking', balance: 12500.5, currency: 'TRY', accountNumber: 'TR120006200000012345' },
  { id: 'acc-2', name: 'Birikim Hesabı', type: 'savings', balance: 130000, currency: 'TRY', accountNumber: 'TR120006200009876543' },
  { id: 'acc-3', name: 'Dolar Hesabı', type: 'foreign_currency', balance: 1200, currency: 'USD', accountNumber: 'TR120006200001234588' },
]

describe('AccountsSummaryWidget', () => {
  it('toplam varlığı ve tüm hesap tiplerine özgü aksiyon butonlarını gösterir', () => {
    render(<AccountsSummaryWidget accounts={accounts} totalAssets={143700.5} onOpenTransfer={vi.fn()} />)
    expect(screen.getByText(/₺143\.700,50/)).toBeInTheDocument()
    expect(screen.getByText('Nakit Avans')).toBeInTheDocument()
    expect(screen.getByText('Hisse Al/Sat')).toBeInTheDocument()
    expect(screen.getByText('Döviz Al/Sat')).toBeInTheDocument()
  })

  it('Para Transferi tıklanınca onOpenTransfer hesap adıyla çağrılır', () => {
    const onOpenTransfer = vi.fn()
    render(<AccountsSummaryWidget accounts={accounts} totalAssets={0} onOpenTransfer={onOpenTransfer} />)
    fireEvent.click(screen.getAllByText('Para Transferi')[0])
    expect(onOpenTransfer).toHaveBeenCalledWith('Vadesiz Maaş Hesabı')
  })

  it('onActionClick verilmemişse aksiyon butonlarına tıklamak hata vermez', () => {
    render(<AccountsSummaryWidget accounts={accounts} totalAssets={0} onOpenTransfer={vi.fn()} />)
    fireEvent.click(screen.getByText('Nakit Avans'))
    fireEvent.click(screen.getByText('Hisse Al/Sat'))
    fireEvent.click(screen.getByText('Döviz Al/Sat'))
  })

  it('onActionClick verilmişse hesap tipine özgü aksiyon adıyla çağrılır', () => {
    const onActionClick = vi.fn()
    render(<AccountsSummaryWidget accounts={accounts} totalAssets={0} onOpenTransfer={vi.fn()} onActionClick={onActionClick} />)
    fireEvent.click(screen.getByText('Nakit Avans'))
    expect(onActionClick).toHaveBeenCalledWith('Nakit Avans')
    fireEvent.click(screen.getByText('Hisse Al/Sat'))
    expect(onActionClick).toHaveBeenCalledWith('Hisse Al/Sat')
    fireEvent.click(screen.getByText('Döviz Al/Sat'))
    expect(onActionClick).toHaveBeenCalledWith('Döviz Al/Sat')
  })
})
