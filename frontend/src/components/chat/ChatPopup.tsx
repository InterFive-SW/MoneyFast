// src/components/chat/ChatPopup.tsx
import React, { useRef, useEffect } from 'react';
import { useChat } from '../../context/ChatContext';
import MessageBubble from './MessageBubble';
import ChatInput from './ChatInput';
import TypingIndicator from './TypingIndicator';

interface ChatPopupProps {
  isOpen: boolean;
  onClose: () => void;
}

/**
 * ChatPopup Bileşeni
 * 
 * Ana ekran dışındaki sayfalarda asistan ikonuna tıklanınca açılan,
 * glassmorphism tasarımlı mini sohbet penceresi.
 * Global `useChat` context'ini kullanarak sohbet geçmişini ana sayfayla senkron tutar.
 */
export default function ChatPopup({ isOpen, onClose }: ChatPopupProps) {
  const { messages, isTyping, currentThought, handleSendMessage } = useChat();
  const scrollContainerRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    // DOM'un render olmasını bekleyip öyle scroll yapmak için setTimeout kullanıyoruz
    setTimeout(() => {
      if (scrollContainerRef.current) {
        scrollContainerRef.current.scrollTo({
          top: scrollContainerRef.current.scrollHeight,
          behavior: 'smooth'
        });
      }
    }, 50);
  };

  useEffect(() => {
    if (isOpen) {
      scrollToBottom();
    }
  }, [messages, isTyping, currentThought, isOpen]);

  if (!isOpen) return null;

  return (
    <div className="fixed bottom-24 right-4 md:right-8 w-[92vw] md:w-[380px] h-[550px] max-h-[70vh] bg-white/95 backdrop-blur-2xl border border-slate-200/80 shadow-2xl rounded-2xl z-[99999] flex flex-col overflow-hidden transition-all duration-300">
      
      {/* Başlık (Header) */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-slate-100 bg-white/80">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-xl bg-emerald-100 flex items-center justify-center text-emerald-600 font-bold text-xs shrink-0">
            MF
          </div>
          <div>
            <h3 className="text-sm font-semibold text-slate-800 leading-tight">Yapay Zeka Asistanı</h3>
            <p className="text-[10px] text-emerald-600 font-medium leading-tight mt-0.5">Sizin için hazır</p>
          </div>
        </div>
        <button 
          onClick={onClose}
          className="p-1.5 text-slate-400 hover:text-slate-600 hover:bg-slate-100 rounded-lg transition-colors focus:outline-none"
        >
          <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

      {/* Mesaj Listesi */}
      <div ref={scrollContainerRef} className="flex-1 overflow-y-auto px-4 py-4 bg-slate-50/50">
        <div className="flex flex-col">
          {messages.map((msg) => (
            <MessageBubble key={msg.id} message={msg} />
          ))}
          {isTyping && <TypingIndicator thought={currentThought} />}
        </div>
      </div>

      {/* Girdi Alanı */}
      <div className="p-3 bg-white border-t border-slate-100">
        <ChatInput onSendMessage={handleSendMessage} disabled={isTyping} />
      </div>

    </div>
  );
}
