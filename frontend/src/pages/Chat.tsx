// src/pages/Chat.tsx
import { useRef, useEffect } from 'react';
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
 * finans asistanının ana sayfa arayüzü. 
 * Düzen: Sol Sidebar (Geçmiş), Orta (Sohbet), Sağ (Bağlam Paneli).
 */
export default function Chat() {
  const { 
    sessions, activeSessionId, messages, isTyping, currentThought, activeContext, 
    handleSendMessage, createNewSession, loadSession, deleteSession 
  } = useChat();
  
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Scroll işlemini daha kararlı hale getirmek için useLayoutEffect ve ResizeObserver/MutationObserver yerine
  // scrollToBottom'u ufak bir gecikme ile çağırıyoruz. Bu, resim veya widget renderlarını beklemeyi sağlar.
  const scrollToBottom = () => {
    if (messagesEndRef.current) {
      messagesEndRef.current.scrollIntoView({ behavior: 'smooth', block: 'end' });
    }
  };

  useEffect(() => {
    scrollToBottom();
    // Mesajlar eklendikten sonra veya yazıyor animasyonu çıkınca aşağı kaydır
    const timeoutId = setTimeout(scrollToBottom, 150);
    return () => clearTimeout(timeoutId);
  }, [messages, isTyping, currentThought]);

  const hasMessages = messages.length > 0;

  return (
    <div className="flex flex-col md:flex-row h-[calc(100vh-80px)] bg-slate-900/30 relative overflow-hidden rounded-xl border border-white/10 shadow-sm">
      
      {/* Sol Sidebar - Sohbet Geçmişi */}
      <div className="hidden md:flex w-64 border-r border-white/10 bg-slate-900/50 flex-col">
        <div className="p-4 border-b border-white/10">
          <button 
            onClick={createNewSession}
            className="w-full flex items-center justify-center gap-2 bg-brandBlue hover:bg-blue-600 text-white py-2.5 rounded-lg text-sm font-medium transition-colors shadow-sm"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
            </svg>
            Yeni Sohbet
          </button>
        </div>
        
        <div className="flex-1 overflow-y-auto p-3 space-y-1">
          <div className="text-xs font-semibold text-slate-400 mb-2 px-2 uppercase tracking-wider">Geçmiş Sohbetler</div>
          
          {sessions.length === 0 && (
            <div className="text-center text-slate-400 text-xs py-4">
              Henüz sohbet bulunmuyor.
            </div>
          )}

          {sessions.map(session => (
            <div 
              key={session.id} 
              className={`group flex items-center justify-between p-2 rounded-lg cursor-pointer transition-colors ${activeSessionId === session.id ? 'bg-brandBlue/20 text-brandBlue' : 'hover:bg-white/5 text-slate-300'}`}
              onClick={() => loadSession(session.id)}
            >
              <div className="flex items-center gap-2 overflow-hidden">
                <svg className="w-4 h-4 shrink-0 opacity-70" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
                </svg>
                <span className="text-sm truncate font-medium">{session.title}</span>
              </div>
              <button 
                onClick={(e) => { e.stopPropagation(); deleteSession(session.id); }}
                className="opacity-0 group-hover:opacity-100 p-1 text-slate-400 hover:text-red-500 transition-opacity"
                title="Sohbeti Sil"
              >
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                </svg>
              </button>
            </div>
          ))}
        </div>
      </div>

      {/* Ana Sohbet Alanı */}
      <div className={`flex-1 flex flex-col relative h-full w-full ${hasMessages ? 'md:w-auto' : ''}`}>
        
        {/* Scroll Edilebilir Mesaj Alanı veya Boş Durum (Empty State) */}
        <div ref={scrollContainerRef} className="flex-1 overflow-y-auto px-4 md:px-8 pt-6 pb-[140px] scroll-smooth">
          <div className="max-w-3xl mx-auto w-full min-h-full flex flex-col justify-end">
            
            {!hasMessages ? (
              <div className="flex-1 flex flex-col items-center justify-center w-full mt-[-10vh] animate-in fade-in duration-500">
                <div className="flex items-center gap-2 mb-8">
                  <div className="w-8 h-8 rounded-md bg-brandBlue text-white flex items-center justify-center font-bold text-sm shadow-sm">
                    MF
                  </div>
                  <span className="text-xl font-bold tracking-tight text-white">
                    finansal zeka
                  </span>
                </div>
                
                <h1 className="text-2xl md:text-3xl font-semibold text-white mb-4 text-center">
                  Nasıl yardımcı olabilirim?
                </h1>
                
                <p className="text-slate-400 text-center text-sm md:text-base max-w-lg mb-8 leading-relaxed">
                  MoneyFast, finansal verileri analiz eden yapay zeka asistanınız. Bilanço, gelir tablosu, fiyat verileri ve daha fazlasını sorgulayabilirsiniz.
                </p>

                <SuggestedPrompts onSelectPrompt={handleSendMessage} />
              </div>
            ) : (
              <div className="flex flex-col w-full justify-start mt-4 min-h-full">
                {messages.map((msg) => (
                  <MessageBubble key={msg.id} message={msg} />
                ))}
                {isTyping && <TypingIndicator thought={currentThought} />}
                <div ref={messagesEndRef} className="h-4 w-full" />
              </div>
            )}
            
          </div>
        </div>

        {/* Sabit Mesaj Girdi Alanı */}
        <div className="absolute bottom-0 w-full bg-gradient-to-t from-slate-950 via-slate-950/95 to-transparent pt-10 pb-4 px-4 md:px-8">
          <div className="max-w-3xl mx-auto w-full flex flex-col items-center">
            <ChatInput onSendMessage={handleSendMessage} disabled={isTyping} />
          </div>
        </div>
      </div>

      {/* Akıllı Bağlam Paneli (Sadece mesaj varsa ve Desktop'ta görünür) */}
      {hasMessages && activeContext && (
        <div className="hidden lg:block w-80 xl:w-96 h-full border-l border-white/10 bg-slate-900/50">
          <ContextPanel contextTopic={activeContext} />
        </div>
      )}
      
    </div>
  );
}
