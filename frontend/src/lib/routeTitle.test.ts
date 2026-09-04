/**
 * Başlıklar.
 *
 * Tablo `location.pathname` ile TAM eşleşiyordu, dolayısıyla alt rotası olan
 * her ekran uygulamanın adına düşüyordu: Piyasalar'da başlık "MoneyFast"
 * yazıyordu. Ekranın adı yerine uygulamanın adını göstermek, kullanıcıya
 * nerede olduğunu söylememektir.
 */
import { describe, expect, it } from 'vitest'
import { titleFor } from './routeTitle'

describe('titleFor', () => {
  it('kök adresi eşleştirir', () => {
    expect(titleFor('/dashboard')).toBe('Gösterge Paneli')
    expect(titleFor('/portfolio')).toBe('Portföy')
  })

  it('ALT rotaları da eşleştirir', () => {
    /* Ekran görüntüsündeki hata: `/investment/hisseler` `/investment`'i
       ıskalıyordu. */
    expect(titleFor('/investment/hisseler')).toBe('Piyasalar')
    expect(titleFor('/investment/hisseler/THYAO')).toBe('Piyasalar')
    expect(titleFor('/analiz/genel')).toBe('Analiz')
    expect(titleFor('/banking/accounts')).toBe('Cüzdan & İşlemler')
    expect(titleFor('/settings/profile')).toBe('Ayarlar')
  })

  it('tabloda hiç olmayan ekranı da kapsar', () => {
    /* `/hizli-finans` haritada yoktu ve "MoneyFast" gösteriyordu. */
    expect(titleFor('/hizli-finans')).toBe('Hızlı Finans')
  })

  it('en UZUN önek kazanır', () => {
    /* Bugünkü haritada iç içe iki rota yok, dolayısıyla bu kural gerçek
       kullanımda hiç sınanmıyor. Bir gün `/investment/fonlar` kendi
       başlığını isterse `/investment`'ten önce eşleşmeli. */
    const nested = { '/investment': 'Piyasalar', '/investment/fonlar': 'Fonlar' }

    expect(titleFor('/investment/fonlar', nested)).toBe('Fonlar')
    expect(titleFor('/investment/fonlar/AFT', nested)).toBe('Fonlar')
    expect(titleFor('/investment/hisseler', nested)).toBe('Piyasalar')
  })

  it('varsayılan tablo uygulamanınki', () => {
    expect(titleFor('/analiz')).toBe('Analiz')
    expect(titleFor('/analiz/senaryo')).toBe('Analiz')
  })

  it('yalnızca segment sınırında eşleşir', () => {
    /* `/investments-eski` `/investment` DEĞİLDİR; düz bir `startsWith`
       onu Piyasalar sanardı. */
    expect(titleFor('/investments-eski')).toBe('MoneyFast')
  })

  it('bilinmeyen adres uygulamanın adına düşer', () => {
    expect(titleFor('/bilinmeyen')).toBe('MoneyFast')
    expect(titleFor('/')).toBe('MoneyFast')
  })
})
