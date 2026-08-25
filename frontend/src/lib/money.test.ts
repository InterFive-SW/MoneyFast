/**
 * Money formatting.
 *
 * The rule under test: a number never appears without the unit that makes it
 * readable, and a currency we cannot convert is never quietly treated as
 * lira. Buying AAPL used to show "₺314,88" for a dollar-priced stock.
 */
import { describe, expect, it } from 'vitest'
import {
  baseEquivalent, convert, currencySymbol, formatAmount, formatMoney, formatWithBase,
} from './money'

const RATES = { USD: 47.9479, EUR: 56.0921 }

describe('currencySymbol', () => {
  it.each([['TRY', '₺'], ['USD', '$'], ['EUR', '€']])('maps %s to %s', (code, symbol) => {
    expect(currencySymbol(code)).toBe(symbol)
  })

  it('is case-insensitive', () => {
    expect(currencySymbol('usd')).toBe('$')
  })

  it('falls back to the code rather than guessing a symbol', () => {
    // A wrong symbol is a wrong claim about the number; an unfamiliar code is
    // merely unfamiliar.
    expect(currencySymbol('GBP')).toBe('GBP')
  })
})

describe('formatMoney', () => {
  it('leads with the lira sign', () => {
    expect(formatMoney(301.25, 'TRY')).toBe('₺301,25')
  })

  it('trails other symbols after the number', () => {
    expect(formatMoney(314.88, 'USD')).toBe('314,88 $')
  })

  it('groups thousands the Turkish way', () => {
    expect(formatMoney(1087833.96, 'TRY')).toBe('₺1.087.833,96')
  })

  it('always shows two decimals', () => {
    expect(formatMoney(300, 'TRY')).toBe('₺300,00')
  })

  it('defaults to the base currency when none is given', () => {
    expect(formatMoney(10)).toBe('₺10,00')
  })

  it.each([null, undefined, NaN])('renders %p as a dash, not as zero', (value) => {
    // "₺0,00" is a claim that the position is worthless. A dash says we do
    // not have the number.
    expect(formatMoney(value as never)).toBe('—')
  })

  it('keeps a genuine zero', () => {
    expect(formatMoney(0, 'TRY')).toBe('₺0,00')
  })

  it('formats a negative amount', () => {
    expect(formatMoney(-1338.46, 'TRY')).toBe('₺-1.338,46')
  })
})

describe('convert', () => {
  it('converts a foreign amount into lira', () => {
    expect(convert(100, 'USD', 'TRY', RATES)).toBeCloseTo(4794.79, 2)
  })

  it('leaves the base currency untouched without needing a rate', () => {
    expect(convert(100, 'TRY', 'TRY', {})).toBe(100)
  })

  it('converts between two foreign currencies through the base', () => {
    expect(convert(100, 'EUR', 'USD', RATES)).toBeCloseTo(116.99, 1)
  })

  it('returns null when the rate is missing rather than assuming 1.0', () => {
    // Treating 100 USD as 100 TRY understates a holding forty-fold.
    expect(convert(100, 'USD', 'TRY', {})).toBeNull()
    expect(convert(100, 'USD', 'TRY', null)).toBeNull()
  })

  it('returns null for a currency it has never heard of', () => {
    expect(convert(100, 'GBP', 'TRY', RATES)).toBeNull()
  })
})

describe('formatWithBase', () => {
  it('shows a foreign price with its lira equivalent', () => {
    expect(formatWithBase(314.88, 'USD', RATES)).toBe('314,88 $ · ≈₺15.097,83')
  })

  it('does not restate a lira price as itself', () => {
    expect(formatWithBase(301.25, 'TRY', RATES)).toBe('₺301,25')
  })

  it('falls back to the native price when no rate is available', () => {
    // Better an unconverted dollar price than an invented lira one.
    expect(formatWithBase(314.88, 'USD', {})).toBe('314,88 $')
  })

  it('renders a missing amount as a dash', () => {
    expect(formatWithBase(null, 'USD', RATES)).toBe('—')
  })
})

describe('baseEquivalent', () => {
  it('gives just the converted half, for a second line', () => {
    expect(baseEquivalent(314.88, 'USD', RATES)).toBe('≈₺15.097,83')
  })

  it('is empty for a base-currency amount', () => {
    expect(baseEquivalent(301.25, 'TRY', RATES)).toBe('')
  })

  it('is empty when the rate is unavailable', () => {
    expect(baseEquivalent(314.88, 'USD', null)).toBe('')
  })

  it('is empty for a missing amount', () => {
    expect(baseEquivalent(null, 'USD', RATES)).toBe('')
  })
})

describe('formatAmount', () => {
  it('formats without any currency marker', () => {
    expect(formatAmount(1234.5)).toBe('1.234,50')
  })

  it('accepts a wider precision for prices that need it', () => {
    expect(formatAmount(47.9479, 4)).toBe('47,9479')
  })
})

describe('missing currency defaults', () => {
  it('treats an absent currency as the base rather than crashing', () => {
    // Rows from older endpoints may still arrive without one; falling back to
    // lira is right for this system, and it must not throw.
    expect(formatWithBase(100, undefined as never, RATES)).toBe('₺100,00')
    expect(baseEquivalent(100, undefined as never, RATES)).toBe('')
  })

  it('renders an empty symbol for an absent currency code', () => {
    expect(currencySymbol(undefined as never)).toBe('')
  })
})
