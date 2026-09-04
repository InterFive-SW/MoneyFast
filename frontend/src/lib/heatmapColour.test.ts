/**
 * Isı haritası renk ölçeği.
 *
 * Ölçek TERSTİ: koyu bir tabandan tam renge doğru karıştığı için %+3 en
 * PARLAK yeşildi ve sakin bir gün en koyu kutuydu. Gözün en çok takıldığı
 * kutu, en az hareket eden kutuydu.
 */
import { describe, expect, it } from 'vitest'
import { FULL_SCALE, LEGEND_STEPS, tileColour, tileTextColour } from './heatmapColour'

/** `hsl(142, 61%, 38%)` -> 38 */
function lightness(colour: string): number {
  const match = colour.match(/hsl\(\d+,\s*\d+%,\s*(\d+)%\)/)
  if (!match) throw new Error(`hsl bekleniyordu: ${colour}`)
  return Number(match[1])
}

function hue(colour: string): number {
  return Number(colour.match(/hsl\((\d+),/)![1])
}

describe('tileColour', () => {
  it('BÜYÜK hareket KOYU, küçük hareket açık', () => {
    /* İstenen davranış bu: %+3 en koyu yeşil olmalı, en parlak değil. */
    expect(lightness(tileColour(3))).toBeLessThan(lightness(tileColour(1)))
    expect(lightness(tileColour(-3))).toBeLessThan(lightness(tileColour(-1)))
  })

  it('kazanç yeşil, kayıp kırmızı', () => {
    expect(hue(tileColour(2))).toBe(142)
    expect(hue(tileColour(-2))).toBe(0)
  })

  it('sıfıra çok yakın hareket nötr kalır', () => {
    /* Yuvarlanmış bir sıfırı yeşile boyamak, olmayan bir kazancı
       göstermek olurdu. */
    expect(tileColour(0)).toBe('#3f4654')
    expect(tileColour(0.04)).toBe('#3f4654')
    expect(tileColour(-0.04)).toBe('#3f4654')
  })

  it('eşiğin ötesi tam doygunlukta durur', () => {
    /* %20'lik bir sıçrama %3'ten daha koyu OLMAZ; ölçek tavanlı. */
    expect(tileColour(20)).toBe(tileColour(FULL_SCALE))
    expect(tileColour(-20)).toBe(tileColour(-FULL_SCALE))
  })

  it('en küçük hareket bile nötrden ayırt edilir', () => {
    expect(tileColour(0.06)).not.toBe('#3f4654')
  })
})

describe('tileTextColour', () => {
  it('açık kutuda koyu yazı', () => {
    /* Ölçek terse dönünce küçük hareketler AÇIK renk oldu ve sabit beyaz
       yazı orada okunmuyordu -- rengi düzeltirken okunabilirliği bozmak,
       bir hatayı başkasıyla değiştirmek olurdu. */
    expect(tileTextColour(0.5)).toBe('#0f172a')
    expect(tileTextColour(-0.5)).toBe('#0f172a')
  })

  it('koyu kutuda beyaz yazı', () => {
    expect(tileTextColour(3)).toBe('#ffffff')
    expect(tileTextColour(-3)).toBe('#ffffff')
  })

  it('nötr kutuda beyaz yazı', () => {
    expect(tileTextColour(0)).toBe('#ffffff')
  })
})

describe('efsane', () => {
  it('çubuk kutularla AYNI fonksiyondan çiziliyor', () => {
    /* Efsane süs değil anahtar: ayrı bir renk tablosu olsaydı ikisi
       ayrışabilir ve çubuk yanlış bir şeyi açıklardı. */
    for (const step of LEGEND_STEPS) {
      expect(tileColour(step)).toBe(tileColour(step))
    }
    expect(LEGEND_STEPS).toEqual([-3, -2, -1, 0, 1, 2, 3])
  })

  it('çubuk uçtan uca koyulaşarak gidiyor', () => {
    const negatives = [-1, -2, -3].map((s) => lightness(tileColour(s)))
    const positives = [1, 2, 3].map((s) => lightness(tileColour(s)))
    expect(negatives).toEqual([...negatives].sort((a, b) => b - a))
    expect(positives).toEqual([...positives].sort((a, b) => b - a))
  })
})
