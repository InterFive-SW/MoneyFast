import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import LoanApplicationModal from './LoanApplicationModal'

beforeEach(() => {
  vi.useFakeTimers()
})

afterEach(() => {
  vi.useRealTimers()
})

describe('LoanApplicationModal', () => {
  it('kapalıyken hiçbir şey render etmez', () => {
    const { container } = render(<LoanApplicationModal isOpen={false} onClose={vi.fn()} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('tutar ve vade değiştirilebilir, başvuru sonrası onaya geçer ve onApply çağrılır', () => {
    const onApply = vi.fn()
    render(<LoanApplicationModal isOpen={true} onClose={vi.fn()} onApply={onApply} />)

    const [amountSlider, monthsSlider] = screen.getAllByRole('slider')
    fireEvent.change(amountSlider, { target: { value: '20000' } })
    fireEvent.change(monthsSlider, { target: { value: '24' } })
    expect(screen.getByText('₺20.000')).toBeInTheDocument()
    expect(screen.getByText('24 Ay')).toBeInTheDocument()

    fireEvent.click(screen.getByText('Başvuruyu İlerle'))
    expect(onApply).toHaveBeenCalledWith(20000)
    expect(screen.getByText('Başvurunuz Alındı!')).toBeInTheDocument()
  })

  it('onApply verilmemişse başvuru hata vermez, Kapat onClose çağırır', () => {
    const onClose = vi.fn()
    render(<LoanApplicationModal isOpen={true} onClose={onClose} />)
    fireEvent.click(screen.getByText('Başvuruyu İlerle'))
    fireEvent.click(screen.getByText('Kapat'))
    expect(onClose).toHaveBeenCalled()
    vi.advanceTimersByTime(300)
  })
})
