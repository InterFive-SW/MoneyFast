import type { DashboardTemplate } from '../types/dashboard'

export const DASHBOARD_TEMPLATES: DashboardTemplate[] = [
  {
    id: 'investor-view',
    name: 'Profesyonel Trader',
    description: 'Borsa pozisyonları, emir geçmişi ve portföy grafiklerini içeren profesyonel yatırımcı görünümü.',
    icon: '📈',
    widgets: [
      // Üst satır - Piyasalar
      { id: 'iv-ticker-usd',   type: 'mini-ticker-usd',      x: 0, y: 0, w: 3, h: 1 },
      { id: 'iv-ticker-eur',   type: 'mini-ticker-eur',      x: 3, y: 0, w: 3, h: 1 },
      { id: 'iv-ticker-gold',  type: 'mini-ticker-gold',     x: 6, y: 0, w: 3, h: 1 },
      { id: 'iv-ticker-bist',  type: 'mini-ticker-bist100',  x: 9, y: 0, w: 3, h: 1 },

      // 1. Satır - Portföy Özeti ve Dağılım
      { id: 'iv-balance',      type: 'investment-balance',   x: 0, y: 1, w: 4, h: 2 },
      { id: 'iv-chart',        type: 'portfolio-chart',      x: 4, y: 1, w: 5, h: 2 },
      { id: 'iv-allocation',   type: 'sector-allocation-pie',x: 9, y: 1, w: 3, h: 2 },

      // 2. Satır - Isı Haritası ve İzleme
      { id: 'iv-heatmap',      type: 'heatmap',              x: 0, y: 3, w: 8, h: 3 },
      { id: 'iv-watchlist',    type: 'watchlist',            x: 8, y: 3, w: 4, h: 3 },

      // 3. Satır - Pozisyonlar ve Emirler
      { id: 'iv-positions',    type: 'positions',            x: 0, y: 6, w: 7, h: 4 },
      { id: 'iv-orders',       type: 'order-history',        x: 7, y: 6, w: 5, h: 4 },

      // 4. Satır - Piyasalar ve Gündem
      { id: 'iv-top-movers',   type: 'top-movers',           x: 0, y: 10, w: 4, h: 3 },
      { id: 'iv-news',         type: 'news',                 x: 8, y: 10, w: 4, h: 3 },
    ],
  },
  {
    id: 'comprehensive-view',
    name: 'Kapsamlı Finans',
    description: 'Yatırımlar, banka bakiyeleri ve harcamaların tek ekranda birleştiği karma görünüm.',
    icon: '📊',
    widgets: [
      // Piyasalar
      { id: 'cv-ticker-usd',   type: 'mini-ticker-usd',      x: 0, y: 0, w: 3, h: 1 },
      { id: 'cv-ticker-eur',   type: 'mini-ticker-eur',      x: 3, y: 0, w: 3, h: 1 },
      { id: 'cv-ticker-gold',  type: 'mini-ticker-gold',     x: 6, y: 0, w: 3, h: 1 },
      { id: 'cv-ticker-bist',  type: 'mini-ticker-bist100',  x: 9, y: 0, w: 3, h: 1 },
      
      // Bakiye ve Portföy
      { id: 'cv-total-bal',    type: 'total-balance',        x: 0, y: 1, w: 6, h: 2 },
      { id: 'cv-inv-bal',      type: 'investment-balance',   x: 6, y: 1, w: 6, h: 2 },

      // Harcamalar ve Pozisyonlar
      { id: 'cv-spending',     type: 'spending-overview',    x: 0, y: 3, w: 6, h: 3 },
      { id: 'cv-positions',    type: 'positions',            x: 6, y: 3, w: 6, h: 3 },
      
      // İşlemler ve Hedefler
      { id: 'cv-transactions', type: 'recent-transactions',  x: 0, y: 6, w: 6, h: 4 },
      { id: 'cv-goals',        type: 'savings-goal',         x: 6, y: 6, w: 6, h: 4 },

      // Ek Widgetlar (İzleme Listesi ve Haberler)
      { id: 'cv-watchlist',    type: 'watchlist',            x: 0, y: 10, w: 6, h: 4 },
      { id: 'cv-news',         type: 'news',                 x: 6, y: 10, w: 6, h: 4 },
    ]
  },
  {
    id: 'standard-banking',
    name: 'Günlük Bankacılık',
    description: 'Sadece harcamalar, hedefler ve son işlemler odaklı genel görünüm.',
    icon: '🏦',
    widgets: [
      { id: 'sb-balance',      type: 'total-balance',        x: 0, y: 0, w: 8, h: 2 },
      { id: 'sb-actions',      type: 'quick-actions',        x: 8, y: 0, w: 4, h: 2 },
      
      { id: 'sb-spending',     type: 'spending-overview',    x: 0, y: 2, w: 5, h: 4 },
      { id: 'sb-transactions', type: 'recent-transactions',  x: 5, y: 2, w: 7, h: 4 },
      
      { id: 'sb-goals',        type: 'savings-goal',         x: 0, y: 6, w: 5, h: 4 },
      { id: 'sb-news',         type: 'news',                 x: 5, y: 6, w: 7, h: 4 },
    ],
  },
]

export const DEFAULT_TEMPLATE_ID = 'investor-view'
