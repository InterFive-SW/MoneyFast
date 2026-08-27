/**
 * MoneyFast Dashboard — Temel Tip Tanımlamaları
 *
 * Widget sistemi, yerleşim şablonları ve kullanıcı bazlı kişiselleştirme
 * altyapısı için kullanılan tüm TypeScript arayüz ve tür bildirimleri
 * bu dosyada merkezi olarak yönetilmektedir.
 */

// ─── Widget Sistemi ───────────────────────────────────────────────────────────

/**
 * Uygulamada kullanılabilecek tüm widget tiplerinin union tipi.
 * Yeni bir widget bileşeni eklendiğinde buraya da eklenmeli ve
 * Dashboard.tsx içindeki `renderWidgetContent` switch tablosu güncellenmeli.
 */
export type WidgetType =
  // Yatırım (Brokerage) Widget'ları
  | 'investment-balance'
  | 'positions'
  | 'order-history'
  | 'portfolio-chart'
  | 'news'
  | 'mini-ticker-usd'
  | 'mini-ticker-eur'
  | 'mini-ticker-gold'
  | 'mini-ticker-bist100'
  | 'watchlist'
  | 'top-movers'
  | 'dividend-calendar'
  | 'sector-allocation-pie'
  | 'heatmap'
  | 'risk-summary'
  // Bireysel/Banka Widget'ları
  | 'total-balance'
  | 'recent-transactions'
  | 'asset-allocation'
  | 'spending-overview'
  | 'quick-actions'
  | 'savings-goal'

/**
 * 3 sütunlu CSS Grid sistemi içinde tek bir widget'ın
 * konum, boyut ve kimlik bilgisini tanımlayan yapı.
 */
export interface WidgetConfig {
  /** Widget'ın grid içindeki benzersiz kimliği */
  id: string
  /** Hangi widget bileşeninin render edileceğini belirleyen tür */
  type: WidgetType
  /** Grid X koordinatı (0-11 arası) */
  x: number
  /** Grid Y koordinatı */
  y: number
  /** Grid içinde kaç sütun kaplayacağı (1–12 arasında) */
  w: number
  /** Grid içinde kaç satır kaplayacağı (grid unit üzerinden) */
  h: number
}

// ─── Şablon Sistemi ───────────────────────────────────────────────────────────

/**
 * Kullanıcının seçebileceği önceden tanımlanmış bir yerleşim şablonu.
 * Her şablon, widget konfigürasyonlarının sıralı bir listesini içerir;
 * bu liste Dashboard grid bileşeni tarafından doğrudan işlenir.
 */
export interface DashboardTemplate {
  /** localStorage ve URL parametresi için benzersiz şablon kimliği */
  id: string
  /** Şablon seçici dropdown'ında görüntülenecek kullanıcı dostu ad */
  name: string
  /** Şablonun odak alanını özetleyen kısa açıklama metni */
  description: string
  /** Şablonu görsel olarak temsil eden Unicode sembol */
  icon: string
  /** Bu şablonda sırayla render edilecek widget konfigürasyon dizisi */
  widgets: WidgetConfig[]
}

// ─── Kullanıcı Yerleşim Durumu ────────────────────────────────────────────────

/**
 * Kullanıcıya ait dashboard konfigürasyon durumu.
 * Mevcut aşamada localStorage'da JSON formatında saklanmakta olup
 * ilerleyen geliştirme döngülerinde backend profil API'sine taşınabilir.
 */
export interface DashboardLayoutState {
  /** Şu anda aktif olan şablonun kimlik değeri */
  activeTemplateId: string
  /**
   * Kullanıcının özel widget yerleşimi — Custom Mode için ayrılmış alan.
   * Şu an kullanılmamakta; ilerideki kişiselleştirme özelliği için
   * mimariye dahil edilmiştir.
   */
  customWidgets?: WidgetConfig[]
  /** Son değişikliğin ISO 8601 formatındaki zaman damgası */
  lastModified?: string
}

// ─── react-grid-layout Entegrasyonu ──────────────────────────────────────────

/**
 * `react-grid-layout` kütüphanesinin Layout tipini genişleten arayüz.
 * Her widget'ın grid içindeki piksel tabanlı konum ve boyut bilgisini tutar.
 * Bu yapı şablon widget konfigürasyonlarından (`WidgetConfig`) türetilir.
 */
export interface GridLayoutItem {
  /** Widget kimliği — `WidgetConfig.id` ile birebir eşleşmeli */
  i: string
  /** Widget'ın bileşen türü (opsiyonel) */
  type?: WidgetType
  /** Yatay başlangıç pozisyonu (0-tabanlı sütun indeksi) */
  x: number
  /** Dikey başlangıç pozisyonu (0-tabanlı satır indeksi) */
  y: number
  /** Kaç sütun kaplandığı (1–3 arasında) */
  w: number
  /** Kaç satır kaplandığı (varsayılan: 1) */
  h: number
  /** Kullanıcı tarafından sürüklemeye kapalıysa true */
  isDraggable?: boolean
  /** Kullanıcı tarafından yeniden boyutlandırmaya kapalıysa true */
  isResizable?: boolean
}

/**
 * Kullanıcının kaydettiği özel grid düzeni.
 * `localStorage`'da `moneyfast_custom_layout` anahtarıyla saklanır.
 */
export interface CustomLayoutState {
  /** Düzenin benzersiz ID'si (ör. 'custom-123') */
  id: string
  /** Kullanıcının bu düzene verdiği isim */
  name: string
  /** Hangi şablon temel alınarak oluşturulduğu (isteğe bağlı) */
  baseTemplateId?: string
  /** Kullanıcının düzenlediği grid öğe dizisi */
  items: GridLayoutItem[]
  /** Kaydedildiği ISO 8601 zaman damgası */
  savedAt: string
}
