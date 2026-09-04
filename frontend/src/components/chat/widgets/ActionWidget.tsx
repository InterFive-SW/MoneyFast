// src/components/chat/widgets/ActionWidget.tsx
import { useCallback, useState } from 'react';
import { ActionWidgetPayload } from '../../../types/chat';
import { api } from '../../../api/client';
import { useTradeFlow } from '../../../hooks/useTradeFlow';

interface ActionWidgetProps {
  payload: ActionWidgetPayload;
}

/**
 * ActionWidget Bileşeni
 * 
 * Yapay zeka asistanının kullanıcıya sunduğu aksiyon onay/red
 * butonlarını içeren interaktif widget bileşeni.
 * API entegrasyonu sayesinde onaylanan işlemler backend'e iletilir.
 */
export default function ActionWidget({ payload }: ActionWidgetProps) {
  const [toastMessage, setToastMessage] = useState<{ type: 'success' | 'error', message: string } | null>(null);

  /**
   * Önceden hazırlanmış öneriyi onaylar.
   *
   * Sistemde bir işlemin yetkilendirildiği TEK yer burası ve yapısı gereği
   * bir kullanıcı eylemi: ajan bu uç noktaya ulaşamıyor ve sohbette "evet"
   * demek onu tetiklemiyor.
   */
  const submit = useCallback(async () => {
    setToastMessage(null);
    try {
      const result = await api.confirmProposal(payload.proposalId ?? payload.actionId);
      setToastMessage({ type: 'success', message: result?.message ?? 'İşlem onaylandı.' });
    } catch (error) {
      console.error("İşlem onayı sırasında hata oluştu:", error);
      // Süresi dolmuş bir öneri geçici bir hata değil; tekrar denemek işe
      // yaramaz, kullanıcının yeniden hazırlatması gerekiyor.
      const expired = error instanceof Error && error.message.includes('410');
      throw new Error(
        expired
          ? 'Bu önerinin süresi doldu. Lütfen işlemi yeniden hazırlatın.'
          : 'İşlem onaylanırken bir hata oluştu. Lütfen tekrar deneyiniz.',
      );
    }
  }, [payload.proposalId, payload.actionId]);

  // `review`'dan başlıyor: öneriyi ajan zaten hazırladı, kullanıcının
  // girecek bir şeyi yok. Panel akışıyla AYNI durum makinesi -- ikisi onayın
  // ne demek olduğu konusunda ayrışmamalı.
  const flow = useTradeFlow({ onSubmit: submit, initialStage: 'review' });

  return (
    <div className="mt-3 w-full relative">
      <div className="bg-slate-900/50 backdrop-blur-xl rounded-xl p-4 border border-white/10 shadow-2xl flex flex-col gap-3 shadow-sm transition-all">
        <p className="text-sm font-medium leading-relaxed text-slate-200">{payload.message}</p>

        {flow.stage === 'review' || flow.stage === 'error' ? (
          <>
            {flow.stage === 'error' && (
              <p className="text-sm text-rose-400">{flow.error}</p>
            )}
            <div className="flex w-full gap-2">
              <button
                onClick={flow.accept}
                className="flex-1 rounded-lg bg-emerald-500 px-3 py-2 text-sm font-medium text-white shadow-sm transition-colors hover:bg-emerald-600"
              >
                {payload.confirmLabel}
              </button>
              <button
                onClick={flow.reject}
                className="flex-1 rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm font-medium text-slate-300 transition-colors hover:bg-white/10"
              >
                {payload.cancelLabel}
              </button>
            </div>
          </>
        ) : flow.stage === 'countdown' ? (
          <div className="flex flex-col gap-2">
            <button
              onClick={flow.submitNow}
              className="w-full rounded-lg bg-emerald-500 px-3 py-2 text-sm font-medium text-white shadow-sm transition-colors hover:bg-emerald-600"
            >
              Onayla ({flow.remaining} sn)
            </button>
            <button
              onClick={flow.cancel}
              className="w-full rounded-lg border border-rose-500/25 bg-rose-500/10 px-3 py-1.5 text-xs font-semibold text-rose-300 transition-colors hover:bg-rose-500/20"
            >
              İptal
            </button>
            <p className="text-center text-[11px] text-slate-500">
              {flow.remaining} saniye sonra iletilecek.
            </p>
          </div>
        ) : flow.stage === 'submitting' ? (
          <p className="text-center text-sm text-slate-400">İletiliyor…</p>
        ) : (
          <div className="mt-1 rounded-lg border border-emerald-500/25 bg-emerald-500/10 px-3 py-2 text-center text-sm font-medium text-emerald-300">
            İşlem yetkilendirildi.
          </div>
        )}
      </div>

      {toastMessage && (
        <p
          className={`mt-2 text-xs ${
            toastMessage.type === 'success' ? 'text-emerald-400' : 'text-rose-400'
          }`}
        >
          {toastMessage.message}
        </p>
      )}
    </div>
  );
}
