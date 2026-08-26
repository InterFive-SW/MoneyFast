// src/context/ChatContext.tsx
import { createContext, useContext, useState, useEffect, useCallback, ReactNode } from 'react';
import { ChatMessage, ChatSession } from '../types/chat';
import { api, StoredMessage } from '../api/client';

interface ChatContextType {
  sessions: ChatSession[];
  activeSessionId: string | null;
  messages: ChatMessage[];
  isTyping: boolean;
  currentThought?: string;
  /** Bu oturumda az önce gelen yanıtın id'si. Yalnızca o mesaj yazılıyormuş
   *  gibi gösterilir; "son mesaj" ölçütü kullanılsaydı, kayıtlı bir sohbet
   *  her açılışta baştan canlanırdı. */
  justAnsweredId: string | null;
  activeContext: string | null;
  /** Dismiss the context panel. Exposed so the panel can close itself —
   *  without it there was no way to hide the panel short of reloading. */
  dismissContext: () => void;
  handleSendMessage: (text: string) => void;
  createNewSession: () => void;
  loadSession: (sessionId: string) => void;
  deleteSession: (sessionId: string) => void;
}

const ChatContext = createContext<ChatContextType | undefined>(undefined);

/**
 * Önbellek anahtarının kökü. Kullanıcı kimliği sonuna eklenir.
 *
 * Sabit tek bir anahtardı ve kullanıcıya göre ayrılmıyordu: ortak bir
 * makinede ya da çıkış yapıp başka biriyle girdiğinde, önceki kullanıcının
 * sohbet başlıkları bir sonrakine görünüyordu.
 */
const STORAGE_ROOT = 'moneyfast_chat_sessions';

const storageKeyFor = (userId: string) => `${STORAGE_ROOT}:${userId}`;

/** Sunucudaki bir turu arayüzün mesaj biçimine çevirir.
 *
 *  Geri gelen tur SADECE metindir. Widget'lar (portföy tablosu, al/sat
 *  düğmesi), düşünce adımları ve dipnotlar hiçbir zaman saklanmadı — `meta`
 *  yalnızca yönlendirme ve uygunluk kaydını tutuyor. Canlı turlar bunları
 *  göstermeye devam eder; geçmişten gelenler düz metin olarak döner. */
const toChatMessage = (m: StoredMessage): ChatMessage => ({
    id: m.id,
    text: m.content,
    sender: m.role === 'user' ? 'user' : 'ai',
    timestamp: new Date(m.created_at),
});

