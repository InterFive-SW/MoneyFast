/**
 * Recharts tooltip yardımcıları.
 *
 * Recharts 3 ile `Tooltip` formatter'ının değer tipi `ValueType | undefined`
 * oldu — grafik verisinde bir noktanın gerçekten boş olabileceğini yansıtıyor.
 * Her çağrı yerinde ayrı ayrı daraltmak yerine tek yerde toplanıyor.
 */

/** Tooltip değerini sayıya çevirir; sayı değilse `null` — 0 değil. */
export function toNumber(value: unknown): number | null {
  if (typeof value === 'number') return Number.isFinite(value) ? value : null
  if (typeof value === 'string' && value.trim() !== '') {
    const parsed = Number(value)
    return Number.isFinite(parsed) ? parsed : null
  }
  return null
}

/** İşaretli yüzde: `+1,2%`. Değer yoksa "—", çünkü %0 bir ölçümdür. */
export function signedPercent(value: unknown): string {
  const parsed = toNumber(value)
  if (parsed === null) return '—'
  return `${parsed > 0 ? '+' : ''}${parsed}%`
}

/** Tooltip serisi adını düz metne çevirir. */
export function seriesName(name: unknown): string {
  return typeof name === 'string' ? name : String(name ?? '')
}

/**
 * Bir serinin Y ekseni aralığı: en düşük ve en yüksek değerin biraz dışı.
 *
 * Recharts'ın sayısal eksende varsayılanı `[0, 'auto']`. Portföy değeri gibi
 * sıfırdan çok uzakta, dar bantta gezinen bir seride bu, çizginin tamamını
 * grafiğin en üst yüzdelik diliminde düz bir çizgiye çeviriyor: ölçülen
 * portföyde 1,41 Mn ile 1,43 Mn arasındaki hareket, 0'dan başlayan bir eksende
 * grafiğin %1,4'ü kadar yer kaplıyordu ve kullanıcı hiçbir şey göremiyordu.
 *
 * Boşluk aralığın KENDİSİNİN yüzdesi kadar, sabit bir miktar değil: yatay bir
 * günü tepe-dip arası bir günmüş gibi göstermek, düz çizgiden farklı bir
 * yalan olurdu. Aralık sıfıra çok yakınsa (tek nokta, ya da hiç değişmemiş
 * bir seri) değerin kendisinden türetiliyor, yoksa sıfır yükseklikte bir
 * eksen kalırdı.
 */
export function paddedDomain(values: number[]): [number, number] {
  const finite = values.filter((value) => Number.isFinite(value))
  if (finite.length === 0) return [0, 1]
  const min = Math.min(...finite)
  const max = Math.max(...finite)
  const span = max - min
  const pad = span > 0 ? span * 0.08 : Math.max(Math.abs(max) * 0.01, 1)
  return [min - pad, max + pad]
}
