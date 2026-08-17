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
export type OrderConfirmRequest = components['schemas']['OrderConfirmRequest'];

export type MarketTicker = GetResponseType<paths['/api/market/tickers']>[0];
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
     * Geliştirme ortamında doğrudan backend'in yayın yaptığı 8000 portuna istek atılır.
     */
    private baseUrl = 'http://localhost:8000/api';

    private async request<T>(endpoint: string): Promise<T> {
        try {
            const response = await fetch(`${this.baseUrl}${endpoint}`);
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
     * Kullanıcının onayladığı işlemi backend'e iletir.
     * 
     * @param request Onaylanacak siparişin detaylarını içeren veri modeli.
     * @returns İşlem sonucu mesajını ve statüsünü döner.
     */
    confirmOrder(request: OrderConfirmRequest) {
        return this.post<Record<string, string>>('/investment/orders/confirm', request);
    }

    // Market endpoints
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
            const response = await fetch(fullUrl);
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
            const response = await fetch(fullUrl, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
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
