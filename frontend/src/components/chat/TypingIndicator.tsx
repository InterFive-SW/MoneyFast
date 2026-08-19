// src/components/chat/TypingIndicator.tsx
import React from 'react';

interface TypingIndicatorProps {
  thought?: string;
}

/**
 * TypingIndicator Bileşeni
 * 
 * Yapay zeka yanıt üretirken kullanıcıya gösterilen bekleme animasyonudur.
 * Sıçrayan üç nokta animasyonu ve varsa o anki düşünce sürecini (chain of thought) içerir.
 */
export default function TypingIndicator({ thought }: TypingIndicatorProps) {
  return (
    <div className="flex justify-start w-full my-4">
      <div className="flex flex-col gap-2 max-w-[85%]">
        <div className="flex items-center gap-2 bg-slate-800/80 backdrop-blur-md border border-white/10 shadow-sm rounded-2xl rounded-bl-sm px-4 py-3 w-fit">
          <div className="w-8 h-8 rounded-full bg-emerald-100 flex items-center justify-center text-brandBlue font-bold text-xs shrink-0">
            MF
          </div>
          <div className="flex gap-1 items-center h-5 px-1">
            <div className="w-1.5 h-1.5 bg-slate-400 rounded-full animate-bounce [animation-delay:-0.3s]"></div>
            <div className="w-1.5 h-1.5 bg-slate-400 rounded-full animate-bounce [animation-delay:-0.15s]"></div>
            <div className="w-1.5 h-1.5 bg-slate-400 rounded-full animate-bounce"></div>
          </div>
        </div>
        {thought && (
          <div className="ml-1 flex items-center gap-2 text-xs font-medium text-slate-400 animate-pulse">
            <svg className="w-3.5 h-3.5 text-emerald-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
            </svg>
            {thought}
          </div>
        )}
      </div>
    </div>
  );
}