export function ChatProvider({ children }: { children: ReactNode }) {
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  
  const [isTyping, setIsTyping] = useState<boolean>(false);
  const [currentThought, setCurrentThought] = useState<string | undefined>();
  const [justAnsweredId, setJustAnsweredId] = useState<string | null>(null);
  const [activeContext, setActiveContext] = useState<string | null>(null);
  /** `${STORAGE_ROOT}:${userId}` — kimlik çözülene kadar null. */
  const [storageKey, setStorageKey] = useState<string | null>(null);
  const dismissContext = useCallback(() => setActiveContext(null), []);

  /**
   * Geçmiş SUNUCUDAN gelir; localStorage yalnızca çevrimdışı yedektir.
   *
   * Eskiden tek kaynak localStorage'dı, yani geçmiş veritabanında değil bir
   * tarayıcıda yaşıyordu: aynı veritabanını yükleyen bir ekip arkadaşı 45
   * sohbetin satırlarını alıyor ve boş bir kenar çubuğu görüyordu. Kendi
   * gizli sekmende de aynısı olurdu.
   *
   * Bu yüzden sunucu kazanır. Önbelleği kaynak kabul etmek, tam olarak o
   * boş listeyi geri getirirdi.
   */
  useEffect(() => {
    let cancelled = false;

    const hydrate = async () => {
      // Token yoksa istek 401 döner; oturum açılmadan denemenin anlamı yok.
      if (!localStorage.getItem('access_token')) return;

      let key: string | null = null;
      try {
        const me = await api.getCurrentUser();
        key = storageKeyFor(me.id);
        if (cancelled) return;
        setStorageKey(key);
      } catch {
        return; // Kimliği çözemeden hiçbir şeyi kimseye ait sayamayız.
      }

      // Önce önbellek: ağ yavaşsa ekran boş kalmasın.
      try {
        const stored = localStorage.getItem(key);
        if (stored && !cancelled) {
          setSessions(JSON.parse(stored).map((session: any) => ({
            ...session,
            updatedAt: new Date(session.updatedAt),
            messages: (session.messages ?? []).map((msg: any) => ({
              ...msg,
              timestamp: new Date(msg.timestamp),
            })),
          })));
        }
      } catch {
        localStorage.removeItem(key);
      }

      try {
        const remote = await api.getConversations();
        if (cancelled) return;

        // Mesajlar burada gelmez; sohbet açıldığında istenir. Kenar çubuğu
        // yalnızca başlık ve tarih gösteriyor, en yoğun kullanıcının ise 45
        // sohbette 292 mesajı var.
        const restored: ChatSession[] = remote.map((c) => ({
          id: c.thread_id,
          title: c.title ?? 'Sohbet',
          messages: [],
          updatedAt: new Date(c.updated_at),
        }));
        setSessions(restored);
        if (restored.length > 0) setActiveSessionId(restored[0].id);
      } catch (e) {
        // Çevrimdışı: yukarıda yüklenen önbellek ekranda kalır.
        console.error('Sohbet geçmişi sunucudan alınamadı:', e);
      }
    };

    void hydrate();
    return () => { cancelled = true; };
  }, []);

  // Sessions her değiştiğinde önbelleğe yaz. Anahtar çözülene kadar yazmayız:
  // kullanıcı belli değilken yazılan bir kopya, ayırmaya çalıştığımız şeyin
  // ta kendisi olurdu.
  useEffect(() => {
    if (!storageKey) return;
    if (sessions.length > 0) {
      localStorage.setItem(storageKey, JSON.stringify(sessions));
    } else {
      localStorage.removeItem(storageKey);
    }
  }, [sessions, storageKey]);

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

  /** Bir sohbetin turlarını, henüz getirilmediyse, sunucudan çeker.
   *
   *  Boş bir `messages` dizisi "bu sohbet boş" değil "henüz açılmadı"
   *  demektir: liste uç noktası mesaj taşımıyor. */
  const ensureMessages = useCallback(async (sessionId: string) => {
    const session = sessions.find(s => s.id === sessionId);
    if (!session || session.messages.length > 0) return;
    try {
      const rows = await api.getConversationMessages(sessionId);
      setSessions(prev => prev.map(s =>
        s.id === sessionId ? { ...s, messages: rows.map(toChatMessage) } : s,
      ));
    } catch (e) {
      // Sunucuda yoksa (yeni, henüz hiç mesaj gönderilmemiş oturum) sorun
      // değil: dizi boş kalır ve ilk mesajla dolar.
      console.error('Sohbet mesajları alınamadı:', e);
    }
  }, [sessions]);

  // Aktif sohbet değiştiğinde turlarını getir. İlk açılışta en son sohbet
  // otomatik seçildiği için bu, onun mesajlarını da yükler.
  useEffect(() => {
    if (activeSessionId) void ensureMessages(activeSessionId);
  }, [activeSessionId, ensureMessages]);

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
    // Sunucuya da gitmeli. Liste artık veritabanından geldiği için, yalnızca
    // yerelde silinen bir sohbet bir sonraki açılışta geri gelirdi.
    void api.deleteConversation(sessionId).catch(() => {
      // Hiç kaydedilmemiş (boş) bir oturumun sunucuda karşılığı yoktur;
      // 404 burada beklenen durumdur.
    });
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
    setCurrentThought(undefined);

    // Bu satırlar eskiden 800ms'de bir dönen sabit bir listeydi ve grafın ne
    // yaptığından bağımsızdı: "Türkiye'nin başkenti neresi" sorusunda bile
    // "Risk modeli güncelleniyor..." yazıyordu. Artık her satır gerçekten
    // girilen bir düğümden geliyor.
    try {
      // Send the recent turns and the session id. Coreference resolution
      // ("peki ya o?") depends on the history, and without a thread_id every
      // session would map onto one stored conversation.
      //
      // For a signed-in user the backend prefers its OWN stored history over
      // this copy: history decides which instrument a follow-up resolves to,
      // so a client able to rewrite it could steer a tool call.
      const requestBody = {
        user_message: text,
        thread_id: currentSessionId,
        conversation_history: priorTurns,
      };

      // Akış önce denenir; kurulamazsa tamponlu uç noktaya düşülür, böylece
      // sohbetin çalışması akışa bağlı kalmaz.
      let data: any = null;
      const streamed = await api.streamChat(requestBody, {
        onStage: (label) => setCurrentThought(label),
        onDone: (payload) => { data = payload; },
      });
      if (!streamed || !data) {
        data = await api.post<any>('/api/ai_orchestrator/chat', requestBody);
      }

      setCurrentThought(undefined);
      setIsTyping(false);

      // Set AND cleared. The old guard only ever set it, so a panel opened by
      // one turn stayed pinned for the rest of the session — showing an
      // instrument nobody had mentioned in ten messages.
      setActiveContext(data.context_topic ?? null);

      const aiResponse: ChatMessage = {
        id: data.id || ((typeof crypto !== 'undefined' && crypto.randomUUID) ? crypto.randomUUID() : Date.now().toString()),
        text: data.final_output || data.text || "Yanıt alınamadı.",
        sender: 'ai',
        timestamp: new Date(),
        widget: data.widget,
        disclosures: data.disclosures ?? []
      };

      setJustAnsweredId(aiResponse.id);
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
      sessions, activeSessionId, messages, isTyping, currentThought, justAnsweredId, activeContext,
      dismissContext, handleSendMessage, createNewSession, loadSession, deleteSession
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
