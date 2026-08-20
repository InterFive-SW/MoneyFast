import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import MiniTickerWidget from './MiniTickerWidget'
import type { MarketTicker } from '../../data/mockData'

const navigateMock = vi.fn()
vi.mock('react-router-dom', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router-dom')>()
  return { ...actual, useNavigate: () => navigateMock }
})

beforeEach(() => {
  navigateMock.mockClear()
})

afterEach(() => {
  vi.restoreAllMocks()
})

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

  it('tıklanınca /investment\'a yönlendirir', () => {
    render(<MiniTickerWidget ticker={makeTicker()} />)
    fireEvent.click(screen.getByText('USD/TRY'))
    expect(navigateMock).toHaveBeenCalledWith('/investment')
  })
})
