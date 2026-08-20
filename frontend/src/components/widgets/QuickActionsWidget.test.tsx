import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import QuickActionsWidget from './QuickActionsWidget'

describe('QuickActionsWidget', () => {
  it('tüm hızlı işlem butonlarını render eder', () => {
    render(<QuickActionsWidget />)
    for (const label of ['Para Gönder', 'Fatura Öde', 'Döviz Al/Sat', 'Kredi Çek']) {
      expect(screen.getByText(label)).toBeInTheDocument()
    }
  })
})
