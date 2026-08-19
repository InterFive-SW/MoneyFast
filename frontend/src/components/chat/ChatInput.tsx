// src/components/chat/ChatInput.tsx
import React, { useState, KeyboardEvent, useRef, useEffect } from 'react';

interface ChatInputProps {
  onSendMessage: (text: string) => void;
  disabled?: boolean;
}

/**
 * ChatInput Bileşeni
 * 
 * Ekranın en altına sabitlenmiş mesaj gönderme formudur.
 * Kullanıcı girdisini alır ve üst bileşene iletir.
 */
export default function ChatInput({ onSendMessage, disabled = false }: ChatInputProps) {
  const [inputText, setInputText] = useState<string>('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Metin kutusunun yüksekliğini içeriğe göre ayarla
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 128)}px`;
    }
  }, [inputText]);

  const handleSend = () => {
    if (inputText.trim() && !disabled) {
      onSendMessage(inputText.trim());
      setInputText('');
      if (textareaRef.current) {
        textareaRef.current.style.height = 'auto';
      }
    }
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    // Sadece Enter'a basıldığında mesaj gönder (Shift+Enter yeni satır)
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="w-full flex flex-col items-center">
      <div className="w-full max-w-4xl relative flex flex-col bg-slate-800/50 border border-white/10 rounded-3xl p-3 shadow-sm focus-within:ring-2 focus-within:ring-brandBlue/20 focus-within:border-brandBlue transition-all">
        <textarea
          ref={textareaRef}
          value={inputText}
          onChange={(e) => setInputText(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Yapay zeka asistanına sorunuzu yazın..."
          disabled={disabled}
          rows={1}
          className="w-full bg-transparent border-none px-3 py-2 focus:outline-none focus:ring-0 resize-none overflow-y-auto min-h-[48px] max-h-32 text-white placeholder-slate-500"
        />
        
        <div className="flex items-center justify-between mt-2 px-1">
          <div className="flex items-center gap-2">
            <button type="button" className="p-2 text-slate-400 hover:text-slate-300 hover:bg-white/10 rounded-full transition-colors" aria-label="Dosya Ekle">
              <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor" className="w-5 h-5">
                <path strokeLinecap="round" strokeLinejoin="round" d="m18.375 12.739-7.693 7.693a4.5 4.5 0 0 1-6.364-6.364l10.94-10.94A3 3 0 1 1 19.5 7.372L8.552 18.32m.009-.01-.01.01m5.699-9.941-7.81 7.81a1.5 1.5 0 0 0 2.112 2.13" />
              </svg>
            </button>
            <button type="button" className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-800 border border-white/10 rounded-full text-xs font-medium text-slate-300 hover:bg-slate-700 transition-colors shadow-sm">
              <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor" className="w-3.5 h-3.5 text-blue-500">
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 21a9.004 9.004 0 0 0 8.716-6.747M12 21a9.004 9.004 0 0 1-8.716-6.747M12 21c2.485 0 4.5-4.03 4.5-9S14.485 3 12 3m0 18c-2.485 0-4.5-4.03-4.5-9S9.515 3 12 3m0 0a8.997 8.997 0 0 1 7.843 4.582M12 3a8.997 8.997 0 0 0-7.843 4.582m15.686 0A11.953 11.953 0 0 1 12 10.5c-2.998 0-5.74-1.1-7.843-2.918m15.686 0A8.959 8.959 0 0 1 21 12c0 .778-.099 1.533-.284 2.253m0 0A17.919 17.919 0 0 1 12 16.5c-3.162 0-6.133-.815-8.716-2.247m0 0A9.015 9.015 0 0 1 3 12c0-1.605.42-3.113 1.157-4.418" />
              </svg>
              Web
            </button>
            <button type="button" className="flex items-center gap-1.5 px-3 py-1.5 bg-transparent text-xs font-medium text-slate-300 hover:bg-white/10 rounded-full transition-colors">
              Hızlı
              <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor" className="w-3 h-3">
                <path strokeLinecap="round" strokeLinejoin="round" d="m19.5 8.25-7.5 7.5-7.5-7.5" />
              </svg>
            </button>
          </div>
          
          <button
            onClick={handleSend}
            disabled={!inputText.trim() || disabled}
            className={`w-9 h-9 flex items-center justify-center rounded-full transition-colors ${
              inputText.trim() && !disabled
                ? 'bg-brandBlue text-white hover:bg-blue-600 shadow-sm'
                : 'bg-slate-800 text-slate-500 cursor-not-allowed'
            }`}
            aria-label="Gönder"
          >
            <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor" className="w-4 h-4">
              <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 10.5 12 3m0 0 7.5 7.5M12 3v18" />
            </svg>
          </button>
        </div>
      </div>
      
      <p className="mt-3 text-[11px] text-slate-400 font-medium">
        AI ile yapılan analizlerde hata olabilir, kendi kontrollerinizi yapın.
      </p>
    </div>
  );
}
