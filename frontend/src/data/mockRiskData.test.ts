import { describe, expect, it } from 'vitest'
import { MOCK_RISK_DATA } from './mockRiskData'

describe('MOCK_RISK_DATA', () => {
  it('0-100 aralığında bir risk skoru içerir', () => {
    expect(MOCK_RISK_DATA.overallScore).toBeGreaterThanOrEqual(0)
    expect(MOCK_RISK_DATA.overallScore).toBeLessThanOrEqual(100)
  })

  it('en az bir olumlu ve bir olumsuz risk faktörü içerir', () => {
    const impacts = MOCK_RISK_DATA.factors.map((f) => f.impact)
    expect(impacts).toContain('positive')
    expect(impacts).toContain('negative')
  })

  it('önerilerin her biri bir öncelik seviyesine sahiptir', () => {
    for (const rec of MOCK_RISK_DATA.recommendations) {
      expect(['high', 'medium', 'low']).toContain(rec.priority)
    }
  })

  it('borç/gelir oranı finansal dengeyle tutarlıdır', () => {
    const { monthlyIncome, totalDebt, debtToIncomeRatio } = MOCK_RISK_DATA.financialBalance
    expect(monthlyIncome).toBeGreaterThan(0)
    expect(totalDebt).toBeGreaterThan(0)
    expect(debtToIncomeRatio).toBeGreaterThan(0)
  })
})
