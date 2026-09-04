/**
 * Kaynak listesindeki bağlantılar.
 *
 * Test edilen özellik: `Markdown.tsx` şema korumasını `react-markdown`'dan
 * bedavaya alıyor, elle kurulan bir `<a>` almıyor. Adres üçüncü taraf metni --
 * `rag.documents.source_url` KAP'tan ve RSS beslemelerinden geliyor.
 */
import { describe, expect, it } from 'vitest'

import { isSafeHref } from './safeHref'

describe('isSafeHref', () => {
    it('bir KAP kalıcı bağlantısına izin verir', () => {
        expect(isSafeHref('https://www.kap.org.tr/tr/Bildirim/1655982')).toBe(true)
    })

    it('düz http adresine de izin verir', () => {
        expect(isSafeHref('http://ornek.test/haber')).toBe(true)
    })

    it('javascript şemasını reddeder', () => {
        // Tıklanınca sayfanın kendi bağlamında kod çalıştırırdı.
        expect(isSafeHref('javascript:alert(1)')).toBe(false)
    })

    it('data şemasını reddeder', () => {
        expect(isSafeHref('data:text/html;base64,PHNjcmlwdD4=')).toBe(false)
    })

    it('ayrıştırılamayan bir adresi reddeder', () => {
        expect(isSafeHref('http://[bozuk')).toBe(false)
    })

    it('boş ya da tanımsız adresi reddeder', () => {
        expect(isSafeHref('')).toBe(false)
        expect(isSafeHref(null)).toBe(false)
        expect(isSafeHref(undefined)).toBe(false)
    })

    it('göreli bir yolu sayfanın kendi şemasıyla çözer', () => {
        expect(isSafeHref('/tr/Bildirim/1')).toBe(true)
    })
})
