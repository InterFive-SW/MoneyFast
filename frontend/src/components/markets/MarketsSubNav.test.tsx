import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import MarketsSubNav from './MarketsSubNav'

describe('MarketsSubNav', () => {
  it('aktif rotaya karşılık gelen sekmeyi vurgular, diğerlerini vurgulamaz', () => {
    render(
      <MemoryRouter initialEntries={['/investment/fonlar']}>
        <MarketsSubNav />
      </MemoryRouter>
    )
    const active = screen.getByText('Fonlar')
    const inactive = screen.getByText('Hisseler')
    expect(active.className).toContain('bg-slate-800')
    expect(inactive.className).not.toContain('bg-slate-800 text-white')
  })
})
