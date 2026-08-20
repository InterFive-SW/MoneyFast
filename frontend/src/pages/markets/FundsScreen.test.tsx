import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import FundsScreen from './FundsScreen'

describe('FundsScreen', () => {
  it('filtre paneli, fon tablosu ve karşılaştırma grafiğini render eder', () => {
    render(
      <MemoryRouter>
        <FundsScreen />
      </MemoryRouter>
    )
    expect(screen.getByText('Fon Listesi')).toBeInTheDocument()
    expect(screen.getByText('Fon Karşılaştır', { exact: false })).toBeInTheDocument()
  })
})
