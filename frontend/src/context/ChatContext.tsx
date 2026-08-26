// src/context/ChatContext.tsx
import { createContext, useContext, ReactNode } from 'react';
import { useChatSessions } from '../hooks/useChatSessions';

/**
 * Sohbet durumunu uygulama geneline dağıtan ince bir provider.
 *
 * Durum makinesinin kendisi `useChatSessions` içinde: kapsama kapısı
 * (`vitest.config.ts`) bilerek `src/hooks/**` ve `src/lib/**`'ı sayıyor,
 * `src/context/**`'i değil. Mantığı hook'ta tutmak, %100 kuralını JSX
 * sayarak değil davranış test ederek karşılamayı sağlıyor.
 */
type ChatContextType = ReturnType<typeof useChatSessions>;

const ChatContext = createContext<ChatContextType | undefined>(undefined);

export function ChatProvider({ children }: { children: ReactNode }) {
  const chat = useChatSessions();
  return <ChatContext.Provider value={chat}>{children}</ChatContext.Provider>;
}

export function useChat(): ChatContextType {
  const context = useContext(ChatContext);
  if (context === undefined) {
    throw new Error('useChat must be used within a ChatProvider');
  }
  return context;
}
