import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import RiskScoreWidget from './RiskScoreWidget'

describe('RiskScoreWidget', () => {
  it('Düşük seviyede emerald rengiyle gösterir', () => {
    render(<RiskScoreWidget score={20} level="Düşük" />)
    expect(screen.getByText('Düşük Risk')).toBeInTheDocument()
  })

  it('Orta seviyede amber rengiyle gösterir', () => {
    render(<RiskScoreWidget score={50} level="Orta" />)
    expect(screen.getByText('Orta Risk')).toBeInTheDocument()
  })

  it('Yüksek seviyede rose rengiyle gösterir', () => {
    render(<RiskScoreWidget score={85} level="Yüksek" />)
    expect(screen.getByText('Yüksek Risk')).toBeInTheDocument()
    expect(screen.getByText('85')).toBeInTheDocument()
  })
})
