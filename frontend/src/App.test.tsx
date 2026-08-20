import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import App from './App'

describe('App', () => {
  it('kök rotada (/) Landing sayfasını render eder', () => {
    render(<App />)
    expect(screen.getByText('Paranızı Hızla Yönetin,')).toBeInTheDocument()
  })
})
