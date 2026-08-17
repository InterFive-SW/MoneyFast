// src/types/chat.ts
export type SenderType = 'user' | 'ai';

export interface ThoughtStep {
  label: string;
  status: 'pending' | 'active' | 'completed';
}

export interface ChartDataPoint {
  name: string;
  value: number;
}

export interface ChartWidgetPayload {
  title: string;
  data: ChartDataPoint[];
  color?: string;
}

export interface ActionWidgetPayload {
  message: string;
  confirmLabel: string;
  cancelLabel: string;
  actionId: string;
}

export type ChatWidget = 
  | { type: 'chart'; payload: ChartWidgetPayload }
  | { type: 'action'; payload: ActionWidgetPayload };

export interface ChatMessage {
  id: string;
  text: string;
  sender: SenderType;
  timestamp: Date;
  thoughtProcess?: ThoughtStep[];
  widget?: ChatWidget;
}
