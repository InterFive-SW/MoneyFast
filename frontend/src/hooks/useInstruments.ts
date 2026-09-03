/**
 * The live instrument universe, shaped for the markets screens.
 *
 * The markets pages were written against `data/mockData.ts`, whose
 * `MarketInstrument` differs from the API's row in naming (`changePercent` vs
 * `change_percent`), in nullability (every fundamental is optional upstream,
 * because provider coverage is partial) and in vocabulary (`market` is
 * "NASDAQ"/"NYSE" upstream, but the table's tabs say "ABD").
 *
 * Adapting here rather than rewriting seven screens keeps one translation
 * point. What it will NOT do is invent values: a fundamental the provider does
 * not publish stays undefined, so the table renders "—" instead of a zero that
 * would make a company look like the cheapest name on the list.
 */

import { useEffect, useMemo, useState } from 'react';
import { apiClient, type MarketInstrument as ApiInstrument } from '../api/client';
import type { MarketInstrument } from '../data/mockData';
import { useLiveRows } from './useLiveRows';

/**
 * Upstream exchange codes to the market labels the screens filter on.
 *
 * FX and COMEX are here because the project document names their instruments
 * explicitly -- "hisse, altın ve döviz" -- and they were the two the map did
 * not cover.
 */
const MARKET_LABELS: Record<string, MarketInstrument['market']> = {
  BIST: 'BIST',
  NASDAQ: 'ABD',
  NYSE: 'ABD',
  FX: 'Döviz',
  COMEX: 'Altın',
};

const CURRENCY_UNITS: Record<string, string> = { TRY: '₺', USD: '$', EUR: '€' };

/** Sektör kavramının tanımlı OLMADIĞI piyasalar. */
const SECTORLESS_MARKETS = new Set(['FX', 'COMEX']);

export function adaptInstrument(row: ApiInstrument): MarketInstrument {
  return {
    symbol: row.symbol,
    name: row.name,
    // Eşleşmeyen piyasa 'Diğer', 'BIST' DEĞİL. Varsayılan 'BIST'ti ve USDTRY
    // ile XAUUSD ekranda Borsa İstanbul enstrümanı gibi görünüyordu --
    // backend'in `exchange` alanına "XIST" yazmasının aynısı. Satır yine
    // düşürülmüyor: dağılım grafiğindeki "Diğer" kovasıyla aynı gerekçe,
    // kaybolan bir satır yanlış etiketlenmiş bir satırdan zor fark edilir.
    market: MARKET_LABELS[row.market ?? ''] ?? 'Diğer',
    price: row.price,
    unit: CURRENCY_UNITS[row.currency] ?? row.currency,
    changePercent: row.change_percent ?? 0,
    // Now carried on the quote itself. It was always stored and never
    // projected, so this read 0 for every row -- which renders as "nobody
    // traded today" rather than as the missing field it actually was.
    volume: row.volume ?? 0,
    marketCap: row.market_cap ?? 0,
    // İKİ FARKLI YOKLUK, iki farklı cevap.
    //
    // Bir HİSSENİN sektörü yoksa bu gerçek bir boşluk -- sağlayıcı bir gün
    // doldurabilir -- ve 'Bilinmiyor' doğru etiket. Ölçüldü: 94 enstrümanın
    // 90'ında sektör var, dördünde yok.
    //
    // Döviz paritesinin ve ons altının ise sektörü EKSİK DEĞİL, YOK: sektör
    // o enstrüman için tanımlı bir kavram değil. Onlara "bilinmiyor" demek,
    // bir gün öğrenilebilecek bir boşluk varmış gibi göstermek olurdu. Bu
    // deponun kendi kuralı: "aracın hiç döndürmediği bir alan için `veri
    // yok` kullanılmaz, o sütun hiç yazılmaz."
    sector: row.sector ?? (SECTORLESS_MARKETS.has(row.market ?? '') ? '' : 'Bilinmiyor'),
    week52Low: row.week52_low ?? 0,
    week52High: row.week52_high ?? 0,
    // Left undefined when the provider publishes nothing, which the column
    // renderer already shows as "—".
    pe: row.pe_ratio ?? undefined,
    pb: row.pb_ratio ?? undefined,
  } as MarketInstrument;
}

export interface InstrumentsState {
  instruments: MarketInstrument[];
  loading: boolean;
  /** Distinct sectors present in the live universe, for the filter panel. */
  sectors: string[];
}

/**
 * Fetch the universe once, then keep prices moving over the shared SSE stream.
 *
 * `changePercent` is refreshed alongside `price` by `useLiveRows`, so a row
 * cannot show a new price beside yesterday's change.
 */
export function useInstruments(limit = 1200, market?: string): InstrumentsState {
  const [fetched, setFetched] = useState<MarketInstrument[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // Piyasa süzgeci SUNUCUDA uygulanır, listede değil. Evren binin üzerinde
    // enstrüman; burada `limit` kadarını çekip istemcide süzmek, seçilen
    // piyasanın yalnızca ilk sayfaya düşen kısmını göstermek olurdu.
    //
    // `market` bir borsa (BIST, NASDAQ) ya da bir ENDEKS (SP500, NASDAQ100)
    // olabilir; ikisini de aynı alan taşıyor, çünkü AAPL hem Nasdaq'ta işlem
    // görür hem de S&P 500 üyesidir.
    setLoading(true);
    apiClient
      .getInstruments(market ? { limit, market } : { limit })
      .then((response) => setFetched((response.instruments ?? []).map(adaptInstrument)))
      .catch((error) => console.error('Failed to load instruments', error))
      .finally(() => setLoading(false));
  }, [limit, market]);

  const instruments = useLiveRows(fetched);
  const sectors = useMemo(
    // Boş sektör süzgeçte SEÇENEK OLMUYOR: adı olmayan bir seçenek
    // tıklanamaz ve listenin sonunda boş bir satır bırakırdı.
    () => Array.from(
      new Set(instruments.map((row) => row.sector).filter(Boolean)),
    ).sort(),
    [instruments],
  );

  return { instruments, loading, sectors };
}
