/**
 * Dengeleme planı ve satır satır emir akışı.
 *
 * **Toplu onay YOK, bilerek.** Her satırın kendi onayı var ve o onay mevcut
 * `stage` -> `confirm` yolundan geçiyor; yeni bir toplu-öneri şeması,
 * kısmi başarısızlığın ne anlama geldiğini yeniden tanımlamayı gerektirirdi
 * (üç emirden ikisi tuttuysa geri alma yolu yok).
 *
 * Mantık burada, bileşende değil: kapsama kapısı `src/hooks/**` altını
 * sayıyor, JSX'i saymıyor.
 */
import { useCallback, useEffect, useState } from 'react';

import { apiClient, type RebalancePlan, type RebalanceRow } from '../api/client';

export const PLAN_ERROR = 'Dengeleme planı yüklenemedi.';

/** Bir satırın durumu. Satırlar birbirinden BAĞIMSIZ: birinin hatası
 *  diğerlerini durdurmuyor. */
export type RowStatus = 'idle' | 'submitting' | 'done' | 'error';

export interface RowState {
    status: RowStatus;
    error: string | null;
}

export interface RebalancePlanState {
    plan: RebalancePlan | null;
    loading: boolean;
    error: string | null;
    rowState: Record<string, RowState>;
    /**
     * Bu oturumda onaylanan satır sayısı. Plan yenilendiğinde SIFIRLANMIYOR:
     * onaylanan bir satış satırı yeni planda genellikle yok, dolayısıyla satır
     * durumundan sayılan bir sayaç her onaydan sonra sıfıra dönerdi.
     */
    confirmed: number;
    /** Hâlâ hatalı duran satır sayısı. */
    failed: number;
    confirmRow: (row: RebalanceRow) => Promise<void>;
    reload: () => void;
}

/**
 * Satırın kimliği. Sembol TEK BAŞINA yetmiyor: aynı sembol iki kovada
 * görünemez ama yön (alış/satış) satırın kimliğinin parçası ve bir sonraki
 * planda değişebiliyor.
 */
export function rowKey(row: RebalanceRow): string {
    return `${row.bucket}:${row.symbol}:${row.side}`;
}

export function useRebalancePlan(): RebalancePlanState {
    const [plan, setPlan] = useState<RebalancePlan | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [rowState, setRowState] = useState<Record<string, RowState>>({});
    const [confirmed, setConfirmed] = useState(0);
    const [nonce, setNonce] = useState(0);

    useEffect(() => {
        let cancelled = false;
        setLoading(true);
        setError(null);
        apiClient
            .getRebalancePlan()
            .then((data) => {
                if (cancelled) return;
                setPlan(data);
                // Başarılı satırların işareti düşüyor: onaylanan bir satır
                // yeni planda genellikle yok ve "onaylandı" etiketini artık
                // var olmayan bir satırın üzerinde bırakmak yanıltırdı.
                // HATALAR kalıyor -- kullanıcı hangi satırın tutmadığını
                // görüp yeniden deneyebilmeli.
                setRowState((state) =>
                    Object.fromEntries(
                        Object.entries(state).filter(
                            ([, row]) => row.status === 'error',
                        ),
                    ),
                );
            })
            .catch(() => {
                if (!cancelled) setError(PLAN_ERROR);
            })
            .finally(() => {
                if (!cancelled) setLoading(false);
            });
        return () => {
            cancelled = true;
        };
    }, [nonce]);

    const reload = useCallback(() => setNonce((value) => value + 1), []);

    const confirmRow = useCallback(
        async (row: RebalanceRow) => {
            const key = rowKey(row);
            setRowState((state) => ({
                ...state,
                [key]: { status: 'submitting', error: null },
            }));
            try {
                const me = await apiClient.getCurrentUser();
                const proposal = await apiClient.stageTransaction({
                    user_id: me.id,
                    transaction_type: row.side,
                    source_account_id: 'TR-DEMO-0001',
                    // Satır başına ayrı anahtar: aynı milisaniyede iki satır
                    // gönderilirse tek bir zaman damgası ikisini de aynı
                    // öneriye bağlardı.
                    idempotency_key: `rebalance-${key}-${Date.now()}`,
                    instrument: { symbol: row.symbol },
                    quantity: row.quantity,
                    order_type: 'MARKET',
                    time_in_force: 'DAY',
                    assumptions: [],
                } as never);
                const staged = proposal as { status?: string; blockers?: string[]; proposal_id: string };
                if (staged.status !== 'PENDING_USER_CONFIRMATION') {
                    throw new Error((staged.blockers ?? []).join(' ') || 'Öneri hazırlanamadı.');
                }
                await apiClient.confirmProposal(staged.proposal_id);
                setRowState((state) => ({
                    ...state,
                    [key]: { status: 'done', error: null },
                }));
                setConfirmed((count) => count + 1);
                // Portföy değişti: plan ZORUNLU yeniden yükleniyor. Eski planı
                // ekranda bırakmak, artık doğru olmayan bir farkı doğruymuş
                // gibi göstermek olurdu.
                reload();
            } catch (err) {
                setRowState((state) => ({
                    ...state,
                    [key]: {
                        status: 'error',
                        error: (err as Error)?.message || 'Emir gönderilemedi.',
                    },
                }));
            }
        },
        [reload],
    );

    const states = Object.values(rowState);
    return {
        plan,
        loading,
        error,
        rowState,
        confirmed,
        failed: states.filter((row) => row.status === 'error').length,
        confirmRow,
        reload,
    };
}
