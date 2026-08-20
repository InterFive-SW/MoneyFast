import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import Investment from './Investment'

describe('Investment', () => {
  it('başlığı, piyasa durumu rozetlerini ve alt navigasyonu render eder', () => {
    render(
      <MemoryRouter>
        <Investment />
      </MemoryRouter>
    )
    expect(screen.getByText('Piyasalar')).toBeInTheDocument()
    expect(screen.getByText('Hisseler')).toBeInTheDocument()
  })
})
