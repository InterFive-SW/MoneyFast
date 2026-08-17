// src/components/chat/TypingIndicator.tsx
import React from 'react';

/**
 * TypingIndicator Bileşeni
 * 
 * Yapay zeka yanıt üretirken kullanıcıya gösterilen bekleme animasyonudur.
 * Sıçrayan üç nokta animasyonu içerir.
 */
export default function TypingIndicator() {
  return (
    <div className="flex justify-start w-full my-4">
      <div className="flex items-center gap-2 bg-white/80 backdrop-blur-sm border border-slate-200 shadow-sm rounded-2xl rounded-bl-sm px-4 py-3">
        <div className="w-8 h-8 rounded-full bg-emerald-100 flex items-center justify-center text-emerald-600 font-bold text-xs shrink-0">
          MF
        </div>
        <div className="flex gap-1 items-center h-5 px-1">
          <div className="w-1.5 h-1.5 bg-slate-400 rounded-full animate-bounce [animation-delay:-0.3s]"></div>
          <div className="w-1.5 h-1.5 bg-slate-400 rounded-full animate-bounce [animation-delay:-0.15s]"></div>
          <div className="w-1.5 h-1.5 bg-slate-400 rounded-full animate-bounce"></div>
        </div>
      </div>
    </div>
  );
}
