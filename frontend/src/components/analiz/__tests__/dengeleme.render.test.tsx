/**
 * Dengeleme sekmesi gerçekten çiziliyor mu.
 *
 * Kapsama kapısı JSX'i saymıyor, dolayısıyla bu dosya kapsama için değil:
 * bileşenin hook'a bağlanmasında bir hata olduğunda test paketinin sessiz
 * kalmaması için.
 *
 * En değerli iki senaryo: **gerekçelerin gerçekten çizilebiliyor olması**
 * (sistemin bir işlem listesi önermesine izin verilmesinin tek dayanağı) ve
 * **kapalı uygunluk kapısı** -- testi tamamlamamış bir kullanıcının göreceği
 * şekil.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'

import DengelemePaneli from '../DengelemePaneli'

const PLAN = {
    gate: { open: true, reason: 'Uygunluk testi tamamlanmış.' },
    lookback: '1Y',
    measuredLevel: 'Orta',
    declaredTolerance: 'Yüksek',
    bindingBand: 'Orta',
    targetSource: 'BAND',
    bandStatement:
        'Portföyünüzün ölçülen riski "Orta", ankette belirttiğiniz tolerans "Yüksek".',
    hasTarget: true,
    totalValue: 24607.54,
    statement: 'Sapma ölçüldü.',
    disclaimer: 'Bu liste yatırım tavsiyesi değildir.',
    rows: [
        {
            symbol: 'THYAO', name: 'THYAO', bucket: 'bist_equity', label: 'BIST Hisse',
            side: 'SELL', quantity: 12, price: 300, currency: 'TRY',
            amount_base: 3600, residual_base: 0,
            statement: 'THYAO için 12 adet satışın karşılığı 3.600,00 TRY.',
            rationale: [
                {
                    kind: 'RISK_CONTRIBUTION',
                    value: 0.31,
                    text: "Portföy oynaklığının %31,0'lik kısmını bu pozisyon üretiyor.",
                },
            ],
        },
    ],
    unresolved: [],
    data_quality: { positions: 1, risk_contribution: 1, fundamentals: 1, news: 0 },
    rounding_residual_base: 0,
    buy_total_base: 0,
    usable_cash_base: 1000,
    blocked_cash_base: 0,
    warning: null,
}

function mockFetch(plan: unknown) {
    return vi.fn(async () =>
        new Response(JSON.stringify(plan), {
            status: 200, headers: { 'Content-Type': 'application/json' },
        }),
    )
}

beforeEach(() => {
    vi.stubGlobal('fetch', mockFetch(PLAN))
})
afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
})

describe('DengelemePaneli', () => {
    it('planı ve satır cümlesini çizer', async () => {
        render(<DengelemePaneli />)
        await waitFor(() =>
            expect(
                screen.getByText(/12 adet satışın karşılığı/),
            ).toBeInTheDocument(),
        )
    })

    it('hedefin nereden geldiğini yazar', async () => {
        // Bir emir listesinin kaynağı, listenin kendisi kadar önemli.
        render(<DengelemePaneli />)
        await waitFor(() =>
            expect(screen.getByText(/ankette belirttiğiniz tolerans/)).toBeInTheDocument(),
        )
    })

    it('her satırın gerekçe bağlantısı var', async () => {
        render(<DengelemePaneli />)
        await waitFor(() =>
            expect(screen.getByText(/Neden bu satır\?/)).toBeInTheDocument(),
        )
    })

    it('çekince koşulsuz görünür', async () => {
        render(<DengelemePaneli />)
        await waitFor(() =>
            expect(
                screen.getByText(/yatırım tavsiyesi değildir/),
            ).toBeInTheDocument(),
        )
    })

    it('pencere seçenekleri çizilir', async () => {
        render(<DengelemePaneli />)
        await waitFor(() => expect(screen.getByText('5 yıl')).toBeInTheDocument())
    })

    it('kapalı kapı boş bir liste ve nedeniyle çizilir', async () => {
        vi.stubGlobal('fetch', mockFetch({
            ...PLAN,
            gate: { open: false, reason: 'Önce uygunluk testini tamamlayın.' },
            hasTarget: false,
            statement: 'Önce uygunluk testini tamamlayın.',
            bandStatement: 'Önce uygunluk testini tamamlayın.',
            rows: [],
        }))
        render(<DengelemePaneli />)
        await waitFor(() =>
            expect(
                screen.getAllByText(/uygunluk testini tamamlayın/).length,
            ).toBeGreaterThan(0),
        )
    })
})
