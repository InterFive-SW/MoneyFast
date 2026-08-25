/**
 * Tooltip formatting.
 *
 * The rule these pin down: a value that is not a number is not zero. Recharts
 * hands the formatter `undefined` for a gap in a series, and rendering that as
 * "0" would draw a day the instrument did not trade as a day it was worthless.
 */
import { describe, expect, it } from 'vitest'
import { seriesName, signedPercent, toNumber } from './chartFormat'

describe('toNumber', () => {
  it('passes a real number through', () => {
    expect(toNumber(12.5)).toBe(12.5)
  })

  it('parses a numeric string, because recharts sometimes hands one over', () => {
    expect(toNumber('12.5')).toBe(12.5)
  })

  it.each([undefined, null, '', '   ', 'abc', NaN, Infinity])(
    'returns null rather than 0 for %p',
    (value) => {
      expect(toNumber(value)).toBeNull()
    },
  )

  it('keeps a genuine zero', () => {
    // Distinct from "no value": 0% change is a measurement.
    expect(toNumber(0)).toBe(0)
  })
})

describe('signedPercent', () => {
  it('marks a gain with a plus so the direction is readable without colour', () => {
    expect(signedPercent(1.2)).toBe('+1.2%')
  })

  it('leaves a loss with its own minus', () => {
    expect(signedPercent(-1.2)).toBe('-1.2%')
  })

  it('does not sign a flat reading', () => {
    expect(signedPercent(0)).toBe('0%')
  })

  it('shows a dash when there is no value, not 0%', () => {
    expect(signedPercent(undefined)).toBe('—')
  })
})

describe('seriesName', () => {
  it('passes a string through', () => {
    expect(seriesName('THYAO')).toBe('THYAO')
  })

  it('stringifies a non-string label', () => {
    expect(seriesName(42)).toBe('42')
  })

  it('renders an absent label as empty rather than "undefined"', () => {
    expect(seriesName(undefined)).toBe('')
    expect(seriesName(null)).toBe('')
  })
})
