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
export type BankAccount = GetResponseType<paths['/api/banking/accounts']>[0];
export type Statement = GetResponseType<paths['/api/banking/accounts/{account_number}/statement']>;
export type Movement = NonNullable<Statement['movements']>[0];
export type SpendingSummary = GetResponseType<paths['/api/banking/spending']>;
export type BalanceHistory = GetResponseType<paths['/api/banking/balance-history']>;

/** Kenar çubuğundaki bir satır. Mesajları taşımaz — bkz. getConversations. */
export interface ConversationSummary {
    thread_id: string;
    title: string | null;
    updated_at: string;
    message_count: number;
}

/** Saklandığı hâliyle bir tur. `meta` yok: yönlendirme/uygunluk kaydı
 *  kullanıcıya ait bir bilgi değil. */
export interface StoredMessage {
    id: string;
    role: string;
    content: string;
    created_at: string;
}
export type SavingsGoalItem = GetResponseType<paths['/api/banking/savings-goals']>[0];
export type TransferRequest = components['schemas']['TransferRequest'];
export type TransferOut = components['schemas']['TransferOut'];
export type MarketInstrument = NonNullable<
    GetResponseType<paths['/api/market/instruments']>['instruments']
>[0];
export type NewsItem = GetResponseType<paths['/api/market/news']>[0];
export type RiskProfile = GetResponseType<paths['/api/risk/profile']>;
export type RiskFinding = NonNullable<RiskProfile['findings']>[0];
export type RiskSuggestion = NonNullable<RiskProfile['suggestions']>[0];

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

    /**
     * Tek uçuş (single-flight) yenileme. Bir sayfa açılışında on kadar istek
     * aynı anda 401 alabilir; her biri ayrı ayrı yenileme denerse yenileme
     * token'ı yarışa girer ve bir kısmı boşa gider.
     */
    private refreshInFlight: Promise<boolean> | null = null;

    private authHeaders(): Record<string, string> {
        const token = localStorage.getItem('access_token');
        const headers: Record<string, string> = {
            'Content-Type': 'application/json',
        };
        if (token) {
            headers['Authorization'] = `Bearer ${token}`;
        }
        return headers;
    }

    private async tryRefresh(): Promise<boolean> {
        if (!this.refreshInFlight) {
            this.refreshInFlight = (async () => {
                const refreshToken = localStorage.getItem('refresh_token');
                if (!refreshToken) return false;
                const response = await fetch(`${this.baseUrl}/auth/refresh`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ refresh_token: refreshToken }),
                });
                if (!response.ok) return false;
                const data = await response.json();
                localStorage.setItem('access_token', data.access_token);
                return true;
            })().finally(() => { this.refreshInFlight = null; });
        }
        return this.refreshInFlight;
    }

    /**
     * Her isteğin geçtiği tek nokta.
     *
     * 401 alındığında bir kez yenilenir ve istek tekrarlanır; yenileme de
     * başarısızsa oturum gerçekten bitmiştir ve kullanıcı girişe gönderilir.
     *
     * Bu katman yoktu: süresi dolmuş bir token sessizce anonim çağırana
     * dönüşüyordu. Kullanıcı çıkış yaptığını fark etmiyordu, çünkü panel
     * uçları token istemiyor; ama sohbet, onaylanması imkânsız işlem
     * önerileri hazırlamaya devam ediyordu.
     */
    private async authedFetch(fullUrl: string, init: RequestInit): Promise<Response> {
        const send = () => fetch(fullUrl, { ...init, headers: this.authHeaders() });
        let response = await send();
        // Giriş ve yenileme uçlarının 401'i normaldir: yanlış şifre ya da
        // ölmüş bir yenileme token'ı. Onları tazelemeye çalışmak döngü olur.
        if (response.status === 401 && !fullUrl.includes('/auth/')) {
            if (await this.tryRefresh()) {
                response = await send();
            } else {
                ApiClient.onSessionExpired();
            }
        }
        return response;
    }

    /** Oturum bittiğinde girişe yönlendirir. Zaten giriş sayfasındaysa değil. */
    static onSessionExpired(): void {
        localStorage.removeItem('access_token');
        localStorage.removeItem('refresh_token');
        if (typeof window !== 'undefined' && !window.location.pathname.startsWith('/login')) {
            window.location.assign('/login');
        }
    }

    private async request<T>(endpoint: string, method: 'GET' | 'DELETE' = 'GET'): Promise<T> {
        try {
            const response = await this.authedFetch(`${this.baseUrl}${endpoint}`, {
                method,
            });
            if (!response.ok) {
                throw new Error(`API Hatası: ${response.status} ${response.statusText}`);
            }
            return await response.json();
        } catch (error) {
            console.error(`[API Ağ Hatası] ${method} ${endpoint} isteği başarısız oldu (Olası CORS veya Sunucu Hatası):`, error);
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

    /** Follow an instrument. Idempotent — starring twice is not an error. */
    addToWatchlist(symbol: string) {
        return this.post<Record<string, string>>(
            `/investment/watchlist/${encodeURIComponent(symbol)}`, {});
    }

    /** Unfollow. */
    removeFromWatchlist(symbol: string) {
        return this.request<Record<string, string>>(
            `/investment/watchlist/${encodeURIComponent(symbol)}`, 'DELETE');
    }

    getWatchlist() {
        return this.request<Record<string, WatchlistItem[]>>('/investment/watchlist');
    }

    getTopMovers() {
        return this.request<Record<string, TopMoverItem[]>>('/investment/top-movers');
    }

    /**
     * Risk sayfasının profili: puan, puanı üreten bileşenler, bulgular ve
     * nakit akışı. Sayfa daha önce sabit bir fixture okuyordu.
     */
    getRiskProfile() {
        return this.request<RiskProfile>('/risk/profile');
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

    /** Mevduat hesapları. */
    getBankAccounts() {
        return this.request<BankAccount[]>('/banking/accounts');
    }

    /** Bir hesabın hareket dökümü. */
    getStatement(accountNumber: string, limit = 20) {
        return this.request<Statement>(
            `/banking/accounts/${encodeURIComponent(accountNumber)}/statement?limit=${limit}`,
        );
    }

    /** Kategorilere göre harcama özeti. */
    getSpending(days = 30) {
        return this.request<SpendingSummary>(`/banking/spending?days=${days}`);
    }

    /** Her hareketten sonraki bakiye — sparkline için. */
    getBalanceHistory(limit = 30) {
        return this.request<BalanceHistory>(`/banking/balance-history?limit=${limit}`);
    }

    /** Birikim hedefleri. */
    getSavingsGoals() {
        return this.request<SavingsGoalItem[]>('/banking/savings-goals');
    }

    /**
     * Para transferi.
     *
     * `destination` hesap numarası ya da IBAN olabilir; backend ikisini de
     * çözer (boşluklu yazılmış IBAN dahil). `source` verilmezse kullanıcının
     * kendi mevduat hesabı kullanılır.
     *
     * Uygulanamayan bir transfer (yetersiz bakiye, kapalı hesap, aynı hesap)
     * 422 döner ve gerekçe Türkçe olarak `detail` alanında gelir; `post`
     * bunu Error.message'a taşıdığı için çağıran doğrudan gösterebilir.
     */
    createTransfer(request: TransferRequest) {
        return this.post<TransferOut>('/banking/transfers', request);
    }

    /** Portföy analizi — dağılım, trend, performans ve işlem geçmişi tek çağrıda. */
    getPortfolioAnalysis() {
        return this.request<PortfolioAnalysis>('/analytics/portfolio');
    }

    /**
     * Kayıtlı sohbetler, en son konuşulan en üstte.
     *
     * Turlar ilk günden beri veritabanına yazılıyordu ama hiçbir uç nokta geri
     * vermiyordu; sohbet geçmişi `localStorage`'dan geliyordu, yani tek bir
     * tarayıcıda yaşıyordu. Seed verisini yükleyen bir ekip arkadaşı satırları
     * alıyor, kenar çubuğunu boş görüyordu.
     */
    getConversations() {
        return this.request<ConversationSummary[]>('/ai_orchestrator/conversations');
    }

    /** Bir sohbetin turları, eskiden yeniye. Liste uç noktası mesaj taşımaz. */
    getConversationMessages(threadId: string) {
        return this.request<StoredMessage[]>(
            `/ai_orchestrator/conversations/${encodeURIComponent(threadId)}/messages`,
        );
    }

    /** Sohbeti kalıcı olarak siler; mesajlar CASCADE ile gider. */
    deleteConversation(threadId: string) {
        return this.request<void>(
            `/ai_orchestrator/conversations/${encodeURIComponent(threadId)}`,
            'DELETE',
        );
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
            const response = await this.authedFetch(fullUrl, { method: 'GET' });
            if (!response.ok) {
                throw new Error(`API Hatası: ${response.status} ${response.statusText}`);
            }
            return await response.json();
        } catch (error) {
            console.error(`[API Ağ Hatası] GET ${fullUrl} isteği başarısız oldu:`, error);
            throw error;
        }
    }

    /**
     * SSE gövdesini okuyan sohbet akışı.
     *
     * `EventSource` kullanılamaz: o yalnızca GET yapar ve başlık gönderemez,
     * sohbet ise POST ve bearer token istiyor. Bu yüzden gövde `fetch` ile
     * parça parça okunuyor.
     *
     * Akış kurulamazsa `false` döner ve çağıran tamponlu `/chat` uç noktasına
     * düşer; sohbetin çalışması akışa bağlı değildir.
     */
    async streamChat(
        body: Record<string, unknown>,
        handlers: {
            onStage?: (label: string) => void
            onDone?: (payload: any) => void
        },
    ): Promise<boolean> {
        let response: Response
        try {
            response = await this.authedFetch(`${this.baseUrl}/ai_orchestrator/chat/stream`, {
                method: 'POST',
                body: JSON.stringify(body),
            })
        } catch {
            return false
        }
        if (!response.ok || !response.body) return false

        const reader = response.body.getReader()
        const decoder = new TextDecoder()
        let buffer = ''
        let sawDone = false

        // SSE olayları boş satırla ayrılır. Bir olay birden fazla ağ
        // parçasına bölünebileceği için tampon, tam olay sınırına kadar
        // bekletilir.
        for (;;) {
            const { done, value } = await reader.read()
            if (done) break
            buffer += decoder.decode(value, { stream: true })
            // `split` always yields at least one element; the last is the
            // partial frame still awaiting its terminator.
            const parts = buffer.split('\n\n')
            buffer = parts[parts.length - 1]
            for (const chunk of parts.slice(0, -1)) {
                const dataLine = chunk.split('\n').find((l) => l.startsWith('data: '))
                if (!dataLine) continue
                let payload: any
                try {
                    payload = JSON.parse(dataLine.slice(6))
                } catch {
                    continue
                }
                if (payload?.error) return sawDone
                if (typeof payload?.stage === 'string') {
                    handlers.onStage?.(payload.stage)
                } else if (payload && 'final_output' in payload) {
                    sawDone = true
                    handlers.onDone?.(payload)
                }
            }
        }
        return sawDone
    }

    // Generic post method for backwards compatibility with Auth components
    async post<T>(url: string, data?: any): Promise<T> {
        // Çift '/api' önekini (prefix) engellemek için url başındaki '/api' kısmını temizleriz.
        const normalizedUrl = url.startsWith('/api') ? url.substring(4) : url;
        const fullUrl = url.startsWith('http') ? url : `${this.baseUrl}${normalizedUrl}`;
        try {
            const response = await this.authedFetch(fullUrl, {
                method: 'POST',
                body: data ? JSON.stringify(data) : undefined,
            });
            if (!response.ok) {
                throw new Error(await describeError(response));
            }
            return await response.json();
        } catch (error) {
            console.error(`[API Ağ Hatası] POST ${fullUrl} isteği başarısız oldu:`, error);
            throw error;
        }
    }
}

/**
 * Bir hata yanıtını kullanıcıya gösterilebilir tek satıra çevirir.
 *
 * Backend reddettiği bir işlemin gerekçesini `detail` alanında Türkçe olarak
 * döndürüyor ("Bakiye yetersiz: transfer ücretle birlikte ... tutuyor").
 * Yalnızca durum kodunu göstermek bu gerekçeyi çöpe atıyor ve kullanıcıya
 * neyi düzeltmesi gerektiğini söylemeyen bir "422" bırakıyordu.
 *
 * FastAPI iki farklı `detail` üretir: HTTPException'da düz metin, gövde
 * doğrulaması başarısız olduğunda ise nesne dizisi. İkisi de ele alınıyor;
 * gövde okunamazsa eski davranışa düşülüyor.
 */
async function describeError(response: Response): Promise<string> {
    const fallback = `API Hatası: ${response.status} ${response.statusText}`;
    try {
        const body = await response.json();
        const detail = body?.detail;
        if (typeof detail === 'string' && detail.trim()) {
            return detail;
        }
        if (Array.isArray(detail)) {
            const messages = detail
                .map((item) => item?.msg)
                .filter((msg): msg is string => typeof msg === 'string' && !!msg.trim());
            if (messages.length) {
                return messages.join(' • ');
            }
        }
        return fallback;
    } catch {
        // Gövde yok ya da JSON değil (ağ katmanından gelen 502 gibi).
        return fallback;
    }
}

export const apiClient = new ApiClient();
export const api = apiClient;
