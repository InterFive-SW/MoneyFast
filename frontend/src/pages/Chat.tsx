// src/pages/Chat.tsx
import React, { useRef, useEffect } from 'react';
import MessageBubble from '../components/chat/MessageBubble';
import ChatInput from '../components/chat/ChatInput';
import SuggestedPrompts from '../components/chat/SuggestedPrompts';
import TypingIndicator from '../components/chat/TypingIndicator';
import ContextPanel from '../components/chat/ContextPanel';
import { useChat } from '../context/ChatContext';

/**
 * Chat Sayfası (MoneyFast AI Asistan)
 * 
 * Kullanıcı etkileşimlerini yöneten, premium ve veri odaklı yapay zeka
 * finans asistanının ana sayfa arayüzü. 2/3 Sohbet, 1/3 Bağlam Paneli düzenindedir.
 */
export default function Chat() {
  const { messages, isTyping, currentThought, activeContext, handleSendMessage } = useChat();
  const scrollContainerRef = useRef<HTMLDivElement>(null);

  // Mesaj eklendiğinde liste sonuna yumuşak geçişli otomatik kaydırma mekanizması
  const scrollToBottom = () => {
    if (scrollContainerRef.current) {
      scrollContainerRef.current.scrollTo({
        top: scrollContainerRef.current.scrollHeight,
        behavior: 'smooth'
      });
    }
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, isTyping, currentThought]);

  const hasMessages = messages.length > 0;

  return (
    <div className="flex flex-col md:flex-row h-[calc(100vh-80px)] bg-white relative overflow-hidden rounded-xl border border-slate-200 shadow-sm">
      
      {/* Ana Sohbet Alanı */}
      <div className={`flex-1 flex flex-col relative h-full w-full ${hasMessages ? 'md:w-2/3' : ''}`}>
        
        {/* Scroll Edilebilir Mesaj Alanı veya Boş Durum (Empty State) */}
        <div ref={scrollContainerRef} className="flex-1 overflow-y-auto px-4 md:px-8 pt-6 pb-[140px]">
          <div className="max-w-3xl mx-auto w-full min-h-full flex flex-col">
            
            {!hasMessages ? (
              <div className="flex-1 flex flex-col items-center justify-center w-full mt-[-10vh] animate-in fade-in duration-500">
                <div className="flex items-center gap-2 mb-8">
                  <div className="w-8 h-8 rounded-md bg-emerald-500 text-white flex items-center justify-center font-bold text-sm shadow-sm">
                    MF
                  </div>
                  <span className="text-xl font-bold tracking-tight text-slate-800">
                    finansal zeka
                  </span>
                </div>
                
                <h1 className="text-2xl md:text-3xl font-semibold text-slate-800 mb-4 text-center">
                  Nasıl yardımcı olabilirim?
                </h1>
                
                <p className="text-slate-500 text-center text-sm md:text-base max-w-lg mb-8 leading-relaxed">
                  MoneyFast, finansal verileri analiz eden yapay zeka asistanınız. Bilanço, gelir tablosu, fiyat verileri ve daha fazlasını sorgulayabilirsiniz.
                </p>

                <SuggestedPrompts onSelectPrompt={handleSendMessage} />
              </div>
            ) : (
              <div className="flex flex-col w-full justify-start mt-4">
                {messages.map((msg) => (
                  <MessageBubble key={msg.id} message={msg} />
                ))}
                {isTyping && <TypingIndicator thought={currentThought} />}
              </div>
            )}
            
          </div>
        </div>

        {/* Sabit Mesaj Girdi Alanı */}
        <div className="absolute bottom-0 w-full bg-gradient-to-t from-white via-white/95 to-transparent pt-10 pb-4 px-4 md:px-8">
          <div className="max-w-3xl mx-auto w-full flex flex-col items-center">
            <ChatInput onSendMessage={handleSendMessage} disabled={isTyping} />
          </div>
        </div>
      </div>

      {/* Akıllı Bağlam Paneli (Sadece mesaj varsa ve Desktop'ta görünür) */}
      {hasMessages && (
        <div className="hidden md:block w-1/3 max-w-[400px] h-full border-l border-slate-100 bg-slate-50/50">
          <ContextPanel contextTopic={activeContext} />
        </div>
      )}
      
    </div>
  );
}
