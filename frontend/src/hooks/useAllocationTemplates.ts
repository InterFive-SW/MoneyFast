/**
 * Hazır dağılım şablonları ve hedef formunun taslağı.
 *
 * Mantık burada, bileşende değil: kapsama kapısı `src/hooks/**` altını sayıyor,
 * JSX'i saymıyor (`vitest.config.ts`). `useAnalysisData` ve `useTradeFlow` ile
 * aynı gerekçe.
 *
 * Toplam-100 doğrulaması da burada. Bugün `HedefDagilimPaneli.tsx` içinde
 * JSX'te duruyordu; ikinci bir ekran onu kendi kopyasıyla yazsaydı biri
 * değişip diğeri kalabilirdi -- ve sunucu tam 100 istiyor, yani kopyaların
 * ayrışması kullanıcının kaydedemediği bir form demek.
 */
import { useCallback, useEffect, useState } from 'react';

import { apiClient, type AllocationTemplateItem, type AllocationTemplates } from '../api/client';

export const TEMPLATES_ERROR = 'Şablonlar yüklenemedi.';

/** Sunucunun kabul ettiği tek toplam. */
export const REQUIRED_TOTAL = 100;

export interface DraftRow {
    bucket: string;
    label: string;
    percent: number;
}

export interface AllocationTemplatesState {
    templates: AllocationTemplateItem[];
    declaredTolerance: string | null;
    measurementNote: string;
    /** Formun o anki hâli. Şablon seçmek bunu DOLDURUYOR, kaydetmiyor. */
    draft: DraftRow[];
    total: number;
    isValid: boolean;
    selectedKey: string | null;
    loading: boolean;
    error: string | null;
    selectTemplate: (key: string) => void;
    setPercent: (bucket: string, percent: number) => void;
    reload: () => void;
}

export function useAllocationTemplates(): AllocationTemplatesState {
    const [templates, setTemplates] = useState<AllocationTemplateItem[]>([]);
    const [declaredTolerance, setDeclaredTolerance] = useState<string | null>(null);
    const [measurementNote, setMeasurementNote] = useState('');
    const [draft, setDraft] = useState<DraftRow[]>([]);
    const [selectedKey, setSelectedKey] = useState<string | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [nonce, setNonce] = useState(0);

    useEffect(() => {
        let cancelled = false;
        setLoading(true);
        setError(null);
        apiClient
            .getAllocationTemplates()
            .then((data: AllocationTemplates) => {
                if (cancelled) return;
                setTemplates(data.items ?? []);
                setDeclaredTolerance(data.declaredTolerance ?? null);
                setMeasurementNote(data.measurementNote ?? '');
            })
            .catch(() => {
                if (!cancelled) setError(TEMPLATES_ERROR);
            })
            .finally(() => {
                if (!cancelled) setLoading(false);
            });
        return () => {
            cancelled = true;
        };
    }, [nonce]);

    const selectTemplate = useCallback(
        (key: string) => {
            const template = templates.find((item) => item.key === key);
            if (!template) return;
            setSelectedKey(key);
            // Şablon formu DOLDURUYOR, kaydetmiyor. Kaydeden şey kullanıcının
            // kendi PUT'u ve o adım ayrı duruyor.
            setDraft(
                template.weights.map((row) => ({
                    bucket: row.bucket,
                    label: row.label,
                    percent: row.percent,
                })),
            );
        },
        [templates],
    );

    const setPercent = useCallback((bucket: string, percent: number) => {
        // Şablondan sapıldığı anda seçim düşüyor: form artık o şablon değil ve
        // öyleymiş gibi göstermek kullanıcıya kaydedeceğinden başka bir şey
        // gösterirdi.
        setSelectedKey(null);
        setDraft((rows) =>
            rows.map((row) =>
                row.bucket === bucket
                    ? { ...row, percent: Number.isFinite(percent) ? percent : 0 }
                    : row,
            ),
        );
    }, []);

    const total = draft.reduce((sum, row) => sum + (row.percent || 0), 0);

    return {
        templates,
        declaredTolerance,
        measurementNote,
        draft,
        total,
        isValid: draft.length > 0 && total === REQUIRED_TOTAL,
        selectedKey,
        loading,
        error,
        selectTemplate,
        setPercent,
        reload: () => setNonce((value) => value + 1),
    };
}
