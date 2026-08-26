// src/components/chat/ChatPopup.tsx
import { useRef, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useChat } from '../../context/ChatContext';
import MessageBubble from './MessageBubble';
import ChatInput from './ChatInput';
import PersistenceNotice from './PersistenceNotice';
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
  const { messages, isTyping, currentThought, notice, dismissNotice, handleSendMessage } = useChat();
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const navigate = useNavigate();

  const scrollToBottom = () => {
    // DOM'un render olmasını bekleyip öyle scroll yapmak için setTimeout kullanıyoruz
    setTimeout(() => {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
    }, 150);
  };

  useEffect(() => {
    if (isOpen) {
      scrollToBottom();
    }
  }, [messages, isTyping, currentThought, isOpen]);

  if (!isOpen) return null;

  return (
    <div className="fixed bottom-24 right-4 md:right-8 w-[92vw] md:w-[380px] h-[550px] max-h-[70vh] bg-slate-950/80 backdrop-blur-2xl border border-white/10 shadow-2xl rounded-2xl z-[99999] flex flex-col overflow-hidden transition-all duration-300">
      
      {/* Başlık (Header) */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-white/10 bg-slate-900/80">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-xl bg-brandBlue/20 flex items-center justify-center text-brandBlue font-bold text-xs shrink-0">
            MF
          </div>
          <div>
            <h3 className="text-sm font-semibold text-white leading-tight">Yapay Zeka Asistanı</h3>
            <p className="text-[10px] text-brandBlue font-medium leading-tight mt-0.5">Sizin için hazır</p>
          </div>
        </div>
        
        <div className="flex items-center gap-1">
          {/* Tam Ekrana (Sohbet Sayfasına) Geçiş Butonu */}
          <button 
            onClick={() => {
              onClose();
              navigate('/chat');
            }}
            className="p-1.5 text-slate-400 hover:text-brandBlue hover:bg-brandBlue/10 rounded-lg transition-colors focus:outline-none"
            title="Sohbet Sayfasına Git"
          >
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 8V4m0 0h4M4 4l5 5m11-1V4m0 0h-4m4 0l-5 5M4 16v4m0 0h4m-4 0l5-5m11 5l-5-5m5 5v-4m0 4h-4" />
            </svg>
          </button>
          
          {/* Kapatma Butonu */}
          <button 
            onClick={onClose}
            className="p-1.5 text-slate-400 hover:text-red-500 hover:bg-red-500/10 rounded-lg transition-colors focus:outline-none"
            title="Kapat"
          >
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
      </div>

      {/* Mesaj Listesi */}
      <div ref={scrollContainerRef} className="flex-1 overflow-y-auto px-4 py-4 bg-transparent">
        <div className="flex flex-col min-h-full justify-end">
          {messages.length === 0 ? (
            <div className="text-center text-slate-400 text-sm py-4 my-auto">
              Sohbete başlamak için bir mesaj yazın...
            </div>
          ) : (
            <>
              {messages.map((msg) => (
                <MessageBubble key={msg.id} message={msg} />
              ))}
              {isTyping && <TypingIndicator thought={currentThought} />}
              <div ref={messagesEndRef} className="h-2 w-full" />
            </>
          )}
        </div>
      </div>

      {/* Girdi Alanı */}
      <div className="p-3 bg-slate-900 border-t border-white/10">
        <PersistenceNotice message={notice} onDismiss={dismissNotice} />
        <ChatInput onSendMessage={handleSendMessage} disabled={isTyping} />
      </div>

    </div>
  );
}
