import type { paths, components } from './generated/schema';

// Helper type to extract response types
type GetResponseType<T> = T extends {
    get: {
        responses: {
            200: {
                content: {
                    'application/json': infer U;
                };
            };
        };
    };
} ? U : never;

// Export types based on the OpenAPI schema
export type InvestmentBalance = GetResponseType<paths['/api/investment/portfolio/summary']>;
export type PortfolioChartData = GetResponseType<paths['/api/investment/portfolio/chart']>;
export type Position = GetResponseType<paths['/api/investment/positions']>[0];
export type Order = GetResponseType<paths['/api/investment/orders']>[0];
export type AssetAllocationItem = GetResponseType<paths['/api/investment/asset-allocation']>[0];
export type StageTransactionRequest = components['schemas']['StageTransactionRequest'];
export type StageTransactionOut = components['schemas']['StageTransactionOut'];

export type MarketTicker = GetResponseType<paths['/api/market/tickers']>[0];
// `instruments` şemada opsiyonel görünür (varsayılanı olan bir alan); satır
// tipini almak için önce boş olmayan hâline daraltılır.
export type CandleSeries = GetResponseType<paths['/api/market/candles']>;
export type Candle = NonNullable<CandleSeries['candles']>[0];
export type PortfolioAnalysis = GetResponseType<paths['/api/analytics/portfolio']>;
export type MarketInstrument = NonNullable<
    GetResponseType<paths['/api/market/instruments']>['instruments']
>[0];
export type NewsItem = GetResponseType<paths['/api/market/news']>[0];

export type WatchlistItem = GetResponseType<paths['/api/investment/watchlist']>['bist'][0];
export type TopMoverItem = GetResponseType<paths['/api/investment/top-movers']>['gainers'][0];
export type DividendItem = GetResponseType<paths['/api/investment/dividends']>[0];
export type SectorAllocationItem = GetResponseType<paths['/api/investment/sector-allocation']>[0];
export type HeatmapItem = GetResponseType<paths['/api/investment/heatmap']>[0];

// Native fetch API client for backend
class ApiClient {
    /**
     * API İsteklerinin yönlendirileceği Base URL (Backend sunucusu).
     * Göreceli path kullanılır çünkü frontend backend ile aynı origin'den serve ediliyor
     * (CORS'a gerek yok, hangi adresten erişilirse erişilsin otomatik doğru yere gider).
     */
    private baseUrl = '/api';

    private async request<T>(endpoint: string): Promise<T> {
        try {
            const token = localStorage.getItem('access_token');
            const headers: Record<string, string> = {
                'Content-Type': 'application/json',
            };
            if (token) {
                headers['Authorization'] = `Bearer ${token}`;
            }

            const response = await fetch(`${this.baseUrl}${endpoint}`, {
                method: 'GET',
                headers,
            });
            if (!response.ok) {
                throw new Error(`API Hatası: ${response.status} ${response.statusText}`);
            }
            return await response.json();
        } catch (error) {
            console.error(`[API Ağ Hatası] GET ${endpoint} isteği başarısız oldu (Olası CORS veya Sunucu Hatası):`, error);
            throw error;
        }
    }

    // Investment endpoints
    getPortfolioSummary() {
        return this.request<InvestmentBalance>('/investment/portfolio/summary');
    }

    getPortfolioChart() {
        return this.request<PortfolioChartData>('/investment/portfolio/chart');
    }

    getPositions() {
        return this.request<Position[]>('/investment/positions');
    }

    getOrders() {
        return this.request<Order[]>('/investment/orders');
    }

    getAssetAllocation() {
        return this.request<AssetAllocationItem[]>('/investment/asset-allocation');
    }

    getWatchlist() {
        return this.request<Record<string, WatchlistItem[]>>('/investment/watchlist');
    }

    getTopMovers() {
        return this.request<Record<string, TopMoverItem[]>>('/investment/top-movers');
    }

    getDividends() {
        return this.request<DividendItem[]>('/investment/dividends');
    }

    getSectorAllocation() {
        return this.request<SectorAllocationItem[]>('/investment/sector-allocation');
    }

    getHeatmap() {
        return this.request<HeatmapItem[]>('/investment/heatmap');
    }

    /**
     * Bir işlemi öneri olarak hazırlar — hiçbir emir iletmez.
     *
     * Sohbet ve gösterge paneli aynı yolu kullanır: önce burada doğrulanıp
     * maliyetlendirilen bir öneri oluşur, sonra kullanıcı `confirmProposal`
     * ile onaylar. Panelin bir zamanlar kullandığı `/orders/propose` ve
     * `/orders/confirm` uçları sabit bir yanıt döndüren taslaklardı: sahiplik,
     * süre ve tekillik denetimlerinin hiçbirini yapmıyorlardı.
     */
    stageTransaction(request: StageTransactionRequest) {
        return this.post<StageTransactionOut>('/investment/transactions/stage', request);
    }

