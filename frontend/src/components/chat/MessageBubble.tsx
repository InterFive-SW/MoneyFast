// src/components/chat/MessageBubble.tsx
import React from 'react';
import { ChatMessage } from '../../types/chat';

interface MessageBubbleProps {
  message: ChatMessage;
}

/**
 * MessageBubble Bileşeni
 * 
 * Kullanıcı ve yapay zeka mesajlarının arayüzdeki temsilidir.
 * Mesaj tipine göre farklı stiller uygulanır.
 */
export default function MessageBubble({ message }: MessageBubbleProps) {
  const isUser = message.sender === 'user';
  
  // Saati formatla (HH:mm)
  const timeString = message.timestamp.toLocaleTimeString('tr-TR', {
    hour: '2-digit',
    minute: '2-digit'
  });

  return (
    <div className={`flex w-full my-4 ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div className={`flex max-w-[85%] md:max-w-[75%] gap-3 ${isUser ? 'flex-row-reverse' : 'flex-row'}`}>
        
        {/* Yapay Zeka Avatarı */}
        {!isUser && (
          <div className="w-8 h-8 rounded-full bg-emerald-100 flex items-center justify-center text-emerald-600 font-bold text-xs shrink-0 mt-auto mb-1">
            MF
          </div>
        )}

        {/* Mesaj İçeriği */}
        <div 
          className={`flex flex-col px-4 py-3 ${
            isUser 
              ? 'bg-emerald-500 text-white shadow-md rounded-2xl rounded-br-sm' 
              : 'bg-white/80 backdrop-blur-sm border border-slate-200 text-slate-800 shadow-sm rounded-2xl rounded-bl-sm'
          }`}
        >
          <p className="text-[15px] leading-relaxed whitespace-pre-wrap">{message.text}</p>
          
          <span 
            className={`text-[10px] mt-1 ${
              isUser ? 'text-emerald-200 self-end' : 'text-slate-400 self-start'
            }`}
          >
            {timeString}
          </span>
        </div>
      </div>
    </div>
  );
}
