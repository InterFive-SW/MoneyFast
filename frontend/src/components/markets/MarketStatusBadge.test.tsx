import { act, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import MarketStatusBadge from './MarketStatusBadge'

// UTC anları; İstanbul (UTC+3, DST yok) ve New York (Ağustos'ta EDT, UTC-4) yerel
// saatlerine bilerek çeviriliyor — isSessionOpen'ın her dalını (hafta içi/hafta sonu,
// açılış öncesi/esnası/sonrası) iki farklı seans üzerinden tek tek tetiklemek için.
const WED_BIST_OPEN_ABD_BEFORE_OPEN = new Date('2026-08-19T10:00:00Z') // İst 13:00 Çrş, NY 06:00 Çrş
const WED_BEFORE_BOTH_OPEN = new Date('2026-08-19T05:00:00Z')          // İst 08:00 Çrş, NY 01:00 Çrş
const WED_BIST_CLOSED_ABD_OPEN = new Date('2026-08-19T17:00:00Z')      // İst 20:00 Çrş, NY 13:00 Çrş
const SATURDAY_BOTH_CLOSED = new Date('2026-08-15T12:00:00Z')          // İst 15:00 Cts, NY 08:00 Cts

beforeEach(() => {
  vi.useFakeTimers()
})

afterEach(() => {
  vi.useRealTimers()
})

describe('MarketStatusBadge', () => {
  it('BIST açıkken ve ABD açılıştan önceyken doğru rozetleri gösterir', () => {
    vi.setSystemTime(WED_BIST_OPEN_ABD_BEFORE_OPEN)
    render(<MarketStatusBadge />)
    expect(screen.getByText('BIST Açık')).toBeInTheDocument()
    expect(screen.getByText('ABD Kapalı')).toBeInTheDocument()
  })

  it('her iki seans açılıştan önceyken ikisi de kapalı gösterilir', () => {
    vi.setSystemTime(WED_BEFORE_BOTH_OPEN)
    render(<MarketStatusBadge />)
    expect(screen.getByText('BIST Kapalı')).toBeInTheDocument()
    expect(screen.getByText('ABD Kapalı')).toBeInTheDocument()
  })

  it('BIST kapanış sonrasıyken ve ABD açıkken doğru rozetleri gösterir', () => {
    vi.setSystemTime(WED_BIST_CLOSED_ABD_OPEN)
    render(<MarketStatusBadge />)
    expect(screen.getByText('BIST Kapalı')).toBeInTheDocument()
    expect(screen.getByText('ABD Açık')).toBeInTheDocument()
  })

  it('hafta sonu her iki seans da kapalı gösterilir', () => {
    vi.setSystemTime(SATURDAY_BOTH_CLOSED)
    render(<MarketStatusBadge />)
    expect(screen.getByText('BIST Kapalı')).toBeInTheDocument()
    expect(screen.getByText('ABD Kapalı')).toBeInTheDocument()
  })

  it('30 saniyede bir günceller ve unmount olunca temizlenir', () => {
    vi.setSystemTime(WED_BIST_OPEN_ABD_BEFORE_OPEN)
    const { unmount } = render(<MarketStatusBadge />)
    act(() => {
      vi.advanceTimersByTime(30_000)
    })
    expect(screen.getByText('BIST Açık')).toBeInTheDocument()
    expect(() => unmount()).not.toThrow()
  })
})
