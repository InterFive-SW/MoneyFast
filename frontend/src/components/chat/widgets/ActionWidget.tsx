// src/components/chat/widgets/ActionWidget.tsx
import React, { useState } from 'react';
import { ActionWidgetPayload } from '../../../types/chat';
import { api } from '../../../api/client';

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
  const [status, setStatus] = useState<'pending' | 'loading' | 'confirmed' | 'cancelled'>('pending');
  const [toastMessage, setToastMessage] = useState<{ type: 'success' | 'error', message: string } | null>(null);

  /**
   * İşlemi onaylar ve backend servisine iletir.
   * Yükleme durumu esnasında butonlarda animasyon gösterir.
   */
  const handleConfirm = async () => {
    setStatus('loading');
    setToastMessage(null);

    try {
      // Backend'in bizden beklediği Pydantic şemasına tam uyumlu istek atıyoruz
      await api.confirmOrder({
        order_id: payload.actionId,
        action: payload.action,
        asset: payload.asset,
        amount: payload.amount,
      });
      
      setStatus('confirmed');
      setToastMessage({ type: 'success', message: 'İşlem başarıyla onaylandı ve sıraya alındı.' });
    } catch (error) {
      console.error("İşlem onayı sırasında hata oluştu:", error);
      setStatus('pending'); // Tekrar denemesi için pending'e çekiyoruz
      setToastMessage({ type: 'error', message: 'İşlem onaylanırken bir hata oluştu. Lütfen tekrar deneyiniz.' });
      
      // Hata mesajını 5 saniye sonra gizle
      setTimeout(() => setToastMessage(null), 5000);
    }
  };

  /**
   * Kullanıcı işlemi reddettiğinde durumu günceller.
   */
  const handleCancel = () => {
    setStatus('cancelled');
    setToastMessage({ type: 'error', message: 'İşlem iptal edildi.' });
  };

  return (
    <div className="mt-3 w-full relative">
      <div className="bg-slate-900/50 backdrop-blur-xl rounded-xl p-4 border border-white/10 shadow-2xl flex flex-col gap-3 shadow-sm transition-all">
        <p className="text-sm font-medium text-slate-700 leading-relaxed">{payload.message}</p>
        
        {status === 'pending' || status === 'loading' ? (
          <div className="flex flex-col gap-2 w-full mt-1">
            <div className="flex gap-2 w-full">
              <button 
                onClick={handleConfirm}
                disabled={status === 'loading'}
                className="flex-1 flex justify-center items-center gap-2 px-3 py-2 bg-emerald-500 hover:bg-emerald-600 text-white text-sm font-medium rounded-lg transition-colors shadow-sm disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {status === 'loading' ? (
                  <svg className="animate-spin h-4 w-4 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                  </svg>
                ) : null}
                {payload.confirmLabel}
              </button>
              <button 
                onClick={handleCancel}
                disabled={status === 'loading'}
                className="flex-1 px-3 py-2 bg-white hover:bg-slate-50 text-slate-300 text-sm font-medium border border-slate-200 rounded-lg transition-colors shadow-sm disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {payload.cancelLabel}
              </button>
            </div>
          </div>
        ) : (
          <div className={`text-sm font-medium px-3 py-2 rounded-lg text-center mt-1 border transition-all duration-300 ease-in-out ${
            status === 'confirmed' 
              ? 'bg-emerald-50 border-white/10 text-emerald-700 shadow-[0_0_15px_rgba(16,185,129,0.1)]' 
              : 'bg-rose-50 border-rose-100 text-rose-700'
          }`}>
            {status === 'confirmed' ? 'İşlem yetkilendirildi.' : 'İşlem sonlandırıldı.'}
          </div>
        )}
      </div>

      {/* Elegant Toast Bildirimi (Cosmos.so ilhamlı) */}
      {toastMessage && (
        <div className={`absolute -bottom-14 left-0 right-0 mx-auto w-[90%] text-center px-4 py-2 rounded-lg text-xs font-medium shadow-md transition-all animate-fade-in-up border ${
          toastMessage.type === 'success'
            ? 'bg-emerald-500 border-emerald-600 text-white shadow-emerald-500/20'
            : 'bg-rose-500 border-rose-600 text-white shadow-rose-500/20'
        }`}>
          {toastMessage.message}
        </div>
      )}
    </div>
  );
}
