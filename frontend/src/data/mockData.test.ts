import { describe, expect, it } from 'vitest'
import { findFund, findIndex, findInstrument } from './mockData'

describe('findInstrument', () => {
  it('sembol eşleşirse ilgili enstrümanı döner', () => {
    const result = findInstrument('THYAO')
    expect(result?.name).toBe('Türk Hava Yolları')
  })

  it('sembol eşleşmezse undefined döner', () => {
    const result = findInstrument('OLMAYAN-SEMBOL')
    expect(result).toBeUndefined()
  })
})

describe('findFund', () => {
  it('fon kodu eşleşirse ilgili fonu döner', () => {
    const result = findFund('AFT')
    expect(result?.name).toBe('İş Portföy Hisse Senedi Fonu')
  })

  it('fon kodu eşleşmezse undefined döner', () => {
    const result = findFund('OLMAYAN-KOD')
    expect(result).toBeUndefined()
  })
})

describe('findIndex', () => {
  it('endeks kodu eşleşirse ilgili endeksi döner', () => {
    const result = findIndex('XU100')
    expect(result?.name).toBe('BIST 100')
  })

  it('endeks kodu eşleşmezse undefined döner', () => {
    const result = findIndex('OLMAYAN-ENDEKS')
    expect(result).toBeUndefined()
  })
})
