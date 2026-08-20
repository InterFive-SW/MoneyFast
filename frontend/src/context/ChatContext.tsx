// src/context/ChatContext.tsx
import { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { ChatMessage, ChatSession } from '../types/chat';
import { api } from '../api/client';

interface ChatContextType {
  sessions: ChatSession[];
  activeSessionId: string | null;
  messages: ChatMessage[];
  isTyping: boolean;
  currentThought?: string;
  activeContext: string | null;
  handleSendMessage: (text: string) => void;
  createNewSession: () => void;
  loadSession: (sessionId: string) => void;
  deleteSession: (sessionId: string) => void;
}

const ChatContext = createContext<ChatContextType | undefined>(undefined);

const STORAGE_KEY = 'moneyfast_chat_sessions';

export function ChatProvider({ children }: { children: ReactNode }) {
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  
  const [isTyping, setIsTyping] = useState<boolean>(false);
  const [currentThought, setCurrentThought] = useState<string | undefined>();
  const [activeContext, setActiveContext] = useState<string | null>(null);

  // Başlangıçta localStorage'dan verileri çek
  useEffect(() => {
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      if (stored) {
        // Tarihleri string'den Date objesine çevir
        const parsedSessions: ChatSession[] = JSON.parse(stored).map((session: any) => ({
          ...session,
          updatedAt: new Date(session.updatedAt),
          messages: session.messages.map((msg: any) => ({
            ...msg,
            timestamp: new Date(msg.timestamp)
          }))
        }));
        setSessions(parsedSessions);
        
        if (parsedSessions.length > 0) {
          // En son güncellenen oturumu aktif yap
          const sorted = [...parsedSessions].sort((a, b) => b.updatedAt.getTime() - a.updatedAt.getTime());
          setActiveSessionId(sorted[0].id);
        }
      }
    } catch (e) {
      console.error("Geçmiş sohbetler yüklenemedi:", e);
    }
  }, []);

  // Sessions her değiştiğinde localStorage'a kaydet
  useEffect(() => {
    if (sessions.length > 0) {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(sessions));
    } else {
      localStorage.removeItem(STORAGE_KEY);
    }
  }, [sessions]);

  // Aktif oturumun mesajlarını hesapla
  const activeSession = sessions.find(s => s.id === activeSessionId);
  const messages = activeSession ? activeSession.messages : [];

  const createNewSession = () => {
    const newSessionId = (typeof crypto !== 'undefined' && crypto.randomUUID) ? crypto.randomUUID() : Date.now().toString();
    const newSession: ChatSession = {
      id: newSessionId,
      title: 'Yeni Sohbet',
      messages: [],
      updatedAt: new Date()
    };
    
    setSessions(prev => [newSession, ...prev]);
    setActiveSessionId(newSessionId);
    setActiveContext(null);
  };

  const loadSession = (sessionId: string) => {
    setActiveSessionId(sessionId);
    setActiveContext(null); // veya oturumdan yüklenebilir
  };

  const deleteSession = (sessionId: string) => {
    setSessions(prev => prev.filter(s => s.id !== sessionId));
    if (activeSessionId === sessionId) {
      setActiveSessionId(null);
      setActiveContext(null);
    }
  };

  const handleSendMessage = async (text: string) => {
    // Eğer hiç aktif oturum yoksa, veya mesaj listesi boşsa yeni oturumun adını güncelle
    let currentSessionId = activeSessionId;
    
    if (!currentSessionId) {
      currentSessionId = (typeof crypto !== 'undefined' && crypto.randomUUID) ? crypto.randomUUID() : Date.now().toString();
      const newSession: ChatSession = {
        id: currentSessionId,
        title: text.substring(0, 30) + (text.length > 30 ? '...' : ''), // İlk mesaja göre başlık
        messages: [],
        updatedAt: new Date()
      };
      setSessions(prev => [newSession, ...prev]);
      setActiveSessionId(currentSessionId);
    }

    // Prior turns, captured before the state update. `sessions` inside this
    // closure is the current render's value, so reading it later would be
    // stale either way; taking it here makes that explicit.
    const priorTurns = (sessions.find((session) => session.id === currentSessionId)?.messages ?? [])
      .slice(-6)
      .map((message) => ({
        role: message.sender === 'user' ? 'user' : 'assistant',
        content: message.text,
      }));

    const messageId = (typeof crypto !== 'undefined' && crypto.randomUUID) ? crypto.randomUUID() : Date.now().toString();
    const newUserMessage: ChatMessage = {
      id: messageId,
      text,
      sender: 'user',
      timestamp: new Date()
    };

    // State'i güncelle (Sadece aktif oturumu bulup mesajı ekle)
    setSessions(prev => prev.map(session => {
      if (session.id === currentSessionId) {
        // Eğer bu ilk mesajsa, başlığı da güncelle
        const title = session.messages.length === 0 ? text.substring(0, 30) + (text.length > 30 ? '...' : '') : session.title;
        return {
          ...session,
          title,
          updatedAt: new Date(),
          messages: [...session.messages, newUserMessage]
        };
      }
      return session;
    }));

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
      // Send the recent turns and the session id. Coreference resolution
      // ("peki ya o?") depends on the history, and without a thread_id every
      // session would map onto one stored conversation.
      //
      // For a signed-in user the backend prefers its OWN stored history over
      // this copy: history decides which instrument a follow-up resolves to,
      // so a client able to rewrite it could steer a tool call.
      const data = await api.post<any>('/api/ai_orchestrator/chat', {
        user_message: text,
        thread_id: currentSessionId,
        conversation_history: priorTurns,
      });
      
      clearInterval(thoughtInterval);
      setCurrentThought(undefined);
      setIsTyping(false);

      if (data.context_topic) {
        setActiveContext(data.context_topic);
      }

      const aiResponse: ChatMessage = {
        id: data.id || ((typeof crypto !== 'undefined' && crypto.randomUUID) ? crypto.randomUUID() : Date.now().toString()),
        text: data.final_output || data.text || "Yanıt alınamadı.",
        sender: 'ai',
        timestamp: new Date(),
        widget: data.widget,
        disclosures: data.disclosures ?? []
      };

      setSessions(prev => prev.map(session => {
        if (session.id === currentSessionId) {
          return {
            ...session,
            updatedAt: new Date(),
            messages: [...session.messages, aiResponse]
          };
        }
        return session;
      }));
      
    } catch (error) {
      console.error("AI Error:", error);
      clearInterval(thoughtInterval);
      setCurrentThought(undefined);
      setIsTyping(false);
      
      const errorResponse: ChatMessage = {
        id: (typeof crypto !== 'undefined' && crypto.randomUUID) ? crypto.randomUUID() : Date.now().toString(),
        text: "Üzgünüm, şu anda sunucularıma bağlanamıyorum. Lütfen daha sonra tekrar deneyin.",
        sender: 'ai',
        timestamp: new Date()
      };

      setSessions(prev => prev.map(session => {
        if (session.id === currentSessionId) {
          return {
            ...session,
            updatedAt: new Date(),
            messages: [...session.messages, errorResponse]
          };
        }
        return session;
      }));
    }
  };

  return (
    <ChatContext.Provider value={{ 
      sessions, activeSessionId, messages, isTyping, currentThought, activeContext, 
      handleSendMessage, createNewSession, loadSession, deleteSession
    }}>
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
