/**
 * Haberlerin yorumlanmış özeti: portföye ait olan ve piyasa geneli.
 *
 * **Cümle SUNUCUDAN geliyor ve burada yeniden kurulmuyor.** Sunucu tarafında
 * her cümle koşullu ve çekincesini aynı nefeste taşıyor; arayüzde ikinci kez
 * kurulan bir cümle o çivinin dışında kalırdı. Bu hook'un işi cümleyi
 * kurmak değil, hangi cümlenin gösterileceğini yönetmek: pencere, açılan
 * satır ve hata.
 *
 * İki hook tek dosyada çünkü aynı gövdeyi okuyorlar (`NewsImpactEntry`) ve
 * ayrı dosyalara bölmek, biri değişince diğerinin sessizce ayrışabileceği bir
 * yer açardı.
 *
 * Mantık burada, bileşende değil: kapsama kapısı `src/hooks/**` altını
 * sayıyor, JSX'i saymıyor.
 */
import { useCallback, useEffect, useState } from 'react';

import { apiClient, type NewsDigest, type NewsImpactEntry } from '../api/client';

export const DIGEST_ERROR = 'Haber özeti alınamadı.';

/** Sunulabilir pencereler. Kapalı küme: sunucu 1-168 saat kabul ediyor ama
 *  ekranda okunabilir olan üç aralık bu. "Bugün" varsayılan, çünkü panelin
 *  sorusu "bugün portföyüme ne dokundu". */
export const DIGEST_WINDOWS = [
    { hours: 24, label: 'Son 24 saat' },
    { hours: 72, label: 'Son 3 gün' },
    { hours: 168, label: 'Son 7 gün' },
] as const;

export interface NewsDigestState {
    headline: string;
    entries: NewsImpactEntry[];
    disclaimer: string;
    hours: number;
    setHours: (hours: number) => void;
    /** Gerekçeleri açık olan sembol. Tek satır açık: bir ekranda on iki
     *  gerekçe listesi birden, okunacak bir metin değil bir duvar olurdu. */
    expanded: string | null;
    toggle: (symbol: string) => void;
    loading: boolean;
    error: string | null;
}

/** Hangi beslemenin okunacağı. Fonksiyon değil bir ETİKET geçiliyor: her
 *  render'da yeniden kurulan bir yükleyici fonksiyonu bağımlılık listesinde
 *  sonsuz döngü olurdu, listeden çıkarmak ise sessizce eskiyen bir kapanış. */
type Feed = 'portfolio' | 'market';

function useImpactFeed(feed: Feed, initialHours: number, limit: number) {
    const [entries, setEntries] = useState<NewsImpactEntry[]>([]);
    const [headline, setHeadline] = useState('');
    const [disclaimer, setDisclaimer] = useState('');
    const [hours, setHours] = useState(initialHours);
    const [expanded, setExpanded] = useState<string | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        let cancelled = false;
        setLoading(true);
        setError(null);
        // İki uç aynı gövdeyi döndürüyor, tek farkla: piyasa genelinde
        // özetlenecek bir portföy olmadığı için `headline` yok. Ortak şekil
        // burada adlandırılıyor -- birleşim tipini olduğu gibi taşımak,
        // eksik alanı her okumada daraltma gerektirirdi.
        const request: Promise<Partial<NewsDigest>> =
            feed === 'portfolio'
                ? apiClient.getNewsDigest(hours)
                : apiClient.getNewsImpactSummary(hours, limit);
        request
            .then((data) => {
                if (cancelled) return;
                setEntries(data.entries ?? []);
                setHeadline(data.headline ?? '');
                // Çekince sunucudan geliyor ve burada YEDEĞİ YOK: arayüzde
                // yazılı bir kopya, sunucudaki metin değiştiğinde sessizce
                // eskiyen ikinci bir çekince olurdu.
                setDisclaimer(data.disclaimer ?? '');
            })
            .catch(() => {
                if (!cancelled) setError(DIGEST_ERROR);
            })
            .finally(() => {
                if (!cancelled) setLoading(false);
            });
        return () => {
            cancelled = true;
        };
    }, [feed, hours, limit]);

    return {
        entries,
        headline,
        disclaimer,
        hours,
        setHours: useCallback((next: number) => setHours(next), []),
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

/** Portföyün günlük haber özeti. Oturum zorunlu; sunucu kullanıcıyı
 *  token'dan çözüyor ve demo portföyüne düşmüyor. */
export function useNewsDigest(initialHours = 24): NewsDigestState {
    return useImpactFeed('portfolio', initialHours, 0);
}

/** Piyasa geneli. `headline` boş: burada özetlenecek bir portföy yok. */
export function useNewsImpactSummary(
    initialHours = 24,
    limit = 12,
): NewsDigestState {
    return useImpactFeed('market', initialHours, limit);
}
