import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import MiniTickerWidget from './MiniTickerWidget'
import type { MarketTicker } from '../../data/mockData'

function makeTicker(overrides: Partial<MarketTicker> = {}): MarketTicker {
  return {
    symbol: 'USD/TRY',
    name: 'Amerikan Doları',
    value: 38.54,
    unit: '₺',
    changePercent: 0.32,
    sparkline: [0.5, 0.6],
    ...overrides,
  }
}

describe('MiniTickerWidget', () => {
  it('pozitif değişimde sembolü ve + işaretli yüzdeyi gösterir', () => {
    render(<MiniTickerWidget ticker={makeTicker()} />)
    expect(screen.getByText('USD/TRY')).toBeInTheDocument()
    expect(screen.getByText('+0.32%')).toBeInTheDocument()
  })

  it('negatif değişimde işaretsiz yüzdeyi gösterir', () => {
    render(<MiniTickerWidget ticker={makeTicker({ changePercent: -0.15 })} />)
    expect(screen.getByText('-0.15%')).toBeInTheDocument()
  })
})
