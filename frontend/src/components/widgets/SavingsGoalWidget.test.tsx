import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import SavingsGoalWidget from './SavingsGoalWidget'
import type { SavingsGoal } from '../../data/mockData'

const goals: SavingsGoal[] = [
  { id: 'g1', name: 'Tatil', target: 20_000, current: 8_000, icon: '✈️', deadline: 'Eyl 2026', color: 'from-blue-400 to-blue-600' },
  { id: 'g2', name: 'Acil Fon', target: 10_000, current: 12_000, icon: '🛟', deadline: 'Ara 2026', color: 'from-emerald-400 to-emerald-600' },
]

describe('SavingsGoalWidget', () => {
  it('hedef altındaki birikimde gerçek yüzdeyi gösterir', () => {
    render(<SavingsGoalWidget goals={goals} />)
    expect(screen.getByText('Tatil')).toBeInTheDocument()
    expect(screen.getByText('40%')).toBeInTheDocument()
  })

  it('hedefi aşan birikimde yüzdeyi 100 ile sınırlar', () => {
    render(<SavingsGoalWidget goals={goals} />)
    expect(screen.getByText('Acil Fon')).toBeInTheDocument()
    expect(screen.getByText('100%')).toBeInTheDocument()
  })
})
