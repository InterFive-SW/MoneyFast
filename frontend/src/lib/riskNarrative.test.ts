/**
 * Düz Türkçe özet.
 *
 * İki özellik korunuyor: ölçülemeyen bir metrik cümleye HİÇ girmez, ve
 * hiçbir cümle bir eşik yargısı taşımaz.
 */
import { describe, expect, it } from 'vitest'
import { reliabilitySentence, summarise } from './riskNarrative'

const METRICS = {
    volatility_annualized: 0.1814,
    max_drawdown: {
        value: -0.110114,
        peak_date: '2026-06-02',
        trough_date: '2026-06-25',
        recovery_date: '2026-08-04',
        duration_days: 16,
    },
    concentration: {
        effective_n: 6.0712,
        largest_position: { symbol: 'ASELS', weight: 0.3421 },
    },
    data_quality: { is_statistically_reliable: true },
}

describe('summarise', () => {
    it('oynaklığı pencereyle birlikte anlatır', () => {
        expect(summarise(METRICS, '1Y')[0]).toBe(
            'Portföyünüz son bir yılda ortalama %18 dalgalandı.',
        )
    })

    it('pencere etiketini metne çevirir', () => {
        expect(summarise(METRICS, '3M')[0]).toContain('son üç ayda')
        expect(summarise(METRICS, 'MAX')[0]).toContain('ölçülebilen tüm dönemde')
    })

    it('tanınmayan pencere için nötr bir ifade kullanır', () => {
        expect(summarise(METRICS, '7G')[0]).toContain('ölçülen dönemde')
    })

    it('toparlanmış düşüşü süresiyle anlatır', () => {
        const line = summarise(METRICS, '1Y')[1]
        expect(line).toContain('En derin düşüşünde')
        expect(line).toContain('%11 değer kaybetti')
        expect(line).toContain('16 işlem günü')
        expect(line).toContain('kaybı geri aldı')
    })

    it('toparlanmamış düşüşü toparlanmış gibi anlatmaz', () => {
        const open = {
            ...METRICS,
            max_drawdown: { ...METRICS.max_drawdown, recovery_date: null },
        }
        expect(summarise(open, '1Y')[1]).toContain('henüz geri almadı')
    })

    it('süresi bilinmeyen toparlanmada gün sayısı uydurmaz', () => {
        const noDuration = {
            ...METRICS,
            max_drawdown: { ...METRICS.max_drawdown, duration_days: null },
        }
        const line = summarise(noDuration, '1Y')[1]
        expect(line).toContain('kaybı geri aldı')
        expect(line).not.toContain('işlem günü')
    })

    it('dağılımı ve en büyük pozisyonu anlatır', () => {
        const line = summarise(METRICS, '1Y')[2]
        expect(line).toContain('6,1 eşit pozisyona denk')
        expect(line).toContain('ASELS')
        expect(line).toContain('%34')
    })

    it('en büyük pozisyon bilinmiyorsa o cümleyi eklemez', () => {
        const bare = {
            ...METRICS,
            concentration: { effective_n: 6.0712 },
        }
        const line = summarise(bare, '1Y')[2]
        expect(line).toContain('eşit pozisyona denk')
        expect(line).not.toContain('En büyük pozisyon')
    })

    it('ölçülemeyen metriği cümleye hiç sokmaz', () => {
        /* Eksik veriyi "sıfır" diye anlatmak, olmayan bir güvence vermek. */
        const partial = { concentration: { effective_n: 3 } }
        const lines = summarise(partial, '1Y')
        expect(lines).toHaveLength(1)
        expect(lines[0]).toContain('eşit pozisyona denk')
    })

    it('hiç ölçüm yoksa boş döner', () => {
        expect(summarise({}, '1Y')).toEqual([])
        expect(summarise({ volatility_annualized: null }, '1Y')).toEqual([])
    })

    it('bozuk düşüş bloğunu atlar', () => {
        expect(summarise({ max_drawdown: { value: null } }, '1Y')).toEqual([])
        expect(summarise({ max_drawdown: 'yok' }, '1Y')).toEqual([])
    })

    it('hiçbir cümle eşik yargısı ya da direktif taşımaz', () => {
        /* Ekranın sözü asistanın sözüyle aynı çizgide durmalı: asistana
           yasak olan bir cümleyi sayfa da kuramaz. */
        const text = summarise(METRICS, '1Y').join(' ')
        for (const banned of [
            'yüksek', 'düşük', 'iyi', 'kötü', 'riskli', 'güvenli',
            'azalt', 'artır', 'öneri', 'meli', 'malı',
        ]) {
            expect(text.toLocaleLowerCase('tr-TR'), banned).not.toContain(banned)
        }
    })
})

describe('reliabilitySentence', () => {
    it('güvenilir ölçümde sessiz kalır', () => {
        expect(reliabilitySentence(METRICS)).toBeNull()
    })

    it('kısa geçmişi söyler', () => {
        const shaky = { data_quality: { is_statistically_reliable: false } }
        expect(reliabilitySentence(shaky)).toContain('kısa bir geçmişe')
    })

    it('kalite bloğu yoksa bir şey uydurmaz', () => {
        expect(reliabilitySentence({})).toBeNull()
    })
})
