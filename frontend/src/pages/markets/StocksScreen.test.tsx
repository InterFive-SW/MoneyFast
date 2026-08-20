import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import StocksScreen from './StocksScreen'

describe('StocksScreen', () => {
  it('kolon seçici, filtre paneli ve enstrüman tablosunu render eder', () => {
    render(
      <MemoryRouter>
        <StocksScreen />
      </MemoryRouter>
    )
    expect(screen.getByText('Enstrümanlar')).toBeInTheDocument()
    expect(screen.getByText('Filtrele')).toBeInTheDocument()
  })
})
