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
    <div className="sticky bottom-0 w-full backdrop-blur-md bg-slate-50/80 border-t border-slate-200/60 p-4 z-10">
      <div className="max-w-4xl mx-auto relative flex items-end">
        <textarea
          ref={textareaRef}
          value={inputText}
          onChange={(e) => setInputText(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Yapay zeka asistana sorunuzu yazın..."
          disabled={disabled}
          rows={1}
          className="w-full bg-white border border-slate-200 rounded-xl pl-4 pr-14 py-3 focus:outline-none focus:ring-2 focus:ring-emerald-500/50 resize-none overflow-y-auto min-h-[48px] max-h-32 text-slate-800 shadow-sm"
        />
        
        <button
          onClick={handleSend}
          disabled={!inputText.trim() || disabled}
          className={`absolute right-2 bottom-2 w-9 h-9 flex items-center justify-center rounded-lg transition-colors ${
            inputText.trim() && !disabled
              ? 'bg-emerald-500 text-white hover:bg-emerald-600 shadow-sm'
              : 'bg-slate-200 text-slate-400 cursor-not-allowed'
          }`}
          aria-label="Gönder"
        >
          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" className="w-5 h-5 translate-x-[-1px] translate-y-[1px]">
            <path d="M3.478 2.404a.75.75 0 0 0-.926.941l2.432 7.905H13.5a.75.75 0 0 1 0 1.5H4.984l-2.432 7.905a.75.75 0 0 0 .926.94 60.519 60.519 0 0 0 18.445-8.986.75.75 0 0 0 0-1.218A60.517 60.517 0 0 0 3.478 2.404Z" />
          </svg>
        </button>
      </div>
    </div>
  );
}
