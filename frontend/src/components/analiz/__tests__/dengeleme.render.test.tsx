/**
 * Dengeleme sekmesi gerçekten çiziliyor mu.
 *
 * Kapsama kapısı JSX'i saymıyor, dolayısıyla bu dosya kapsama için değil:
 * bileşenin hook'a bağlanmasında bir hata olduğunda test paketinin sessiz
 * kalmaması için. Asıl değer katan senaryo BOŞ gövde -- yeni kayıtlı bir
 * kullanıcının göreceği şekil.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'

import Dengeleme from '../../../pages/analiz/Dengeleme'

const TEMPLATES = {
    declaredTolerance: 'Düşük',
    measurementNote: 'Oynaklık son bir yıldan ölçüldü; nakit getirisi sıfır varsayıldı.',
    items: [
        {
            key: 'cash_heavy',
            label: 'Ağırlıklı nakit',
            weights: [{ bucket: 'cash', label: 'Nakit (TRY)', percent: 100 }],
            volatility: 0.067,
            band: 'Düşük',
            highlighted: true,
            statement: 'Ağırlıklı nakit şablonunun ölçülen oynaklığı %6,7.',
            unmeasured: [],
        },
    ],
}

const PLAN = {
    hasTarget: true,
    totalValue: 24607.54,
    statement: 'Sapma ölçüldü.',
    disclaimer: 'Bu liste yatırım tavsiyesi değildir; kendi belirlediğiniz hedefin aritmetik karşılığıdır.',
    rows: [
        {
            symbol: 'THYAO', name: 'THYAO', bucket: 'bist_equity', label: 'BIST Hisse',
            side: 'SELL', quantity: 12, price: 300, currency: 'TRY',
            amount_base: 3600, residual_base: 0,
            statement: 'THYAO için 12 adet satışın karşılığı 3.600,00 TRY.',
        },
    ],
    unresolved: [
        { bucket: 'gold', label: 'Altın', gap_amount: -5000,
          reason: 'Altın kovasında pozisyonunuz yok; hangi enstrümanla dolduracağınız sizin seçiminiz.' },
    ],
    rounding_residual_base: 0,
    buy_total_base: 0,
    usable_cash_base: 1000,
    blocked_cash_base: 0,
    warning: null,
}

const EMPTY_PLAN = {
    ...PLAN, hasTarget: false, rows: [], unresolved: [],
    statement: 'Hedef dağılım belirlemediniz.',
}

function stubFetch(plan: unknown, templates: unknown = TEMPLATES) {
    vi.stubGlobal('fetch', vi.fn((url: string) => Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve(
            String(url).includes('allocation-templates') ? templates : plan,
        ),
    })))
}

beforeEach(() => {
    vi.spyOn(console, 'error').mockImplementation(() => {})
})
afterEach(() => {
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
})

describe('Dengeleme ekranı', () => {
    it('şablonu, emri ve çekinceyi birlikte gösterir', async () => {
        stubFetch(PLAN)
        render(<Dengeleme />)

        // Ad hem kartın başlığında hem cümlesinde geçiyor.
        expect((await screen.findAllByText(/Ağırlıklı nakit/)).length).toBeGreaterThan(0)
        expect(await screen.findByText(/12 adet satışın karşılığı/)).toBeTruthy()
        // Çekince KOŞULSUZ: plan boş olsa da duruyor.
        expect(await screen.findByText(/yatırım tavsiyesi değildir/)).toBeTruthy()
    })

    it('emir üretilemeyen kovanın nedenini yazar', async () => {
        // Sessiz bir atlama, hedefe ulaşılamamasının sebebini görünmez yapardı.
        stubFetch(PLAN)
        render(<Dengeleme />)
        expect(await screen.findByText(/sizin seçiminiz/)).toBeTruthy()
    })

    it('hedefi olmayan yeni bir kullanıcıda boş ama anlamlı', async () => {
        stubFetch(EMPTY_PLAN, { ...TEMPLATES, items: [] })
        render(<Dengeleme />)
        expect(await screen.findByText(/Hedef dağılım belirlemediniz/)).toBeTruthy()
        await waitFor(() =>
            expect(screen.queryByText(/adet satışın karşılığı/)).toBeNull(),
        )
    })
})
