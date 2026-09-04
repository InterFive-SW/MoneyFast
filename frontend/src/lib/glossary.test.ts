/**
 * Terim sözlüğü.
 *
 * İçerik testleri değil, **kural** testleri: sözlük ekranın konuştuğu dili
 * belirliyor ve asistanın konuştuğu dille aynı çizgide durmak zorunda.
 */
import { describe, expect, it } from 'vitest'
import { GLOSSARY, lookupTerm } from './glossary'

describe('lookupTerm', () => {
    it('bilinen terimi döndürür', () => {
        expect(lookupTerm('volatility')?.title).toBe('Yıllık oynaklık')
    })

    it('bilinmeyen anahtar ekranı bozmaz', () => {
        /* Eksik bir tanım, sayfanın çökmesi için bir sebep değil. */
        expect(lookupTerm('bilinmeyen_terim')).toBeNull()
        expect(lookupTerm('')).toBeNull()
    })
})

describe('sözlük kuralları', () => {
    const entries = Object.entries(GLOSSARY)

    it('her terimin başlığı, kısa ve uzun tanımı var', () => {
        for (const [key, entry] of entries) {
            expect(entry.title, key).toBeTruthy()
            expect(entry.short, key).toBeTruthy()
            expect(entry.long, key).toBeTruthy()
        }
    })

    it('hiçbir tanım alan adı sızdırmaz', () => {
        /* NAMING kuralı: kullanıcı `max_drawdown` değil "en derin düşüş" okur. */
        for (const [key, entry] of entries) {
            const text = `${entry.title} ${entry.short} ${entry.long} ${entry.example ?? ''}`
            expect(text, key).not.toMatch(/[a-z]_[a-z]/)
        }
    })

    it('hiçbir tanım kullanıcıya ne yapması gerektiğini söylemez', () => {
        /* Ekranın sözü asistanın sözüyle aynı çizgide: tanım serbest,
           direktif değil. */
        for (const [key, entry] of entries) {
            const text = `${entry.short} ${entry.long} ${entry.example ?? ''}`.toLocaleLowerCase(
                'tr-TR',
            )
            for (const banned of ['almalı', 'satmalı', 'azaltmalı', 'artırmalı', 'tavsiye']) {
                expect(text, `${key}: ${banned}`).not.toContain(banned)
            }
        }
    })

    it('ölçek satırları bir eşik yargısı değil', () => {
        /* `anchors` cetveldir: "10 eşit pozisyon ≈ 10,0" ölçek verir,
           "6’nın altı yetersizdir" ise bir yargıdır ve bu ürün onu vermiyor. */
        for (const [key, entry] of entries) {
            for (const anchor of entry.anchors ?? []) {
                const text = anchor.toLocaleLowerCase('tr-TR')
                for (const banned of ['yetersiz', 'ideal', 'olmalı', 'tehlikeli', 'güvenli']) {
                    expect(text, `${key}: ${anchor}`).not.toContain(banned)
                }
            }
        }
    })

    it('risk puanının ters ölçeği açıkça yazılmış', () => {
        /* Sayfanın adı "Risk Analizi" ve puan tersine çalışıyor: 83 gören biri
           doğal olarak yüksek risk sanar. */
        const entry = GLOSSARY.risk_score
        expect(entry.long).toContain('TERSTİR')
        expect(entry.short).toContain('daha sakin')
    })

    it('kayıp eşiğinin bir tahmin olmadığı belirtilmiş', () => {
        /* MCP sözleşmesinin şartı: tarihsel ölçüm, gelecek için sınır değil. */
        expect(GLOSSARY.var.long).toContain('DEĞİLDİR')
        expect(GLOSSARY.cvar.long).toContain('tahmin değildir')
    })

    it('risk dışı terimleri de kapsar', () => {
        /* Sözlük uygulama geneli: Portföy ve Piyasalar da aynı tanımları
           kullanabilsin diye. */
        for (const key of ['pe_ratio', 'pb_ratio', 'market_cap', 'volume']) {
            expect(lookupTerm(key), key).not.toBeNull()
        }
    })
})
