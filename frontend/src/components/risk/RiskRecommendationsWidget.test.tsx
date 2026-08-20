import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import RiskRecommendationsWidget from './RiskRecommendationsWidget'
import type { RiskRecommendation } from '../../data/mockRiskData'

const recommendations: RiskRecommendation[] = [
  { id: 'r1', title: 'Acil Fon Oluşturun', description: 'En az 3 aylık gider biriktirin', priority: 'high', actionLabel: 'Detaylar' },
  { id: 'r2', title: 'Portföyü Çeşitlendirin', description: 'Tek sektöre bağımlılığı azaltın', priority: 'medium', actionLabel: 'İncele' },
  { id: 'r3', title: 'Emeklilik Planı', description: 'Uzun vadeli birikim başlatın', priority: 'low', actionLabel: 'Başla' },
]

describe('RiskRecommendationsWidget', () => {
  it('öneri sayısını ve yüksek/orta/düşük öncelikli tüm önerileri render eder', () => {
    render(<RiskRecommendationsWidget recommendations={recommendations} />)
    expect(screen.getByText('3 Öneri')).toBeInTheDocument()
    expect(screen.getByText('Acil Fon Oluşturun')).toBeInTheDocument()
    expect(screen.getByText('Portföyü Çeşitlendirin')).toBeInTheDocument()
    expect(screen.getByText('Emeklilik Planı')).toBeInTheDocument()
  })
})
