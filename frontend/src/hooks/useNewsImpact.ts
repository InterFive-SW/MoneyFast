/**
 * Haber okumasının ÖLÇÜLEN zemini.
 *
 * **Bu hook yorum taşımıyor ve taşımayacak.** Sunucudan gelen her değer
 * sayılmış ya da ölçülmüş: kaç haber, kaçı bildirim, hisse ne yaptı, o
 * hissede normal bir hareket ne kadar. Haberlerin ne anlama geldiğine dair
 * okuma sohbet turunda kuruluyor ve orada uygunluk kapısından geçiyor;
 * aynı okumayı ekranda ikinci kez kurmak, o kapıdan geçmeyen bir kopya
 * üretirdi.
 *
 * Mantık burada, bileşende değil: kapsama kapısı `src/hooks/**` altını
 * sayıyor, JSX'i saymıyor.
 */
import { useCallback, useEffect, useState } from 'react';

import { apiClient, type NewsImpactPackage, type NewsImpactSymbol } from '../api/client';

export const IMPACT_ERROR = 'Haber ölçümleri alınamadı.';

/** Sunulabilir pencereler.
 *
 *  Varsayılan doksan gün ve daha kısası "daha güncel" DEĞİL, daha boş:
 *  ölçüldü, otuz gün bir test portföyünde tek bir başlık buluyor, doksan
 *  gün dokuz. Sebep eşleştirmenin bilerek dar olması. */
export const IMPACT_WINDOWS = [
    { days: 30, label: 'Son 30 gün' },
    { days: 90, label: 'Son 90 gün' },
    { days: 180, label: 'Son 180 gün' },
] as const;

export interface NewsImpactState {
    rows: NewsImpactSymbol[];
    coverage: NewsImpactPackage['coverage'] | null;
    days: number;
    setDays: (days: number) => void;
    /** Başlıkları açık olan sembol. Tek satır açık: beş sembolün başlıkları
     *  birden, okunacak bir liste değil bir duvar olurdu. */
    expanded: string | null;
    toggle: (symbol: string) => void;
    loading: boolean;
    error: string | null;
}

export function useNewsImpact(initialDays = 90, limit = 5): NewsImpactState {
    const [rows, setRows] = useState<NewsImpactSymbol[]>([]);
    const [coverage, setCoverage] = useState<NewsImpactPackage['coverage'] | null>(null);
    const [days, setDays] = useState(initialDays);
    const [expanded, setExpanded] = useState<string | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        let cancelled = false;
        setLoading(true);
        setError(null);
        apiClient
            .getNewsImpact(days, limit)
            .then((data) => {
                if (cancelled) return;
                setRows(data.symbols ?? []);
                // Kapsama SAKLANMIYOR: listelenenlerin portföyün tamamı
                // olduğunu sanan bir okuyucu, dar bir kapsamı geniş sanır.
                setCoverage(data.coverage ?? null);
            })
            .catch(() => {
                if (!cancelled) setError(IMPACT_ERROR);
            })
            .finally(() => {
                if (!cancelled) setLoading(false);
            });
        return () => {
            cancelled = true;
        };
    }, [days, limit]);

    return {
        rows,
        coverage,
        days,
        setDays: useCallback((next: number) => setDays(next), []),
        expanded,
        toggle: useCallback(
            (symbol: string) =>
                setExpanded((current) => (current === symbol ? null : symbol)),
            [],
        ),
        loading,
        error,
    };
}

/** Bir hareketi KENDİ aralığına karşı okuyan cümle.
 *
 *  "%5 düştü" tek başına hiçbir şey söylemiyor; "bu sembolde beş günlük
 *  hareketler tipik olarak %2 büyüklüğünde" ile birlikte söylüyor. Tipik
 *  hareket ölçülemediğinde büyüklük hakkında HİÇBİR ŞEY denmiyor -- burada
 *  `null` dönmek, arayüzün o satırı hiç yazmaması demek. */
export function moveStatement(row: NewsImpactSymbol): string | null {
    const { recent_move_pct: recent, typical_move_pct: typical, window_days: window } =
        row.price;
    if (recent === null || typical === null) return null;
    const direction = recent >= 0 ? 'yükseldi' : 'geriledi';
    const fmt = (value: number) =>
        `%${Math.abs(value).toLocaleString('tr-TR', {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2,
        })}`;
    return (
        `Son ${window} işlem gününde ${fmt(recent)} ${direction}; ` +
        `bu sembolde ${window} günlük hareketler tipik olarak ` +
        `${fmt(typical)} büyüklüğünde.`
    );
}

/** Kapsama cümlesi. Kaç pozisyon dışarıda kaldı ve haberin kaynağı ne.
 *
 *  Bildirimin ihraççısı makine okunur bir alanda yazılı; besleme haberi
 *  metinden eşleştirildi. İkisini aynı kefeye koymak, kapsamanın nereden
 *  geldiğini gizlerdi. */
export function coverageStatement(
    coverage: NewsImpactPackage['coverage'] | null,
): string | null {
    if (!coverage) return null;
    const parts = [
        `${coverage.filings} bildirim ve ${coverage.feed_articles} haber okundu`,
    ];
    if (coverage.symbols_omitted > 0) {
        parts.push(
            `${coverage.symbols} pozisyonun ${coverage.symbols_omitted} tanesi ` +
            'bu listede yok',
        );
    }
    return `${parts.join('; ')}.`;
}
