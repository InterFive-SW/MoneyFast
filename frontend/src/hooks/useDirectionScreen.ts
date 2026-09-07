/**
 * Gecelik hesaplanmış yön okumaları — Piyasalar ekranının taraması.
 *
 * **Bu bir "en iyi hisseler" listesi DEĞİL.** Sıralanan şey ölçülen kanıtların
 * meyli, bir cazibe sıralaması değil; `prompts.py`'deki "never rank by
 * attractiveness" kuralı sohbette olduğu gibi burada da geçerli. Ölçüm değeri
 * her satırda görünür duruyor ki sıralamanın neye göre yapıldığı okunabilsin.
 *
 * `computedAt` gizlenmiyor: bir okumanın ne zaman yapıldığını söylemeden
 * göstermek, dünkü ölçümü bugünün ölçümü gibi göstermek olurdu.
 *
 * Mantık burada, bileşende değil: kapsama kapısı `src/hooks/**` altını
 * sayıyor, JSX'i saymıyor.
 */
import { useCallback, useEffect, useState } from 'react';

import { apiClient, type DirectionScreenRow } from '../api/client';
import type { Horizon } from './useDirectionSignal';

export const SCREEN_ERROR = 'Yön taraması alınamadı.';

/** Süzgeç seçenekleri. "Tümü" bir yön DEĞİL: süzgecin yokluğu. */
export const SCREEN_FILTERS = [
    { key: '', label: 'Tümü' },
    { key: 'UP_LEAN', label: 'Yükseliş yönünde' },
    { key: 'DOWN_LEAN', label: 'Düşüş yönünde' },
] as const;

export interface DirectionScreenState {
    rows: DirectionScreenRow[];
    computedAt: string | null;
    /** Vade dışı bir istekte sunucunun döndürdüğü açıklama. */
    note: string | null;
    horizon: Horizon;
    setHorizon: (horizon: Horizon) => void;
    direction: string;
    setDirection: (direction: string) => void;
    loading: boolean;
    error: string | null;
}

export function useDirectionScreen(limit = 10): DirectionScreenState {
    const [rows, setRows] = useState<DirectionScreenRow[]>([]);
    const [computedAt, setComputedAt] = useState<string | null>(null);
    const [note, setNote] = useState<string | null>(null);
    const [horizon, setHorizon] = useState<Horizon>('3M');
    const [direction, setDirection] = useState<string>('UP_LEAN');
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        let cancelled = false;
        setLoading(true);
        setError(null);
        apiClient
            .getDirectionScreen(horizon, direction || undefined, limit)
            .then((data) => {
                if (cancelled) return;
                setRows(data.items ?? []);
                setComputedAt(data.computedAt ?? null);
                setNote(data.note ?? null);
            })
            .catch(() => {
                if (!cancelled) setError(SCREEN_ERROR);
            })
            .finally(() => {
                if (!cancelled) setLoading(false);
            });
        return () => {
            cancelled = true;
        };
    }, [horizon, direction, limit]);

    return {
        rows,
        computedAt,
        note,
        horizon,
        setHorizon: useCallback((next: Horizon) => setHorizon(next), []),
        direction,
        setDirection: useCallback((next: string) => setDirection(next), []),
        loading,
        error,
    };
}
