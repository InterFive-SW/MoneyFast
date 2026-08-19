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
  asset: string;
  amount: number;
  action: 'buy' | 'sell';
}

export interface PortfolioPosition {
  symbol: string;
  quantity: number;
  avg_cost: number;
  last_price: number;
  market_value: number;
  unrealized_pnl: number;
  unrealized_pnl_pct: number;
}

export interface PortfolioWidgetPayload {
  total_value: number;
  total_profit_loss: number;
  positions: PortfolioPosition[];
}

export type ChatWidget = 
  | { type: 'chart'; payload: ChartWidgetPayload }
  | { type: 'action'; payload: ActionWidgetPayload }
  | { type: 'portfolio'; payload: PortfolioWidgetPayload };

export interface ChatMessage {
  id: string;
  text: string;
  sender: SenderType;
  timestamp: Date;
  thoughtProcess?: ThoughtStep[];
  widget?: ChatWidget;
}

/**
 * Sohbet Oturumu (Chat Session) Veri Modeli
 */
export interface ChatSession {
  id: string;
  title: string;
  messages: ChatMessage[];
  updatedAt: Date;
}
