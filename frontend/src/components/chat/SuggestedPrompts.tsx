// src/components/chat/SuggestedPrompts.tsx

interface SuggestedPromptsProps {
  onSelectPrompt: (prompt: string) => void;
}

/**
 * SuggestedPrompts Bileşeni
 * 
 * Sohbet girdi alanının üzerinde yatay olarak kaydırılabilir (horizontal scroll) 
 * öneri butonlarını (chip/pill) barındırır.
 */
export default function SuggestedPrompts({ onSelectPrompt }: SuggestedPromptsProps) {
  const prompts = [
    "SASA'nın son çeyrek bilançosunu basitçe anlat",
    "THYAO'da son dönemde öne çıkan gelişmeler neler?",
    "BIST 100'de bugün en çok kazandıranlar",
    "Apple (AAPL) finansal özetini getir",
    "TLY ve PHE fonlarının getiri ve portföy dağılımını karşılaştır"
  ];

  return (
    <div className="w-full flex flex-wrap justify-center gap-3">
      {prompts.map((prompt, index) => (
        <button 
          key={index}
          onClick={() => onSelectPrompt(prompt)}
          className="px-5 py-3 rounded-2xl border border-white/10 bg-slate-800 hover:bg-slate-700 text-sm font-medium text-slate-200 transition-colors cursor-pointer shadow-sm"
        >
          {prompt}
        </button>
      ))}
    </div>
  );
}
