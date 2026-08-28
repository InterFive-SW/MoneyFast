import { describe, expect, it } from 'vitest'
import {
  citationToWire,
  formatCitationTime,
  isSafeKapUrl,
  isSafeXPostUrl,
  normalizeCitations,
  reviveCitations,
  sanitizeCitation,
  sourceTypeLabel,
  verificationLabel,
} from './researchCitations'

const VALID = {
  evidence_id: '1ac7a52713bdf683e6be98a05ae4dfe6',
  platform: 'x',
  handle: 'kap_bildirimleri',
  display_name: 'KAP Bildirimleri',
  published_at: '2026-08-27T09:00:00+00:00',
  post_url: 'https://x.com/kap_bildirimleri/status/123',
  kap_url: 'https://kap.org.tr/tr/Bildirim/1',
  verification_status: 'officially_verified',
  source_type: 'disclosure_aggregator',
  excerpt: 'Kısa güvenli özet',
  matched_symbols: ['ASELS'],
}

describe('isSafeXPostUrl', () => {
  it('accepts canonical https x/twitter status urls', () => {
    expect(isSafeXPostUrl('https://x.com/a/status/1')).toBe(true)
    expect(isSafeXPostUrl('https://www.x.com/a/status/1')).toBe(true)
    expect(isSafeXPostUrl('https://twitter.com/a/status/1')).toBe(true)
    expect(isSafeXPostUrl('https://www.twitter.com/a/status/1/')).toBe(true)
  })

  it('rejects http, lookalikes, userinfo, ports, query, fragment, schemes', () => {
    expect(isSafeXPostUrl('http://x.com/a/status/1')).toBe(false)
    expect(isSafeXPostUrl('https://x.com.evil.example/a/status/1')).toBe(false)
    expect(isSafeXPostUrl('https://evil-x.com/a/status/1')).toBe(false)
    expect(isSafeXPostUrl('https://user:pass@x.com/a/status/1')).toBe(false)
    expect(isSafeXPostUrl('https://x.com:8443/a/status/1')).toBe(false)
    expect(isSafeXPostUrl('https://x.com/a/status/1?utm=1')).toBe(false)
    expect(isSafeXPostUrl('https://x.com/a/status/1#frag')).toBe(false)
    expect(isSafeXPostUrl('javascript:alert(1)')).toBe(false)
    expect(isSafeXPostUrl('data:text/html,hi')).toBe(false)
    expect(isSafeXPostUrl('https://x.com/a/status/1\u0000')).toBe(false)
  })

  it('rejects every C0 control and DEL before URL parsing (no silent repair)', () => {
    // JS URL() strips TAB/LF/CR — these must fail closed on the raw string.
    expect(isSafeXPostUrl('https://x.com/a/sta\ttus/1')).toBe(false)
    expect(isSafeXPostUrl('https://x.com/a/sta\ntus/1')).toBe(false)
    expect(isSafeXPostUrl('https://x.com/a/sta\rtus/1')).toBe(false)
    expect(isSafeXPostUrl('\thttps://x.com/a/status/1')).toBe(false)
    expect(isSafeXPostUrl('https://x.com/a/status/1\n')).toBe(false)
    expect(isSafeXPostUrl('\rhttps://x.com/a/status/1\r')).toBe(false)
    expect(isSafeXPostUrl('https://x.com/a/status/1\u007f')).toBe(false)
    expect(isSafeXPostUrl('https://x.com/a/status/\u000b1')).toBe(false)
  })
})

describe('isSafeKapUrl', () => {
  it('accepts exact kap hosts over https', () => {
    expect(isSafeKapUrl('https://kap.org.tr/tr/Bildirim/1')).toBe(true)
    expect(isSafeKapUrl('https://www.kap.org.tr/tr/Bildirim/1')).toBe(true)
  })

  it('rejects lookalikes, http, userinfo, ports', () => {
    expect(isSafeKapUrl('http://kap.org.tr/x')).toBe(false)
    expect(isSafeKapUrl('https://kap.org.tr.evil.example/x')).toBe(false)
    expect(isSafeKapUrl('https://evil.kap.org.tr/x')).toBe(false)
    expect(isSafeKapUrl('https://user:pass@kap.org.tr/x')).toBe(false)
    expect(isSafeKapUrl('https://kap.org.tr:8443/x')).toBe(false)
  })

  it('rejects control characters in KAP urls before parsing', () => {
    expect(isSafeKapUrl('https://kap.org.tr/x\ny')).toBe(false)
    expect(isSafeKapUrl('https://kap.org.tr/x\ty')).toBe(false)
    expect(isSafeKapUrl('https://kap.org.tr/x\ry')).toBe(false)
    expect(isSafeKapUrl('\nhttps://kap.org.tr/tr/Bildirim/1')).toBe(false)
    expect(isSafeKapUrl('https://kap.org.tr/tr/Bildirim/1\u007f')).toBe(false)
  })

  it('still accepts ordinary unicode display text and valid KAP paths', () => {
    expect(isSafeKapUrl('https://kap.org.tr/tr/Bildirim/ğ')).toBe(true)
    const [one] = normalizeCitations([
      { ...VALID, display_name: 'KAP Bildirimleri — özet', excerpt: 'Şirket açıklaması' },
    ])
    expect(one.displayName).toContain('ö')
    expect(one.excerpt).toContain('Ş')
  })
})

