import type { paths } from './generated/schema';

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

export type MarketTicker = GetResponseType<paths['/api/market/tickers']>[0];
export type NewsItem = GetResponseType<paths['/api/market/news']>[0];

export type WatchlistItem = GetResponseType<paths['/api/investment/watchlist']>['bist'][0];
export type TopMoverItem = GetResponseType<paths['/api/investment/top-movers']>['gainers'][0];
export type DividendItem = GetResponseType<paths['/api/investment/dividends']>[0];
export type SectorAllocationItem = GetResponseType<paths['/api/investment/sector-allocation']>[0];
export type HeatmapItem = GetResponseType<paths['/api/investment/heatmap']>[0];

// Native fetch API client for backend
class ApiClient {
    private baseUrl = '/api';

    private async request<T>(endpoint: string): Promise<T> {
        const response = await fetch(`${this.baseUrl}${endpoint}`);
        if (!response.ok) {
            throw new Error(`API Error: ${response.status} ${response.statusText}`);
        }
        return await response.json();
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

    // Market endpoints
    getMarketTickers() {
        return this.request<MarketTicker[]>('/market/tickers');
    }

    getMarketNews() {
        return this.request<NewsItem[]>('/market/news');
    }

    // Generic get method for backwards compatibility with UserContext
    async get<T>(url: string): Promise<T> {
        const response = await fetch(url);
        if (!response.ok) {
            throw new Error(`API Error: ${response.status} ${response.statusText}`);
        }
        return await response.json();
    }

    // Generic post method for backwards compatibility with Auth components
    async post<T>(url: string, data?: any): Promise<T> {
        const response = await fetch(url, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: data ? JSON.stringify(data) : undefined,
        });
        if (!response.ok) {
            throw new Error(`API Error: ${response.status} ${response.statusText}`);
        }
        return await response.json();
    }
}

export const apiClient = new ApiClient();
export const api = apiClient;
