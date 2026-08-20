import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import CloseAccountModal from './CloseAccountModal'
import type { BankAccount } from '../../data/mockBankingData'

const account: BankAccount = {
  id: 'acc-1',
  name: 'Vadesiz Maaş Hesabı',
  type: 'checking',
  balance: 12500.5,
  currency: 'TRY',
  accountNumber: 'TR12 0006 2000 0001 2345 67',
}

describe('CloseAccountModal', () => {
  it('kapalıyken hiçbir şey render etmez', () => {
    const { container } = render(
      <CloseAccountModal isOpen={false} onClose={vi.fn()} account={account} onConfirm={vi.fn()} />
    )
    expect(container).toBeEmptyDOMElement()
  })

  it('account null iken hiçbir şey render etmez', () => {
    const { container } = render(
      <CloseAccountModal isOpen={true} onClose={vi.fn()} account={null} onConfirm={vi.fn()} />
    )
    expect(container).toBeEmptyDOMElement()
  })

  it('bakiye pozitifken uyarı notunu gösterir, İptal Et onClose çağırır', () => {
    const onClose = vi.fn()
    render(<CloseAccountModal isOpen={true} onClose={onClose} account={account} onConfirm={vi.fn()} />)
    expect(screen.getByText(/toplam varlıklarınızdan düşülecektir/)).toBeInTheDocument()

    fireEvent.click(screen.getByText('İptal Et'))
    expect(onClose).toHaveBeenCalled()
  })

  it('bakiye sıfırken uyarı notu gösterilmez', () => {
    render(
      <CloseAccountModal
        isOpen={true}
        onClose={vi.fn()}
        account={{ ...account, balance: 0 }}
        onConfirm={vi.fn()}
      />
    )
    expect(screen.queryByText(/toplam varlıklarınızdan düşülecektir/)).not.toBeInTheDocument()
  })

  it('Hesabı Kapat tıklanınca onConfirm ve onClose çağrılır', () => {
    const onConfirm = vi.fn()
    const onClose = vi.fn()
    render(<CloseAccountModal isOpen={true} onClose={onClose} account={account} onConfirm={onConfirm} />)
    fireEvent.click(screen.getByText('Hesabı Kapat'))
    expect(onConfirm).toHaveBeenCalledWith('acc-1')
    expect(onClose).toHaveBeenCalled()
  })
})
