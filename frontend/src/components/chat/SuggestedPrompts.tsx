// src/components/chat/SuggestedPrompts.tsx
import React from 'react';

interface SuggestedPromptsProps {
  onSelectPrompt: (prompt: string) => void;
}

/**
 * SuggestedPrompts Bileşeni
 * 
 * Sohbet geçmişi boş olduğunda kullanıcıya sunulan örnek finansal komutları barındırır.
 */
export default function SuggestedPrompts({ onSelectPrompt }: SuggestedPromptsProps) {
  const prompts = [
    "Portföyümün risk analizini yap",
    "Bugün en çok kazandıran BIST hisseleri neler?",
    "Apple (AAPL) son çeyrek bilançosunu özetle"
  ];

  return (
    <div className="flex flex-col items-center justify-center h-full w-full p-6 transition-opacity duration-500 opacity-100">
      <h2 className="text-2xl font-medium text-slate-800 mb-8">Nasıl yardımcı olabilirim?</h2>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 w-full max-w-4xl">
        {prompts.map((prompt, index) => (
          <div 
            key={index}
            onClick={() => onSelectPrompt(prompt)}
            className="bg-white/60 border border-slate-200 hover:border-emerald-400 hover:shadow-md hover:-translate-y-1 transition-all cursor-pointer rounded-xl p-4 flex items-center justify-center text-center text-slate-700 font-medium"
          >
            {prompt}
          </div>
        ))}
      </div>
    </div>
  );
}
