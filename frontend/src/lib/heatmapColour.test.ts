/**
 * Isı haritası renk ölçeği.
 *
 * Ölçek TERSTİ: koyu bir tabandan tam renge doğru karıştığı için %+3 en
 * PARLAK yeşildi ve sakin bir gün en koyu kutuydu. Gözün en çok takıldığı
 * kutu, en az hareket eden kutuydu.
 */
import { describe, expect, it } from 'vitest'
import {
  FULL_SCALE,
  LEGEND_STEPS,
  TILE_TEXT_COLOUR,
  tileColour,
  tileLightness,
} from './heatmapColour'

/** `hsl(142, 61%, 38%)` -> 38 */
function lightness(colour: string): number {
  const match = colour.match(/hsl\(\d+,\s*\d+%,\s*(\d+)%\)/)
  if (!match) throw new Error(`hsl bekleniyordu: ${colour}`)
  return Number(match[1])
}

function hue(colour: string): number {
  return Number(colour.match(/hsl\((\d+),/)![1])
}

const NEUTRAL_HEX = '#3f4654'

/** sRGB bileşeni -> doğrusal ışık. WCAG 2.1, 
 * https://www.w3.org/TR/WCAG21/#dfn-relative-luminance */
function channel(value: number): number {
  const c = value / 255
  return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4
}

function rgbOf(colour: string): [number, number, number] {
  const hex = colour.match(/^#([0-9a-f]{6})$/i)
  if (hex) {
    const n = parseInt(hex[1], 16)
    return [(n >> 16) & 255, (n >> 8) & 255, n & 255]
  }
  const [h, s, l] = [hue(colour), saturation(colour), lightness(colour)]
  const sat = s / 100
  const lig = l / 100
  const c = (1 - Math.abs(2 * lig - 1)) * sat
  const x = c * (1 - Math.abs(((h / 60) % 2) - 1))
  const m = lig - c / 2
  const [r, g, b] =
    h < 60 ? [c, x, 0] : h < 120 ? [x, c, 0] : h < 180 ? [0, c, x] : [0, 0, 0]
  return [(r + m) * 255, (g + m) * 255, (b + m) * 255]
}

/** Beyaz yazının bu zemindeki kontrast oranı. */
function contrastWithWhite(colour: string): number {
  const [r, g, b] = rgbOf(colour)
  const luminance =
    0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)
  return 1.05 / (luminance + 0.05)
}

function saturation(colour: string): number {
  return Number(colour.match(/hsl\(\d+,\s*(\d+)%/)![1])
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

describe('yazı rengi', () => {
  it('her kutuda beyaz', () => {
    /* Açık kutuda koyu, koyu kutuda beyaz yazan bir kural vardı. İki renk
       arasında gidip gelen etiket, ölçeğin kendisiyle yarışan ikinci bir
       sinyal üretiyordu. */
    expect(TILE_TEXT_COLOUR).toBe('#ffffff')
  })

  it('en AÇIK kutu bile beyaz yazıyı taşıyor', () => {
    /* Sabit beyaz yazı, ancak zemin her yerde yeterince koyuysa dürüst bir
       tercih. Ölçeğin en açık ucunu -- yani en kötü hâli -- ölçüyoruz;
       yorumda yazan 4,48 sayısı burada doğrulanıyor. */
    for (const step of LEGEND_STEPS) {
      if (step === 0) continue
      expect(contrastWithWhite(tileColour(step))).toBeGreaterThanOrEqual(3)
    }
    /* Sıfıra en yakın renkli kutu ölçeğin en açık noktası. */
    expect(contrastWithWhite(tileColour(0.06))).toBeGreaterThanOrEqual(4.4)
    expect(contrastWithWhite(NEUTRAL_HEX)).toBeGreaterThanOrEqual(4.4)
  })

  it('açıklık eğrisi tek yerden geliyor', () => {
    /* İki kopya sessizce ayrışırdı: renk bir eğriyi, okunabilirlik iddiası
       başkasını izlerdi. */
    expect(lightness(tileColour(FULL_SCALE))).toBe(Math.round(tileLightness(1)))
    expect(lightness(tileColour(0.06))).toBe(Math.round(tileLightness(0.02)))
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
