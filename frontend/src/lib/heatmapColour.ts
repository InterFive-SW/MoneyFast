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
 * Yüzde değişimi renge çevirir: kazanç yeşil, kayıp kırmızı.
 *
 * Doygunluk hareketin BÜYÜKLÜĞÜYLE artıyor -- %0,2'lik bir kıpırdanma ile
 * %8'lik bir sıçrama aynı renkte olsaydı harita hangi hissenin gerçekten
 * hareket ettiğini söylemezdi. Sıfıra çok yakın değerler nötr gri kalıyor:
 * yuvarlanmış bir sıfırı yeşile boyamak, olmayan bir kazancı göstermek olurdu.
 *
 * **Büyük hareket KOYU, küçük hareket açık.** Önceki ölçek tersiydi: koyu bir
 * tabandan tam renge doğru karıştığı için %+3 en PARLAK yeşildi ve sakin bir
 * gün en koyu kutuydu. Ölçek artık açıklıkla iniyor -- gözün en çok takıldığı
 * kutu, gerçekten en çok hareket eden kutu.
 */
export function tileColour(changePercent: number): string {
  if (Math.abs(changePercent) < 0.05) return NEUTRAL
  const intensity = Math.min(1, Math.abs(changePercent) / FULL_SCALE)
  const hue = changePercent > 0 ? 142 : 0
  // Açıklık %62'den %26'ya iniyor: küçük hareket soluk, büyük hareket derin.
  const lightness = 62 - intensity * 36
  // Doygunluk da büyüklükle artıyor, yoksa soluk uç griye çok yaklaşıyor.
  const saturation = 38 + intensity * 34
  return `hsl(${hue}, ${Math.round(saturation)}%, ${Math.round(lightness)}%)`
}

/**
 * Kutunun üzerindeki yazı rengi.
 *
 * Ölçek terse döndüğü için küçük hareketler artık AÇIK renkli ve sabit beyaz
 * yazı orada okunmuyordu -- rengi düzeltirken okunabilirliği bozmak, bir hatayı
 * başkasıyla değiştirmek olurdu. Eşik açıklık ölçeğinin ortası.
 */
export function tileTextColour(changePercent: number): string {
  if (Math.abs(changePercent) < 0.05) return '#ffffff'
  const intensity = Math.min(1, Math.abs(changePercent) / FULL_SCALE)
  return 62 - intensity * 36 > 45 ? '#0f172a' : '#ffffff'
}