describe('citationToWire / reviveCitations', () => {
  it('revives camelCase storage rows including Date publishedAt', () => {
    const wire = citationToWire({
      evidence_id: VALID.evidence_id,
      platform: 'x',
      handle: 'kap_bildirimleri',
      displayName: 'KAP',
      publishedAt: new Date('2026-08-27T09:00:00+00:00'),
      postUrl: VALID.post_url,
      kapUrl: VALID.kap_url,
      verificationStatus: 'officially_verified',
      sourceType: 'disclosure_aggregator',
      excerpt: 'özet',
      matchedSymbols: ['ASELS'],
    })
    const [one] = reviveCitations([wire])
    expect(one.publishedAt).toBeInstanceOf(Date)
    expect(one.postUrl).toBe(VALID.post_url)
  })

  it('passes through API snake_case and drops invalid Date publishedAt', () => {
    const apiShaped = citationToWire({
      evidence_id: VALID.evidence_id,
      platform: 'x',
      handle: 'kap_bildirimleri',
      post_url: VALID.post_url,
      published_at: '2026-08-27T09:00:00+00:00',
    })
    expect((apiShaped as { post_url: string }).post_url).toBe(VALID.post_url)

    expect(
      citationToWire({
        evidence_id: VALID.evidence_id,
        platform: 'x',
        handle: 'a',
        postUrl: VALID.post_url,
        publishedAt: new Date('not-a-date'),
      }),
    ).toMatchObject({ published_at: null })

    // Neither Date nor string → published_at stays null on the storage path.
    expect(
      citationToWire({
        evidence_id: VALID.evidence_id,
        platform: 'x',
        handle: 'a',
        postUrl: VALID.post_url,
        publishedAt: 12345,
      }),
    ).toMatchObject({ published_at: null })

    // Storage row with ISO string publishedAt (post-JSON).
    expect(
      citationToWire({
        evidence_id: VALID.evidence_id,
        platform: 'x',
        handle: 'kap_bildirimleri',
        postUrl: VALID.post_url,
        publishedAt: '2026-08-27T09:00:00.000Z',
      }),
    ).toMatchObject({ published_at: '2026-08-27T09:00:00.000Z' })

    // Non-temporal published_at on the API path stays null (fail closed).
    expect(
      citationToWire({
        evidence_id: VALID.evidence_id,
        platform: 'x',
        handle: 'a',
        post_url: VALID.post_url,
        published_at: 999,
      }),
    ).toMatchObject({ published_at: null })

    // Storage-shaped via displayName, post_url fallback when postUrl absent.
    const viaFallback = citationToWire({
      evidence_id: VALID.evidence_id,
      platform: 'x',
      handle: 'kap_bildirimleri',
      displayName: 'KAP',
      post_url: VALID.post_url,
      kap_url: VALID.kap_url,
    }) as { post_url: string; kap_url: string }
    expect(viaFallback.post_url).toBe(VALID.post_url)
    expect(viaFallback.kap_url).toBe(VALID.kap_url)

    expect(
      sanitizeCitation({
        ...VALID,
        published_at: new Date('2026-08-27T09:00:00+00:00'),
      })?.publishedAt,
    ).toBeInstanceOf(Date)
    expect(
      sanitizeCitation({ ...VALID, published_at: new Date('not-a-date') })?.publishedAt,
    ).toBeNull()
    expect(
      sanitizeCitation({ ...VALID, display_name: 'bad\u0000name' })?.displayName,
    ).toBeNull()
    expect(isSafeXPostUrl(undefined)).toBe(false)
    expect(isSafeXPostUrl(12)).toBe(false)
    expect(isSafeXPostUrl('   ')).toBe(false)
    expect(isSafeKapUrl('   ')).toBe(false)
    expect(reviveCitations(null)).toEqual([])
    expect(reviveCitations({})).toEqual([])
    expect(citationToWire(null)).toBeNull()
  })
})

