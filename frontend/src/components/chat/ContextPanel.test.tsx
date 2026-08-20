import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import ContextPanel from './ContextPanel'

describe('ContextPanel', () => {
  it('konu yokken boş durum panelini gösterir', () => {
    render(<ContextPanel contextTopic={null} />)
    expect(screen.getByText('Akıllı Bağlam Paneli')).toBeInTheDocument()
  })

  it('konu verildiğinde başlığı ve baş harflerini gösterir', () => {
    render(<ContextPanel contextTopic="THYAO" />)
    expect(screen.getByText('THYAO')).toBeInTheDocument()
    expect(screen.getByText('TH')).toBeInTheDocument()
  })
})
