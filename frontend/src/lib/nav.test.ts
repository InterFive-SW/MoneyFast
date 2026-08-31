import { describe, expect, it } from 'vitest'
import { isMatch } from './nav'

describe('isMatch', () => {
    it('tam eşleşmeyi kabul eder', () => {
        expect(isMatch('/analiz/senaryo', '/analiz/senaryo')).toBe(true)
    })

    it('alt adresleri kapsar', () => {
        expect(isMatch('/analiz/senaryo/2024', '/analiz/senaryo')).toBe(true)
    })

    it('segment sınırına saygı duyar', () => {
        // Düz bir `startsWith` burada `true` derdi ve menüde alakasız bir
        // öğe yanardı.
        expect(isMatch('/analiz/senaryolar', '/analiz/senaryo')).toBe(false)
    })

    it('sondaki eğik çizgi ikinci kez eklenmez', () => {
        expect(isMatch('/analiz/senaryo/x', '/analiz/senaryo/')).toBe(true)
    })

    it('ilgisiz adres eşleşmez', () => {
        expect(isMatch('/portfolio', '/analiz/senaryo')).toBe(false)
    })
})