describe('normalizeCitations', () => {
  it('treats missing, null and non-arrays as empty', () => {
    expect(normalizeCitations(undefined)).toEqual([])
    expect(normalizeCitations(null)).toEqual([])
    expect(normalizeCitations({})).toEqual([])
    expect(normalizeCitations('nope')).toEqual([])
  })

  it('keeps one valid x citation', () => {
    const [one] = normalizeCitations([
      {
        ...VALID,
        kap_url: null,
      },
    ])
    expect(one.evidence_id).toBe(VALID.evidence_id)
    expect(one.postUrl).toBe(VALID.post_url)
    expect(one.kapUrl).toBeNull()
    expect(one.handle).toBe('kap_bildirimleri')
  })

  it('prefers kap primary identity while keeping both urls', () => {
    const [one] = normalizeCitations([VALID])
    expect(one.kapUrl).toBe(VALID.kap_url)
    expect(one.postUrl).toBe(VALID.post_url)
  })

  it('dedupes by evidence_id preserving first order', () => {
    const second = {
      ...VALID,
      excerpt: 'ikinci',
      post_url: 'https://x.com/kap_bildirimleri/status/999',
    }
    const out = normalizeCitations([VALID, second, VALID])
    expect(out).toHaveLength(1)
    expect(out[0].excerpt).toBe('Kısa güvenli özet')
  })

  it('drops malicious hosts and keeps a sibling valid row', () => {
    const out = normalizeCitations([
      { ...VALID, post_url: 'https://x.com.evil.example/a/status/1', kap_url: null },
      { ...VALID, evidence_id: 'b'.repeat(32), post_url: 'https://x.com/a/status/2', kap_url: null },
      {
        ...VALID,
        evidence_id: 'c'.repeat(32),
        post_url: 'https://x.com/a/status/3',
        kap_url: 'https://kap.org.tr.evil.example/x',
      },
    ])
    expect(out.map((c) => c.evidence_id)).toEqual(['b'.repeat(32), 'c'.repeat(32)])
    expect(out[1].kapUrl).toBeNull()
  })

  it('drops http and userinfo urls', () => {
    expect(
      normalizeCitations([
        { ...VALID, post_url: 'http://x.com/a/status/1', kap_url: null },
        {
          ...VALID,
          evidence_id: 'd'.repeat(32),
          post_url: 'https://user:pass@x.com/a/status/1',
          kap_url: null,
        },
      ]),
    ).toEqual([])
  })

  it('drops unsupported ports', () => {
    expect(
      normalizeCitations([
        { ...VALID, post_url: 'https://x.com:8443/a/status/1', kap_url: null },
      ]),
    ).toEqual([])
  })

  it('keeps script-like excerpt only as plain text payload', () => {
    const [one] = normalizeCitations([
      { ...VALID, excerpt: '<script>alert(1)</script> güvenli metin' },
    ])
    expect(one.excerpt).toContain('<script>')
    expect(one.excerpt).toContain('güvenli metin')
  })

  it('handles missing optional fields and invalid timestamps', () => {
    const [one] = normalizeCitations([
      {
        evidence_id: VALID.evidence_id,
        platform: 'x',
        handle: 'test_finans',
        post_url: 'https://x.com/test_finans/status/1',
        published_at: '2026-08-27T09:00:00',
      },
    ])
    expect(one.displayName).toBeNull()
    expect(one.publishedAt).toBeNull()
    expect(one.matchedSymbols).toEqual([])
    expect(one.excerpt).toBeNull()
  })

  it('labels verification and source types in Turkish', () => {
    expect(verificationLabel('officially_verified')).toBe('Resmi doğrulanmış')
    expect(verificationLabel('corroborated')).toBe('Desteklenmiş')
    expect(verificationLabel('contradicted')).toBe('Çelişkili')
    expect(verificationLabel('unverified')).toBe('Doğrulanmamış')
    expect(verificationLabel(null)).toBeNull()
    expect(verificationLabel('nope' as never)).toBeNull()

    expect(sourceTypeLabel('official_company')).toBe('Şirket hesabı')
    expect(sourceTypeLabel('official_disclosure')).toBe('Resmi bildirim')
    expect(sourceTypeLabel('disclosure_aggregator')).toBe('Bildirim derleyicisi')
    expect(sourceTypeLabel('news_agency')).toBe('Ajans')
    expect(sourceTypeLabel('financial_media')).toBe('Finans medyası')
    expect(sourceTypeLabel('analyst')).toBe('Analist')
    expect(sourceTypeLabel(null)).toBeNull()
    expect(sourceTypeLabel('nope' as never)).toBeNull()
  })

  it('formats publication times for tr-TR', () => {
    const formatted = formatCitationTime(new Date('2026-08-27T09:00:00+00:00'))
    expect(formatted).toBeTruthy()
    expect(formatCitationTime(null)).toBeNull()
    expect(formatCitationTime(new Date('not-a-date'))).toBeNull()
    expect(sanitizeCitation(null)).toBeNull()
  })

  it('returns null when DateTimeFormat throws', () => {
    const original = Intl.DateTimeFormat
    // Force the catch path without depending on a real invalid locale.
    // @ts-expect-error intentional stub
    Intl.DateTimeFormat = () => {
      throw new RangeError('bad locale')
    }
    try {
      expect(formatCitationTime(new Date('2026-08-27T09:00:00+00:00'))).toBeNull()
    } finally {
      Intl.DateTimeFormat = original
    }
  })

  it('rejects malformed URL strings that fail URL parsing', () => {
    expect(isSafeXPostUrl('https://[')).toBe(false)
    expect(isSafeKapUrl('https://[')).toBe(false)
  })

  it('drops citations with control chars, bad platform, or no usable link', () => {
    expect(
      sanitizeCitation({
        ...VALID,
        handle: 'bad\u0000handle',
      }),
    ).toBeNull()
    expect(
      sanitizeCitation({
        ...VALID,
        platform: 'reddit',
      }),
    ).toBeNull()
    expect(
      sanitizeCitation({
        ...VALID,
        evidence_id: 12,
      }),
    ).toBeNull()
    expect(
      sanitizeCitation({
        ...VALID,
        evidence_id: 'zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz',
      }),
    ).toBeNull()
    expect(
      sanitizeCitation({
        ...VALID,
        handle: 99,
      }),
    ).toBeNull()
    expect(
      sanitizeCitation({
        ...VALID,
        handle: '@kap_bildirimleri',
      })?.handle,
    ).toBe('kap_bildirimleri')
    expect(
      sanitizeCitation({
        ...VALID,
        post_url: 'https://x.com.evil.example/a/status/1',
        kap_url: 'https://kap.org.tr.evil.example/x',
      }),
    ).toBeNull()
    expect(
      sanitizeCitation({
        ...VALID,
        excerpt: 'has ``` fence',
      })?.excerpt,
    ).toBeNull()
    expect(
      sanitizeCitation({
        ...VALID,
        excerpt: 'bad\u0001',
      })?.excerpt,
    ).toBeNull()
    expect(
      sanitizeCitation({
        ...VALID,
        excerpt: '   ',
      })?.excerpt,
    ).toBeNull()
    expect(
      sanitizeCitation({
        ...VALID,
        excerpt: 12,
      })?.excerpt,
    ).toBeNull()
    expect(
      sanitizeCitation({
        ...VALID,
        matched_symbols: ['ok', '', '   ', 3, 'TOOLONGSYMBOLNAMEHERE', 'ok'],
      })?.matchedSymbols,
    ).toEqual(['OK'])
    expect(
      sanitizeCitation({
        ...VALID,
        published_at: '',
      })?.publishedAt,
    ).toBeNull()
    expect(
      sanitizeCitation({
        ...VALID,
        published_at: 'totally-not-a-date',
      })?.publishedAt,
    ).toBeNull()
    expect(
      sanitizeCitation({
        ...VALID,
        published_at: 'bad\u0000',
      })?.publishedAt,
    ).toBeNull()
    expect(
      sanitizeCitation({
        ...VALID,
        verification_status: 'made_up',
        source_type: 'blog',
      })?.verificationStatus,
    ).toBeNull()
  })

  it('truncates long symbol lists and excerpts without inventing citations', () => {
    const [one] = normalizeCitations([
      {
        ...VALID,
        matched_symbols: [
          'ASELS',
          'THYAO',
          'GARAN',
          'EREGL',
          'SISE',
          'KCHOL',
          'BIMAS',
          'AKBNK',
          'YKBNK',
          'SAHOL',
        ],
        excerpt: 'E'.repeat(400),
        display_name: 'N'.repeat(200),
      },
    ])
    expect(one.matchedSymbols).toHaveLength(8)
    expect(one.excerpt).toBeNull()
    expect(one.displayName).toHaveLength(120)
  })
})
