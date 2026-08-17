// src/components/chat/ContextPanel.tsx
import React from 'react';

interface ContextPanelProps {
  contextTopic: string | null;
}

/**
 * ContextPanel Bileşeni
 * 
 * Sohbet esnasında adı geçen finansal terimlerin (örn. hisse, portföy)
 * detaylı anlık verilerini gösteren sağ bilgi paneli.
 * Cosmos.so tasarım diline uygun cam görünümlü (glassmorphism) bir yapıdadır.
 */
export default function ContextPanel({ contextTopic }: ContextPanelProps) {
  if (!contextTopic) {
    return (
      <div className="h-full w-full bg-slate-50/50 backdrop-blur-xl border-l border-white/60 p-6 hidden md:flex flex-col items-center justify-center text-center">
        <div className="w-16 h-16 rounded-2xl bg-white shadow-sm text-emerald-500 flex items-center justify-center mb-5 border border-slate-100">
          <svg className="w-7 h-7" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
        </div>
        <h3 className="text-slate-700 font-semibold mb-2">Akıllı Bağlam Paneli</h3>
        <p className="text-slate-500 text-sm max-w-[220px] leading-relaxed">
          Sohbet esnasında bahsedilen hisse veya finansal varlıkların canlı verileri burada belirir.
        </p>
      </div>
    );
  }

  return (
    <div className="h-full w-full bg-slate-50/50 backdrop-blur-xl border-l border-white/60 p-6 hidden md:flex flex-col">
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-white shadow-sm flex items-center justify-center border border-slate-100 text-slate-700 font-bold">
            {contextTopic.substring(0, 2).toUpperCase()}
          </div>
          <h2 className="text-lg font-semibold text-slate-800">{contextTopic}</h2>
        </div>
        <span className="px-2.5 py-1 bg-emerald-100 text-emerald-700 rounded-lg text-xs font-semibold">Canlı</span>
      </div>

      <div className="space-y-4">
        {/* Fiyat Kartı */}
        <div className="p-5 bg-white/80 backdrop-blur-sm rounded-2xl border border-white shadow-sm">
          <p className="text-xs text-slate-500 mb-1 font-medium uppercase tracking-wider">Anlık Fiyat</p>
          <div className="flex items-end gap-2">
            <span className="text-3xl font-bold text-slate-800 tracking-tight">₺ 304.50</span>
            <span className="text-sm font-semibold text-emerald-500 mb-1 flex items-center">
              <svg className="w-3 h-3 mr-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 10l7-7m0 0l7 7m-7-7v18" />
              </svg>
              %2.4
            </span>
          </div>
        </div>

        {/* Haberler Kartı */}
        <div className="p-5 bg-white/80 backdrop-blur-sm rounded-2xl border border-white shadow-sm">
          <h4 className="text-sm font-semibold text-slate-800 mb-4 flex items-center gap-2">
            <svg className="w-4 h-4 text-teal-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 20H5a2 2 0 01-2-2V6a2 2 0 012-2h10a2 2 0 012 2v1m2 13a2 2 0 01-2-2V7m2 13a2 2 0 002-2V9.5a2.5 2.5 0 00-2.5-2.5H15" />
            </svg>
            Son Gelişmeler
          </h4>
          <ul className="space-y-4">
            <li className="flex gap-3 items-start">
              <div className="w-1.5 h-1.5 rounded-full bg-teal-400 mt-1.5 shrink-0"></div>
              <p className="text-[13px] text-slate-600 leading-relaxed">
                Şirketin yeni çeyrek bilançosunda beklentilerin üzerinde kâr açıklandı.
              </p>
            </li>
            <li className="flex gap-3 items-start">
              <div className="w-1.5 h-1.5 rounded-full bg-slate-300 mt-1.5 shrink-0"></div>
              <p className="text-[13px] text-slate-600 leading-relaxed">
                Yabancı yatırımcı oranı son 1 ayın en yüksek seviyesine ulaştı.
              </p>
            </li>
          </ul>
        </div>
      </div>
    </div>
  );
}
