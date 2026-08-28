import { describe, expect, it } from 'vitest'
import { fireEvent, render, screen, within } from '@testing-library/react'
import CitationList from './CitationList'
import {
  CITATION_INITIAL_VISIBLE,
  normalizeCitations,
  type SafeResearchCitation,
} from '../../lib/researchCitations'

const BASE = {
  evidence_id: '1ac7a52713bdf683e6be98a05ae4dfe6',
  platform: 'x' as const,
  handle: 'kap_bildirimleri',
  display_name: 'KAP Bildirimleri',
  published_at: '2026-08-27T09:00:00+00:00',
  post_url: 'https://x.com/kap_bildirimleri/status/123',
  kap_url: 'https://kap.org.tr/tr/Bildirim/1',
  verification_status: 'officially_verified' as const,
  source_type: 'disclosure_aggregator' as const,
  excerpt: 'Kısa güvenli özet',
  matched_symbols: ['ASELS'],
}

function safe(overrides: Record<string, unknown> = {}): SafeResearchCitation {
  const [one] = normalizeCitations([{ ...BASE, ...overrides }])
  if (!one) throw new Error('expected citation')
  return one
}

describe('CitationList', () => {
  it('renders nothing when citations are empty', () => {
    const { container } = render(<CitationList citations={[]} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('shows KAP as primary and X as secondary social signal', () => {
    render(<CitationList citations={[safe()]} />)
    expect(screen.getByRole('heading', { name: 'Kaynaklar' })).toBeInTheDocument()
    const kap = screen.getByRole('link', { name: 'KAP bildirimini görüntüle' })
    expect(kap).toHaveAttribute('href', BASE.kap_url)
    expect(kap).toHaveAttribute('rel', expect.stringContaining('noopener'))
    expect(kap).toHaveAttribute('target', '_blank')
    const x = screen.getByRole('link', { name: 'X gönderisini gör (sosyal sinyal)' })
    expect(x).toHaveAttribute('href', BASE.post_url)
  })

  it('labels X-only citations as social signal sources', () => {
    render(<CitationList citations={[safe({ kap_url: null })]} />)
    expect(screen.getByRole('link', { name: 'X gönderisini gör' })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'KAP bildirimini görüntüle' })).toBeNull()
  })

  it('escapes script-like excerpts as text', () => {
    render(
      <CitationList
        citations={[safe({ excerpt: '<script>alert(1)</script> güvenli' })]}
      />,
    )
    expect(screen.getByText(/<script>alert\(1\)<\/script>/)).toBeInTheDocument()
    expect(document.querySelector('script')).toBeNull()
  })

  it('expands beyond the initial visible count', () => {
    const many = Array.from({ length: CITATION_INITIAL_VISIBLE + 2 }, (_, i) =>
      safe({
        evidence_id: i.toString(16).padStart(32, '0'),
        post_url: `https://x.com/kap_bildirimleri/status/${i + 1}`,
        kap_url: null,
        handle: `handle_${i}`,
        display_name: `Kaynak ${i}`,
      }),
    )
    render(<CitationList citations={many} />)
    expect(screen.getAllByRole('listitem')).toHaveLength(CITATION_INITIAL_VISIBLE)
    fireEvent.click(screen.getByRole('button', { name: /kaynak daha göster/i }))
    expect(screen.getAllByRole('listitem')).toHaveLength(many.length)
  })

  it('does not overflow long names and symbol lists', () => {
    const long = safe({
      display_name: 'A'.repeat(120),
      matched_symbols: ['ASELS', 'THYAO', 'GARAN', 'EREGL', 'SISE', 'KCHOL', 'BIMAS', 'AKBNK'],
      excerpt: 'X'.repeat(200),
    })
    const { container } = render(<CitationList citations={[long]} />)
    const section = within(container).getByRole('region')
    expect(section.className).toContain('flex')
    expect(screen.getByText(/AAAA/)).toBeInTheDocument()
  })
})
