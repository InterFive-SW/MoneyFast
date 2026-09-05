/**
 * Money formatting — one implementation, so a price cannot be labelled two
 * ways in two places.
 *
 * There were seven near-identical copies of a `formatCurrency` hardcoded to
 * TRY (TradeModal, PortfolioSummaryBar, TotalBalance, RecentTransactions,
 * AssetAllocation, FinancialBalance and the chat PortfolioWidget), plus three
 * separate currency→symbol maps. That is why buying AAPL — a dollar-priced
 * stock — showed "₺314,88".
 */

/** Display symbols for the currencies actually quoted in this system. */
const SYMBOLS: Record<string, string> = {
  TRY: '₺',
  USD: '$',
  EUR: '€',
};

/** The account currency every total is expressed in. */
export const BASE_CURRENCY = 'TRY';

/**
 * The symbol for a currency, or the code itself when we have no symbol.
 *
 * Falling back to the code rather than to ₺ is the whole point: a wrong
 * symbol is a wrong claim about what the number means, while an unfamiliar
 * code is merely unfamiliar.
 */
export function currencySymbol(currency: string): string {
  return SYMBOLS[currency?.toUpperCase()] ?? currency ?? '';
}

/** A number with Turkish grouping and exactly two decimals. */
export function formatAmount(amount: number, maximumFractionDigits = 2): string {
  return amount.toLocaleString('tr-TR', {
    minimumFractionDigits: 2,
    maximumFractionDigits,
  });
}

/**
 * A short number for a cramped axis: `1,4 Mn`, `812 B`, `47,25`.
 *
 * Axis ticks are the one place the full form does not fit — six ticks of
 * `₺1.412.905,33` either overlap or push the plot off the panel. The suffixes
 * are Turkish (`B` bin, `Mn` milyon, `Mr` milyar), not `K/M/B`, because `B`
 * means *billion* to an English reader and *thousand* to a Turkish one and the
 * axis has no room to disambiguate.
 *
 * No currency symbol: this is a tick label, and the panel already says what
 * the series is. `formatMoney` stays the only thing that labels a value with
 * its unit.
 */
export function formatCompact(value: number, span?: number): string {
  if (value == null || Number.isNaN(value)) return '—';
  const sign = value < 0 ? '-' : '';
  const size = Math.abs(value);
  const [scaled, suffix, unit] =
    size >= 1_000_000_000
      ? [size / 1_000_000_000, ' Mr', 1_000_000_000]
      : size >= 1_000_000
        ? [size / 1_000_000, ' Mn', 1_000_000]
        : size >= 1_000
          ? [size / 1_000, ' B', 1_000]
          : [size, '', 1];
  return `${sign}${scaled.toLocaleString('tr-TR', {
    minimumFractionDigits: compactDigits(scaled, suffix, span, unit),
    maximumFractionDigits: compactDigits(scaled, suffix, span, unit),
  })}${suffix}`;
}

/**
 * Kaç ondalık basamak yazılacağı.
 *
 * Hassasiyet BÜYÜKLÜKTEN değil ARALIKTAN türüyor. Sabit bir kural
 * (`ondan küçükse bir basamak`) tek bir sayı için doğru ama bir EKSEN için
 * değil: ölçüldü, haftalık portföy bandı 1.091.137 - 1.117.318, yani beş Y
 * etiketinin BEŞİ de "1,1 Mn" yazıyordu. Beş kez aynı sayıyı yazan bir eksen
 * eksen değildir.
 *
 * `span` verildiğinde basamak sayısı, komşu iki etiketi ayırt etmeye yetecek
 * kadar açılıyor: ~5 aralık için bant/5 kadarlık bir adımı görünür kılan en
 * küçük basamak. Verilmediğinde eski davranış aynen duruyor -- tek bir
 * sayıyı biçimlendiren onlarca çağrı yeri var ve onlar için doğruydu.
 */
function compactDigits(
  scaled: number,
  suffix: string,
  span: number | undefined,
  unit: number,
): number {
  if (span == null || !Number.isFinite(span) || span <= 0) {
    // One decimal below ten, none above: `1,4 Mn` reads, `1,412 Mn` does not,
    // and `412,9 B` adds a digit nobody reads off an axis.
    return scaled < 10 && suffix !== '' ? 1 : 0;
  }
  // Beş etiketlik bir eksende bir adım. Ölçek biriminde ifade ediliyor,
  // çünkü basamak sayısı ölçeklenmiş sayıya uygulanıyor.
  const step = span / 5 / unit;
  if (step >= 1) return 0;
  // `-log10(step)` yukarı yuvarlanınca adımı görünür kılan basamak çıkıyor;
  // üç basamakla sınırlı, çünkü `1,0912 Mn` bir eksen etiketi değil.
  return Math.min(3, Math.ceil(-Math.log10(step)));
}

/**
 * A price with its own currency: `314,88 USD`, `301,25 ₺`.
 *
 * The unit always travels with the number. A bare figure in a mixed-currency
 * table cannot be read correctly, which is exactly the state the positions
 * table was in.
 */
export function formatMoney(amount: number | null | undefined, currency = BASE_CURRENCY): string {
  if (amount == null || Number.isNaN(amount)) return '—';
  const symbol = currencySymbol(currency);
  // The lira sign leads, as it does in Turkish typography; ISO codes trail.
  return symbol === '₺'
    ? `₺${formatAmount(amount)}`
    : `${formatAmount(amount)} ${symbol}`;
}

/**
 * Convert into the account's currency using rates supplied by the backend.
 *
 * Returns null when no rate is available rather than falling back to 1.0 —
 * treating 100 USD as 100 TRY understates a holding by a factor of forty, and
 * this codebase has already paid for that mistake once on the trading side.
 */
export function convert(
  amount: number,
  from: string,
  to: string,
  rates: Record<string, number> | null | undefined,
): number | null {
  const table: Record<string, number> = { [BASE_CURRENCY]: 1, ...(rates ?? {}) };
  const fromRate = table[from?.toUpperCase()];
  const toRate = table[to?.toUpperCase()];
  if (fromRate == null || toRate == null) return null;
  return (amount * fromRate) / toRate;
}

/**
 * The native price plus its approximate value in the account's currency:
 * `314,88 $ · ≈₺15.098,00`.
 *
 * The equivalent is marked "≈" and omitted entirely when the instrument is
 * already in the base currency, so a TRY row never carries a redundant
 * restatement of itself.
 */
export function formatWithBase(
  amount: number | null | undefined,
  currency: string,
  rates?: Record<string, number> | null,
): string {
  const native = formatMoney(amount, currency);
  if (amount == null || (currency ?? BASE_CURRENCY).toUpperCase() === BASE_CURRENCY) {
    return native;
  }
  const converted = convert(amount, currency, BASE_CURRENCY, rates);
  if (converted == null) return native;
  return `${native} · ≈${formatMoney(converted, BASE_CURRENCY)}`;
}

/**
 * Just the base-currency equivalent, for dense tables that show it on a
 * second line. Empty string when there is nothing to add.
 */
export function baseEquivalent(
  amount: number | null | undefined,
  currency: string,
  rates?: Record<string, number> | null,
): string {
  if (amount == null || (currency ?? BASE_CURRENCY).toUpperCase() === BASE_CURRENCY) return '';
  const converted = convert(amount, currency, BASE_CURRENCY, rates);
  return converted == null ? '' : `≈${formatMoney(converted, BASE_CURRENCY)}`;
}
