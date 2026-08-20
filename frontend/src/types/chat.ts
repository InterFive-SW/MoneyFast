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
  /** Kept for backwards compatibility; equals proposalId for chat proposals. */
  actionId: string;
  /** The staged proposal this button confirms. Validated server-side. */
  proposalId?: string;
  /** ISO 8601. A proposal past this instant is refused with 410. */
  expiresAt?: string;
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
  /**
   * Zorunlu yasal bildirimler, kelimesi kelimesine.
   *
   * Mesaj metnine eklenmek yerine ayrı taşınıyor ve balonun altında küçük
   * punto dipnot olarak gösteriliyor. Metin değişmiyor — yalnızca yeri.
   * Her yanıtın sonuna yapıştırılan üç cümlelik kalıp, okuyucuya bildirimi
   * gerçekten gerektiği yerde de atlatıyordu.
   */
  disclosures?: string[];
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
