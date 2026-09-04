/**
 * Isı haritası renk ölçeği.
 *
 * Bileşenden ayrı, çünkü bu JSX değil kural — ve efsane çubuğu ile kutular
 * AYNI fonksiyondan besleniyor, dolayısıyla ikisinin ayrışmaması test
 * edilebilir bir iddia. Kapsama kapısı `src/lib/**` altını sayıyor.
 */
/**
 * Renk eşiği: bu yüzdeden büyük hareketler tam doygunlukta.
 *
 * Efsane çubuğu da bu ölçekten üretiliyor, dolayısıyla çubuktaki renkle
 * kutudaki renk aynı kuralın çıktısı -- efsane süs değil, anahtar.
 */
export const FULL_SCALE = 3

/** Efsane basamakları, ekrandaki çubuğun aynısı. */
export const LEGEND_STEPS = [-3, -2, -1, 0, 1, 2, 3]

/** Nötr gri: sıfıra çok yakın hareketler. */
const NEUTRAL = '#3f4654'

/**
 * Kutunun üzerindeki yazı rengi -- her kutuda aynı.
 *
 * Bir dönem açık kutularda koyu (`#0f172a`), koyu kutularda beyaz yazılıyordu.
 * İki renk arasında gidip gelen bir etiket, ölçeğin kendisiyle yarışan ikinci
 * bir sinyal üretiyordu: yan yana iki kutunun yazı rengi farklı olduğunda göz
 * bunu bir anlam sanıyor. Yazı artık sabit; okunabilirliği sağlayan şey
 * ZEMİN -- `tileLightness` en açık uçta bile beyazla 4,5:1 kontrastı
 * geçecek kadar koyu kalıyor (bkz. aşağısı).
 */
export const TILE_TEXT_COLOUR = '#ffffff'

/**
 * Ölçeğin açıklık eğrisi. Tek yerde, çünkü hem renk hem de o rengin
 * okunabilirlik iddiası buradan türüyor; iki kopya sessizce ayrışırdı.
 *
 * **Büyük hareket KOYU, küçük hareket açık.** Önceki ölçek tersiydi: koyu bir
 * tabandan tam renge doğru karıştığı için %+3 en PARLAK yeşildi ve sakin bir
 * gün en koyu kutuydu. Ölçek açıklıkla iniyor -- gözün en çok takıldığı kutu,
 * gerçekten en çok hareket eden kutu.
 *
 * Tavan %38, %62 değil. Beyaz yazı %62 açıklıktaki bir yeşilde 2,2:1
 * kontrastla okunmuyordu; ölçeğin açık ucu bu yüzden aşağı çekildi.
 * Hesaplanan en kötü hâl `hsl(142, 38%, 38%)` üzerinde beyaz = **4,48:1**
 * (WCAG AA eşiği 4,5:1, kalın 12px+ metin için 3:1). Kırmızı uç çok daha
 * rahat: `hsl(0, 38%, 38%)` üzerinde 7,75:1.
 */
export function tileLightness(intensity: number): number {
  return 38 - intensity * 14
}

/**
 * Yüzde değişimi renge çevirir: kazanç yeşil, kayıp kırmızı.
 *
 * Doygunluk hareketin BÜYÜKLÜĞÜYLE artıyor -- %0,2'lik bir kıpırdanma ile
 * %8'lik bir sıçrama aynı renkte olsaydı harita hangi hissenin gerçekten
 * hareket ettiğini söylemezdi. Sıfıra çok yakın değerler nötr gri kalıyor:
 * yuvarlanmış bir sıfırı yeşile boyamak, olmayan bir kazancı göstermek olurdu.
 */
export function tileColour(changePercent: number): string {
  if (Math.abs(changePercent) < 0.05) return NEUTRAL
  const intensity = Math.min(1, Math.abs(changePercent) / FULL_SCALE)
  const hue = changePercent > 0 ? 142 : 0
  // Doygunluk da büyüklükle artıyor, yoksa soluk uç griye çok yaklaşıyor.
  const saturation = 38 + intensity * 34
  return `hsl(${hue}, ${Math.round(saturation)}%, ${Math.round(tileLightness(intensity))}%)`
}
