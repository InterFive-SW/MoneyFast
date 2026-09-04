import type { MessageSource } from '../api/client';

export type { MessageSource };

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
  /** The instrument's own currency. `last_price` and `avg_cost` are in
   *  this; the value columns are already converted to base_currency. */
  instrument_currency?: string;
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
  /** Currency the TOTALS are expressed in — the backend converts them. */
  base_currency?: string;
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
  /**
   * Cevabın dayandığı kaynaklar.
   *
   * Bildirimler gibi ayrı taşınıyor ve aynı sebeple: metnin içine
   * karıştırılan bir kaynakça okunmuyor. Ama bildirimlerden farklı olarak
   * bunlar TIKLANABİLİR olmalı, o yüzden düz metin değil bağlantı olarak
   * gösteriliyorlar.
   *
   * Widget'ların aksine geri yükleniyorlar: bir kaynak tarihsel bir olgu --
   * o belge vardı ve bu cevap ona dayanıyordu -- ve yarın da doğru kalıyor.
   */
  sources?: MessageSource[];
}

/**
 * Sohbet Oturumu (Chat Session) Veri Modeli
 */
export interface ChatSession {
  id: string;
  title: string;
  messages: ChatMessage[];
  updatedAt: Date;
  /**
   * Sunucudan gelen bir oturum önce yalnızca başlığıyla listelenir;
   * mesajları ilk açılışında yüklenir. Bu bayrak olmasaydı "mesajı olmayan
   * sohbet" ile "mesajları henüz getirilmemiş sohbet" ayırt edilemezdi.
   */
  messagesLoaded?: boolean;
  /**
   * `server` ise silme/yeniden adlandırma isteklerinin gideceği bir satır
   * var. Henüz hiç mesaj gönderilmemiş yerel bir oturumun karşılığı yoktur
   * ve onu silmeye çalışmak 404 üretir.
   */
  origin?: 'server' | 'local';
}

/**
 * Bir turun geçmişe yazılıp yazılmadığı ve yazılmadıysa sebebi.
 * `anonymous` ile `session_expired` bilerek ayrı: ilki hiç kaybı olmayan
 * bir ziyaretçi, ikincisi kaybı olan biri.
 */
export type PersistenceStatus = 'saved' | 'anonymous' | 'session_expired' | 'failed';
