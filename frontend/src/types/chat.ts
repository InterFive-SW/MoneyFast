// src/types/chat.ts
export type SenderType = 'user' | 'ai';

export interface ChatMessage {
  id: string;
  text: string;
  sender: SenderType;
  timestamp: Date;
}
