import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import ChartWidget from './ChartWidget'
import type { ChartWidgetPayload } from '../../../types/chat'

describe('ChartWidget', () => {
  it('renk verilmişse başlığı render eder', () => {
    const payload: ChartWidgetPayload = { title: 'THYAO Performansı', data: [{ name: 'Oca', value: 100 }], color: '#3b82f6' }
    render(<ChartWidget payload={payload} />)
    expect(screen.getByText('THYAO Performansı')).toBeInTheDocument()
  })

  it('renk verilmezse varsayılan renkle çökmeden render eder', () => {
    const payload: ChartWidgetPayload = { title: 'GARAN Performansı', data: [{ name: 'Oca', value: 50 }, { name: 'Şub', value: 60 }] }
    render(<ChartWidget payload={payload} />)
    expect(screen.getByText('GARAN Performansı')).toBeInTheDocument()
  })
})
