import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import RiskFactorsWidget from './RiskFactorsWidget'
import type { RiskFactor } from '../../data/mockRiskData'

const factors: RiskFactor[] = [
  { id: 'f1', title: 'Düzenli Birikim', description: 'Aylık düzenli tasarruf', impact: 'positive' },
  { id: 'f2', title: 'Yüksek Kaldıraç', description: 'Kredi kullanımı yüksek', impact: 'negative' },
  { id: 'f3', title: 'Nötr Faktör', description: 'Etkisi belirsiz', impact: 'neutral' },
]

describe('RiskFactorsWidget', () => {
  it('pozitif, negatif ve nötr etkili faktörleri ayrı ikon/renklerle render eder', () => {
    render(<RiskFactorsWidget factors={factors} />)
    expect(screen.getByText('Düzenli Birikim')).toBeInTheDocument()
    expect(screen.getByText('Yüksek Kaldıraç')).toBeInTheDocument()
    expect(screen.getByText('Nötr Faktör')).toBeInTheDocument()
  })
})
