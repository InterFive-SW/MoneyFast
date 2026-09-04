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
export function formatCompact(value: number): string {
  if (value == null || Number.isNaN(value)) return '—';
  const sign = value < 0 ? '-' : '';
  const size = Math.abs(value);
  const [scaled, suffix] =
    size >= 1_000_000_000
      ? [size / 1_000_000_000, ' Mr']
      : size >= 1_000_000
        ? [size / 1_000_000, ' Mn']
        : size >= 1_000
          ? [size / 1_000, ' B']
          : [size, ''];
  // One decimal below ten, none above: `1,4 Mn` reads, `1,412 Mn` does not,
  // and `412,9 B` adds a digit nobody reads off an axis.
  const digits = scaled < 10 && suffix !== '' ? 1 : 0;
  return `${sign}${scaled.toLocaleString('tr-TR', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })}${suffix}`;
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
  return `${native} (${formatMoney(converted, BASE_CURRENCY)})`;
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
  return converted == null ? '' : `(${formatMoney(converted, BASE_CURRENCY)})`;
}