    /**
     * Hazırlanmış bir işlem önerisini id'siyle onaylar; backend önerinin var
     * olduğunu, süresinin dolmadığını ve çağıran kullanıcıya ait olduğunu
     * doğrular.
     *
     * Onay yalnızca burada, kullanıcının kendi eylemiyle verilir. Ajan bu uç
     * noktaya erişemez ve sohbette "evet" demek onay sayılmaz.
     */
    confirmProposal(proposalId: string) {
        return this.post<Record<string, string>>(
            `/investment/transactions/${encodeURIComponent(proposalId)}/confirm`,
            {},
        );
    }

    // Market endpoints
    /**
     * Enstrüman evreni — fiyat ve temel oranlar birlikte.
     *
     * Parametre adı `limit`; bir süre `top_k` gönderildi ve FastAPI bilinmeyen
     * query parametrelerini sessizce yok saydığı için istek her zaman
     * varsayılan 20 satırla dönüyordu. "Takip edilen 20 enstrüman" yazısının
     * sebebi buydu.
     */
    getInstruments(params?: {
        limit?: number;
        sort_by?: string;
        market?: string;
        sector?: string;
        symbols?: string[];
        max_pe?: number;
        min_pe?: number;
        max_pb?: number;
    }) {
        const query = new URLSearchParams();
        if (params?.limit != null) query.set('limit', String(params.limit));
        if (params?.sort_by) query.set('sort_by', params.sort_by);
        if (params?.market) query.set('market', params.market);
        if (params?.sector) query.set('sector', params.sector);
        if (params?.max_pe != null) query.set('max_pe', String(params.max_pe));
        if (params?.min_pe != null) query.set('min_pe', String(params.min_pe));
        if (params?.max_pb != null) query.set('max_pb', String(params.max_pb));
        // Repeated key, not a comma list: FastAPI reads List[str] that way.
        params?.symbols?.forEach((symbol) => query.append('symbols', symbol));
        const suffix = query.toString() ? `?${query}` : '';
        return this.request<{ instruments: MarketInstrument[] }>(`/market/instruments${suffix}`);
    }

    /** Bir enstrümanın gerçek günlük mum verisi. */
    getCandles(symbol: string, limit = 180) {
        return this.request<CandleSeries>(
            `/market/candles?symbol=${encodeURIComponent(symbol)}&limit=${limit}`,
        );
    }

    /** Portföy analizi — dağılım, trend, performans ve işlem geçmişi tek çağrıda. */
    getPortfolioAnalysis() {
        return this.request<PortfolioAnalysis>('/analytics/portfolio');
    }

    /** Oturumdaki kullanıcının profili; token yoksa istek 401 ile döner. */
    getCurrentUser() {
        return this.request<{ id: string; first_name: string; last_name: string }>('/auth/me');
    }

    getMarketTickers() {
        return this.request<MarketTicker[]>('/market/tickers');
    }

    getMarketNews() {
        return this.request<NewsItem[]>('/market/news');
    }

    // Generic get method for backwards compatibility with UserContext
    async get<T>(url: string): Promise<T> {
        // Çift '/api' önekini (prefix) engellemek için url başındaki '/api' kısmını temizleriz.
        const normalizedUrl = url.startsWith('/api') ? url.substring(4) : url;
        const fullUrl = url.startsWith('http') ? url : `${this.baseUrl}${normalizedUrl}`;
        try {
            const token = localStorage.getItem('access_token');
            const headers: Record<string, string> = {
                'Content-Type': 'application/json',
            };
            if (token) {
                headers['Authorization'] = `Bearer ${token}`;
            }

            const response = await fetch(fullUrl, {
                method: 'GET',
                headers,
            });
            if (!response.ok) {
                throw new Error(`API Hatası: ${response.status} ${response.statusText}`);
            }
            return await response.json();
        } catch (error) {
            console.error(`[API Ağ Hatası] GET ${fullUrl} isteği başarısız oldu:`, error);
            throw error;
        }
    }

    // Generic post method for backwards compatibility with Auth components
    async post<T>(url: string, data?: any): Promise<T> {
        // Çift '/api' önekini (prefix) engellemek için url başındaki '/api' kısmını temizleriz.
        const normalizedUrl = url.startsWith('/api') ? url.substring(4) : url;
        const fullUrl = url.startsWith('http') ? url : `${this.baseUrl}${normalizedUrl}`;
        try {
            const token = localStorage.getItem('access_token');
            const headers: Record<string, string> = {
                'Content-Type': 'application/json',
            };
            if (token) {
                headers['Authorization'] = `Bearer ${token}`;
            }

            const response = await fetch(fullUrl, {
                method: 'POST',
                headers,
                body: data ? JSON.stringify(data) : undefined,
            });
            if (!response.ok) {
                throw new Error(`API Hatası: ${response.status} ${response.statusText}`);
            }
            return await response.json();
        } catch (error) {
            console.error(`[API Ağ Hatası] POST ${fullUrl} isteği başarısız oldu:`, error);
            throw error;
        }
    }
}

export const apiClient = new ApiClient();
export const api = apiClient;
