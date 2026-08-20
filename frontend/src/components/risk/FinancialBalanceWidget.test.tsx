import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import FinancialBalanceWidget, { formatFinancialBalanceTooltip } from './FinancialBalanceWidget'

describe('FinancialBalanceWidget', () => {
  it('borç/gelir oranı %40\'ı geçince kırmızı rozet gösterir', () => {
    render(<FinancialBalanceWidget income={50_000} expense={30_000} debt={25_000} debtToIncomeRatio={50} />)
    const badge = screen.getByText('Borç/Gelir: %50')
    expect(badge.className).toContain('bg-rose-50')
  })

  it('borç/gelir oranı %40 veya altındayken yeşil rozet gösterir', () => {
    render(<FinancialBalanceWidget income={50_000} expense={20_000} debt={10_000} debtToIncomeRatio={20} />)
    const badge = screen.getByText('Borç/Gelir: %20')
    expect(badge.className).toContain('bg-emerald-50')
  })
})

describe('formatFinancialBalanceTooltip', () => {
  it('değeri para birimi olarak "Tutar" etiketiyle biçimlendirir', () => {
    const [label, name] = formatFinancialBalanceTooltip(50_000)
    expect(label).toContain('50.000')
    expect(name).toBe('Tutar')
  })
})
