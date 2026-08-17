// src/context/ChatContext.tsx
import React, { createContext, useContext, useState, ReactNode } from 'react';
import { ChatMessage } from '../types/chat';
import { api } from '../api/client';

interface ChatContextType {
  messages: ChatMessage[];
  isTyping: boolean;
  currentThought?: string;
  activeContext: string | null;
  handleSendMessage: (text: string) => void;
}

const ChatContext = createContext<ChatContextType | undefined>(undefined);

export function ChatProvider({ children }: { children: ReactNode }) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isTyping, setIsTyping] = useState<boolean>(false);
  const [currentThought, setCurrentThought] = useState<string | undefined>();
  const [activeContext, setActiveContext] = useState<string | null>(null);

  const handleSendMessage = async (text: string) => {
    const messageId = (typeof crypto !== 'undefined' && crypto.randomUUID) ? crypto.randomUUID() : Date.now().toString();
    const newUserMessage: ChatMessage = {
      id: messageId,
      text,
      sender: 'user',
      timestamp: new Date()
    };

    setMessages((prev) => [...prev, newUserMessage]);
    setIsTyping(true);

    let step = 0;
    const thoughts = [
      "Kullanıcı talebi analiz ediliyor...",
      "Canlı piyasa verileri çekiliyor...",
      "Risk modeli güncelleniyor...",
      "Yanıt oluşturuluyor..."
    ];

    const thoughtInterval = setInterval(() => {
      if (step < thoughts.length) {
        setCurrentThought(thoughts[step]);
        step++;
      }
    }, 800);

    try {
      // Merkezi api istemcisini kullanarak POST isteği atıyoruz
      // Bu sayede base URL ve hata yönetimi merkezi olarak kontrol edilir
      const data = await api.post<any>('/api/ai_assistant/chat', { text });

      
      clearInterval(thoughtInterval);
      setCurrentThought(undefined);
      setIsTyping(false);

      if (data.context_topic) {
        setActiveContext(data.context_topic);
      }

      const aiResponse: ChatMessage = {
        id: data.id || ((typeof crypto !== 'undefined' && crypto.randomUUID) ? crypto.randomUUID() : Date.now().toString()),
        text: data.text,
        sender: 'ai',
        timestamp: new Date(),
        widget: data.widget
      };

      setMessages((prev) => [...prev, aiResponse]);
    } catch (error) {
      console.error("AI Error:", error);
      clearInterval(thoughtInterval);
      setCurrentThought(undefined);
      setIsTyping(false);
      
      setMessages((prev) => [...prev, {
        id: (typeof crypto !== 'undefined' && crypto.randomUUID) ? crypto.randomUUID() : Date.now().toString(),
        text: "Üzgünüm, şu anda sunucularıma bağlanamıyorum. Lütfen daha sonra tekrar deneyin.",
        sender: 'ai',
        timestamp: new Date()
      }]);
    }
  };

  return (
    <ChatContext.Provider value={{ messages, isTyping, currentThought, activeContext, handleSendMessage }}>
      {children}
    </ChatContext.Provider>
  );
}

export function useChat() {
  const context = useContext(ChatContext);
  if (context === undefined) {
    throw new Error('useChat must be used within a ChatProvider');
  }
  return context;
}
