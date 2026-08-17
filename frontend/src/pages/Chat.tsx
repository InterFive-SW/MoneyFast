// src/pages/Chat.tsx
import React, { useState, useRef, useEffect } from 'react';
import { ChatMessage } from '../types/chat';
import MessageBubble from '../components/chat/MessageBubble';
import ChatInput from '../components/chat/ChatInput';
import SuggestedPrompts from '../components/chat/SuggestedPrompts';
import TypingIndicator from '../components/chat/TypingIndicator';

/**
 * Chat Sayfası (MoneyFast AI Asistan)
 * 
 * Kullanıcı etkileşimlerini yöneten, premium ve veri odaklı yapay zeka
 * finans asistanının ana sayfa arayüzü.
 */
export default function Chat() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isTyping, setIsTyping] = useState<boolean>(false);
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
  }, [messages, isTyping]);

  const handleSendMessage = (text: string) => {
    // Kullanıcı mesajını oluştur ve listeye ekle
    const newUserMessage: ChatMessage = {
      id: crypto.randomUUID ? crypto.randomUUID() : Date.now().toString(),
      text,
      sender: 'user',
      timestamp: new Date()
    };

    setMessages((prev) => [...prev, newUserMessage]);
    setIsTyping(true);

    // AI yanıt simülasyonu (1.5 saniye bekleme ile)
    setTimeout(() => {
      const aiResponse: ChatMessage = {
        id: crypto.randomUUID ? crypto.randomUUID() : (Date.now() + 1).toString(),
        text: "Portföyünüzün ağırlıklı kısmı Teknoloji sektöründe bulunuyor. BIST 100 endeksindeki son dalgalanmaları göz önüne alarak teknoloji ağırlığını %10 azaltıp, temettü verimi yüksek sanayi hisselerine yönelmenizi tavsiye edebilirim.",
        sender: 'ai',
        timestamp: new Date()
      };
      
      setMessages((prev) => [...prev, aiResponse]);
      setIsTyping(false);
    }, 1500);
  };

  return (
    <div className="flex flex-col h-[calc(100vh-80px)] bg-slate-50 relative overflow-hidden rounded-xl border border-slate-200 shadow-sm">
      
      {/* Scroll Edilebilir Mesaj Alanı */}
      <div ref={scrollContainerRef} className="flex-1 overflow-y-auto px-4 md:px-8 pt-6 pb-24">
        <div className="max-w-4xl mx-auto w-full h-full flex flex-col">
          {messages.length === 0 ? (
            <SuggestedPrompts onSelectPrompt={handleSendMessage} />
          ) : (
            <>
              {messages.map((msg) => (
                <MessageBubble key={msg.id} message={msg} />
              ))}
              {isTyping && <TypingIndicator />}
            </>
          )}
        </div>
      </div>

      {/* Sabit Mesaj Girdi Alanı */}
      <div className="absolute bottom-0 w-full">
        <ChatInput onSendMessage={handleSendMessage} disabled={isTyping} />
      </div>
    </div>
  );
}
