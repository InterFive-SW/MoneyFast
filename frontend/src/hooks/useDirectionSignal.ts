/**
 * Bir enstrümanın yön okuması.
 *
 * Sohbetle AYNI uç noktayı okuyor: ayrı hesaplasalardı aynı hisse için farklı
 * bir yön söyleyebilirlerdi -- `useAnalysisData`'nın ve `get_technicals`'ın
 * kendi gerekçesiyle aynı.
 *
 * Mantık burada, bileşende değil: kapsama kapısı `src/hooks/**` altını
 * sayıyor, JSX'i saymıyor.
 */
import { useCallback, useEffect, useState } from 'react';

import { apiClient, type DirectionSignal } from '../api/client';

export const DIRECTION_ERROR = 'Yön okuması alınamadı.';

/** Sunucunun kabul ettiği vadeler. Sunucudaki `signals.HORIZONS` ile aynı
 *  küme; ayrışırsa kullanıcı sorduğundan başka bir vadenin okumasını alır. */
export const HORIZONS = ['1M', '3M', '6M'] as const;
export type Horizon = (typeof HORIZONS)[number];

export const HORIZON_LABELS: Record<Horizon, string> = {
    '1M': '1 ay',
    '3M': '3 ay',
    '6M': '6 ay',
};

/** Okumanın Türkçe başlığı. Ham enum kullanıcıya hiç ulaşmıyor. */
export const DIRECTION_LABELS: Record<string, string> = {
    UP_LEAN: 'Yükseliş yönünde',
    DOWN_LEAN: 'Düşüş yönünde',
    MIXED: 'İki yöne birden',
    INSUFFICIENT: 'Ölçüm yetersiz',
    OUT_OF_RANGE: 'Bu vade ölçülemiyor',
};

export interface DirectionSignalState {
    signal: DirectionSignal | null;
    horizon: Horizon;
    setHorizon: (horizon: Horizon) => void;
    /** Yön lehine ve karşı ölçümler, ayrı listeler. Karşı tarafı gizlemek
     *  sonucu desteksiz bırakırdı. */
    supporting: string[];
    opposing: string[];
    loading: boolean;
    error: string | null;
}

export function useDirectionSignal(symbol: string | undefined): DirectionSignalState {
    const [signal, setSignal] = useState<DirectionSignal | null>(null);
    const [horizon, setHorizon] = useState<Horizon>('3M');
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        if (!symbol) {
            setSignal(null);
            return;
        }
        let cancelled = false;
        setLoading(true);
        setError(null);
        apiClient
            .getDirectionSignal(symbol, horizon)
            .then((data) => {
                if (!cancelled) setSignal(data);
            })
            .catch(() => {
                if (!cancelled) setError(DIRECTION_ERROR);
            })
            .finally(() => {
                if (!cancelled) setLoading(false);
            });
        return () => {
            cancelled = true;
        };
    }, [symbol, horizon]);

    const evidence = signal?.evidence ?? [];
    return {
        signal,
        horizon,
        setHorizon: useCallback((next: Horizon) => setHorizon(next), []),
        supporting: evidence.filter((row) => row.direction === 'UP').map((row) => row.text),
        opposing: evidence.filter((row) => row.direction === 'DOWN').map((row) => row.text),
        loading,
        error,
    };
}
