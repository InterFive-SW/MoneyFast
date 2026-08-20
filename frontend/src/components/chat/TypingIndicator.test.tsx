import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import TypingIndicator from './TypingIndicator'

describe('TypingIndicator', () => {
  it('düşünce metni verilmezse yalnızca sıçrayan noktaları gösterir', () => {
    const { container } = render(<TypingIndicator />)
    expect(container.querySelectorAll('.animate-bounce').length).toBe(3)
  })

  it('düşünce metni verilirse onu da gösterir', () => {
    render(<TypingIndicator thought="Portföy verileri analiz ediliyor..." />)
    expect(screen.getByText('Portföy verileri analiz ediliyor...')).toBeInTheDocument()
  })
})
