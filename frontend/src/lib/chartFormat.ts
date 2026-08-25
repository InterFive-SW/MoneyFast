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
