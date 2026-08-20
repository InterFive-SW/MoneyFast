import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import FeatureNotReadyModal from './FeatureNotReadyModal'

describe('FeatureNotReadyModal', () => {
  it('kapalıyken hiçbir şey render etmez', () => {
    const { container } = render(
      <FeatureNotReadyModal isOpen={false} onClose={vi.fn()} featureName="Fatura Öde" />
    )
    expect(container).toBeEmptyDOMElement()
  })

  it('açıkken özellik adını gösterir ve Anladım butonuna basınca onClose çağrılır', () => {
    const onClose = vi.fn()
    render(<FeatureNotReadyModal isOpen={true} onClose={onClose} featureName="Fatura Öde" />)
    expect(screen.getByText('Fatura Öde')).toBeInTheDocument()

    fireEvent.click(screen.getByText('Anladım'))
    expect(onClose).toHaveBeenCalled()
  })
})
