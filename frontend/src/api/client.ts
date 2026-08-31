import type { paths, components } from './generated/schema';
import { clearChatStorage } from '../lib/chatStorage';
import { isTokenExpiringSoon } from '../lib/jwt';

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

// --- Banking: bills, staged payments, saved payees -------------------------

/** Vadesiz, vadeli veya yatırım — tek biçimde. */
export interface HeatmapTile {
    symbol: string
    name?: string | null
    /** Kutunun ALANI bundan geliyor. */
    marketCap: number
    changePercent: number
    sector: string
    price: number
    currency: string
}

export interface MarketHeatmap {
    items: HeatmapTile[]
    /** Piyasa değeri bilinmediği için çizilemeyen enstrüman sayısı. */
    missing: number
}

export interface InstrumentSuggestion {
    symbol: string
    name?: string | null
    market?: string | null
    currency?: string | null
}

export interface PortfolioAccount {
    id: string
    account_number: string
    iban?: string | null
    account_type: string
    currency_code: string
    balance: number
    /** Vadeli hesabın saklanan yıllık oranı ve vadesi; vadesizde null. */
    interest_rate?: number | null
    term_days?: number | null
    is_investment: boolean
}

export interface ApiCard {
    id: string
    name: string
    brand: string
    card_number: string
    limit: number
    current_debt: number
    available_limit: number
    due_day: number
    color?: string | null
    is_digital: boolean
    settings: Record<string, unknown>
    linked_account_id?: string | null
}

export interface ApiLoan {
    id: string
    title: string
    total_amount: number
    remaining_amount: number
    installment_amount: number
    installment_count: number
    paid_installments: number
    remaining_months: number
    next_due?: string | null
    progress_percentage: number
}

export interface BillLookup {
    found: boolean
    id?: string | null
    institution?: string | null
    bill_type?: string | null
    subscriber_no?: string | null
    amount?: number | null
    due_day?: number | null
}

export interface StagePaymentRequest {
    payment_type: 'TRANSFER' | 'BILL_PAYMENT' | 'CARD_PAYMENT'
    amount?: number | null
    destination?: string | null
    institution?: string | null
    subscriber_no?: string | null
    description?: string | null
    idempotency_key?: string | null
}

/** Hazırlanmış ama uygulanmamış bir ödeme. Onaylanana kadar para durur. */
export interface PaymentProposal {
    proposal_id: string
    status: string
    payment_type: string
    amount: number
    currency: string
    destination?: string | null
    description?: string | null
    expires_at: string
    balance_before?: number | null
}

export interface PaymentConfirmation {
    proposal_id: string
    status: string
    reference_number: string
    amount: number
    currency: string
    balance_after?: number | null
}

export interface SavedPayee {
    id: string
    label: string
    institution: string
    subscriber_no: string
}
// `instruments` şemada opsiyonel görünür (varsayılanı olan bir alan); satır
// tipini almak için önce boş olmayan hâline daraltılır.
export type CandleSeries = GetResponseType<paths['/api/market/candles']>;
export type Candle = NonNullable<CandleSeries['candles']>[0];
/**
 * `benchmark` burada elle yazılı: `generated/schema.d.ts` bu alan eklenmeden
 * önce üretilmişti. Yeniden üretimi ayrı ve opsiyonel bir adım
 * (CONTRACT_WORKFLOW.md).
 */
export interface BenchmarkSeries {
    symbol: string;
    points: { date: string; value: number }[];
}

export type PortfolioAnalysis = GetResponseType<paths['/api/analytics/portfolio']> & {
    /** Endeksin, portföyün kendi günlerindeki ham kapanışları. Örtüşen geçmiş
     *  yoksa `null` — kısmi örtüşmeden çizilen bir karşılaştırma çizgisi,
     *  birinin barı olmayan günlerde ayrışma gösterir. */
    benchmark?: BenchmarkSeries | null;
};
export type BankAccount = GetResponseType<paths['/api/banking/accounts']>[0];
export type Statement = GetResponseType<paths['/api/banking/accounts/{account_number}/statement']>;
export type Movement = NonNullable<Statement['movements']>[0];
export type SpendingSummary = GetResponseType<paths['/api/banking/spending']>;
export type BalanceHistory = GetResponseType<paths['/api/banking/balance-history']>;
export type SavingsGoalItem = GetResponseType<paths['/api/banking/savings-goals']>[0];
export type TransferRequest = components['schemas']['TransferRequest'];
export type TransferOut = components['schemas']['TransferOut'];
export type MarketInstrument = NonNullable<
    GetResponseType<paths['/api/market/instruments']>['instruments']
>[0];
export type NewsItem = GetResponseType<paths['/api/market/news']>[0];
/** Kullanıcının ankette beyan ettiği tolerans. Anket doldurulmadan `null`. */
export interface DeclaredRiskProfile {
    tolerance_level: string;
    investment_horizon: string;
    assessed_at: string;
    questionnaire_version: string;
}

/**
 * Ölçüm ile beyanın karşılaştırması.
 *
 * İki taraf da AYNI üç etiketi taşır (Düşük/Orta/Yüksek), iki sayı değil:
 * ölçülen puan ters (100 = sakin), anketin ham puanı değil.
 */
export interface RiskSuitability {
    measured_level: string | null;
    declared_tolerance: string | null;
    alignment: 'ALIGNED' | 'PORTFOLIO_RISKIER' | 'PORTFOLIO_CALMER' | 'UNKNOWN';
    statement: string;
}

/**
 * `declared` ve `suitability` burada elle yazılı: `generated/schema.d.ts` bu
 * alanlar eklenmeden önce üretilmişti. Yeniden üretimi ayrı ve opsiyonel bir
 * adım (CONTRACT_WORKFLOW.md).
 */
export type RiskProfile = GetResponseType<paths['/api/risk/profile']> & {
    declared?: DeclaredRiskProfile | null;
    suitability?: RiskSuitability | null;
    /** Ölçümün kapsadığı aralık: başlangıç/bitiş tarihi ve gözlem sayısı. */
    window?: Record<string, unknown> | null;
    /** Neye göre ölçüldüğü: karşılaştırma ölçütü, Sharpe'ın netleştirildiği
     *  faiz, yeniden dengeleme varsayımı. */
    assumptions?: Record<string, unknown> | null;
};
/** Uç noktanın kabul ettiği kapalı küme; sunucu bunun dışını 422 ile reddeder. */
/**
 * Teknik göstergeler.
 *
 * Her alan null olabilir ve null "geçmiş bu göstergeyi hesaplayacak kadar
 * uzun değil" demek — sıfır DEĞİL. 30 barlık bir enstrümanda 200 günlük
 * ortalama yoktur ve arayüz onu çizmez.
 */
export interface TechnicalSignals {
    observations: number;
    last_close: number | null;
    sma_20: number | null;
    sma_50: number | null;
    sma_200: number | null;
    pct_from_sma_20: number | null;
    pct_from_sma_50: number | null;
    pct_from_sma_200: number | null;
    rsi_14: number | null;
    week52_high: number | null;
    week52_low: number | null;
    week52_position_pct: number | null;
    up_days_recent: number | null;
    recent_window: number | null;
    volume_vs_average: number | null;
    annualised_volatility: number | null;
    max_drawdown_pct: number | null;
    trend: 'UPTREND' | 'DOWNTREND' | 'SIDEWAYS' | 'UNKNOWN';
}

export interface TechnicalSignalsOut {
    symbol: string;
    currency: string;
    signals: TechnicalSignals;
    /** Gösterilecek Türkçe cümle, tam hâliyle. Yeterli geçmiş yoksa null. */
    narrative: string | null;
}

/** Kullanıcının sohbete yüklediği bir belge, listede göründüğü hâliyle. */
export interface ChatDocument {
    id: string;
    filename: string;
    /** PDF / Excel / CSV / PowerPoint / Metin. */
    kind: string;
    size_bytes: number;
    /** PDF'te sayfa, tabloda satır, sunumda slayt. */
    units: number | null;
    char_count: number | null;
    /** Metin tavana takıldıysa doğru. */
    truncated: boolean;
    created_at: string;
}

export interface ChatDocumentList {
    documents: ChatDocument[];
    /** Kabul edilen uzantılar. Dosya seçici bunu okuyor: iki listenin
     *  ayrışması, seçilebilen ama reddedilen bir dosya demek. */
    accepted: string[];
    max_bytes: number;
}

export type RiskLookback = '1M' | '3M' | '6M' | '1Y' | '3Y' | '5Y' | 'MAX';

/** Anket soruları. Puanlar istemciye HİÇ gelmez: seçeneğin ağırlığını
 *  görmek anketi bir teste çevirir ve insanlar teste cevap verir. */
export interface RiskQuestion {
    key: string;
    prompt: string;
    helper: string | null;
    options: { value: string; label: string }[];
}

export interface RiskQuestionnaire {
    version: string;
    questions: RiskQuestion[];
}

/** Simülasyonun bir tarafı. Metriklerin tamamı değil, kıyaslanabilir olanlar. */
export interface RiskSimulationSide {
    score: number | null;
    level: string | null;
    volatility: number | null;
    hhi: number | null;
    effective_n: number | null;
    max_drawdown: number | null;
    position_count: number;
}

export interface RiskSimulationChange {
    symbol: string;
    quantity_delta: number;
    applied: boolean;
    note: string | null;
}

export interface RiskSimulation {
    as_of: string;
    current: RiskSimulationSide;
    hypothetical: RiskSimulationSide;
    /** sonra - önce. Ölçülemeyen tarafta `null` — sıfır "değişmedi" demek. */
    deltas: Record<string, number | null>;
    changes: RiskSimulationChange[];
    warnings: string[];
}

/** Bir günün ölçümü. Her metrik opsiyonel: ölçülemeyen bir gün sıfır
 *  değil, boşluk olarak çizilir. */
export interface RiskSnapshot {
    captured_on: string;
    score: number | null;
    level: string | null;
    volatility: number | null;
    hhi: number | null;
    max_drawdown: number | null;
    position_count: number;
}

export interface RiskHistory {
    /** Her noktanın ölçüldüğü pencere. Noktalar farklı pencerelerden gelseydi
     *  seri anlamsız olurdu. */
    lookback: string;
    days: number;
    points: RiskSnapshot[];
}

export interface RiskAssessmentResult {
    tolerance_level: string;
    investment_horizon: string;
    assessed_at: string;
    questionnaire_version: string;
    raw_score: number;
}
export type RiskFinding = NonNullable<RiskProfile['findings']>[0];
export type RiskSuggestion = NonNullable<RiskProfile['suggestions']>[0];

export type WatchlistItem = GetResponseType<paths['/api/investment/watchlist']>['bist'][0];
export type TopMoverItem = GetResponseType<paths['/api/investment/top-movers']>['gainers'][0];
export type SectorAllocationItem = GetResponseType<paths['/api/investment/sector-allocation']>[0];
export type HeatmapItem = GetResponseType<paths['/api/investment/heatmap']>[0];

/** Sohbet listesi satırı. Kaynak anahtarı `thread_id`, `id` değil. */
export interface ConversationSummary {
    id: string;
    thread_id: string;
    title: string | null;
    created_at: string;
    updated_at: string;
}

export interface ConversationList {
    items: ConversationSummary[];
    total: number;
    limit: number;
    offset: number;
}

export interface ConversationMessage {
    id: string;
    role: 'user' | 'assistant';
    content: string;
    created_at: string;
    disclosures: string[];
}

export interface ConversationDetail extends ConversationSummary {
    messages: ConversationMessage[];
    has_more: boolean;
    context_topic: string | null;
}

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

    /**
     * @param body Gönderilecek gövde. `FormData` ise Content-Type
     *   KURULMAZ: multipart sınırını (`boundary=...`) tarayıcı üretiyor ve
     *   elle yazılan bir başlık onu ezerek gövdeyi sunucu tarafında
     *   ayrıştırılamaz hâle getirir.
     */
    private authHeaders(body?: BodyInit | null): Record<string, string> {
        const token = localStorage.getItem('access_token');
        const headers: Record<string, string> = {};
        if (!(body instanceof FormData)) {
            headers['Content-Type'] = 'application/json';
        }
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
        const send = () =>
            fetch(fullUrl, { ...init, headers: this.authHeaders(init.body) });
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
        // Sohbet deposu da gider. Token'ları silip sohbetleri bırakmak, ortak
        // bir tarayıcıda sıradaki kullanıcıya öncekinin konuşmalarını
        // devretmek demekti.
        clearChatStorage();
        if (typeof window !== 'undefined' && !window.location.pathname.startsWith('/login')) {
            window.location.assign('/login');
        }
    }

    /**
     * Bir tur göndermeden önce oturumu tazele ve sonucu bildir.
     *
     * Sohbet uçları anonim çağrıyı kabul ediyor, dolayısıyla süresi dolmuş
     * bir token 401 DEĞİL, 200-anonim üretiyor — ve `authedFetch`'in yenileme
     * makinesi 401 görmediği için sohbet yolunda hiç çalışmıyordu. Oturumun
     * sessizce düşmesinin sebebi buydu.
     *
     * Başarısızlıkta `/login`'e YÖNLENDİRMEZ: birini cümlenin ortasında
     * oradan almak, yazdığı mesajı kaybettirir. Çağıran anonim olarak devam
     * eder ve kullanıcıya kaydedilmediği söylenir.
     */
    async ensureFreshSession(): Promise<'authenticated' | 'anonymous'> {
        const token = localStorage.getItem('access_token');
        if (!token) return 'anonymous';
        if (!isTokenExpiringSoon(token)) return 'authenticated';
        return (await this.tryRefresh()) ? 'authenticated' : 'anonymous';
    }

    // ----------------------------------------------------------------------
    // Conversations
    //
    // Şemalar burada elle yazılı: `src/api/generated/schema.d.ts` bu uçlar
    // eklenmeden önce üretilmişti. Yeniden üretimi ayrı bir adım
    // (CONTRACT_WORKFLOW.md) ve bu dosyanın çalışmasının önkoşulu değil.
    // ----------------------------------------------------------------------
    getConversations(params: { limit?: number; offset?: number } = {}) {
        const query = new URLSearchParams();
        if (params.limit !== undefined) query.set('limit', String(params.limit));
        if (params.offset !== undefined) query.set('offset', String(params.offset));
        const suffix = query.toString() ? `?${query}` : '';
        return this.request<ConversationList>(`/ai_orchestrator/conversations${suffix}`);
    }

    getConversation(threadId: string, limit?: number) {
        const suffix = limit === undefined ? '' : `?limit=${limit}`;
        return this.request<ConversationDetail>(
            `/ai_orchestrator/conversations/${encodeURIComponent(threadId)}${suffix}`,
        );
    }

    renameConversation(threadId: string, title: string) {
        return this.patch<ConversationSummary>(
            `/ai_orchestrator/conversations/${encodeURIComponent(threadId)}`,
            { title },
        );
    }

    deleteConversation(threadId: string) {
        return this.request<{ thread_id: string; status: string }>(
            `/ai_orchestrator/conversations/${encodeURIComponent(threadId)}`,
            'DELETE',
        );
    }

    private async patch<T>(endpoint: string, data: unknown): Promise<T> {
        const response = await this.authedFetch(`${this.baseUrl}${endpoint}`, {
            method: 'PATCH',
            body: JSON.stringify(data),
        });
        if (!response.ok) {
            throw new Error(`API Hatası: ${response.status} ${response.statusText}`);
        }
        return await response.json();
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

    /**
     * Portföyün mum serisi, TEK aralık.
     *
     * Beş aralığın hepsi tek istekte üretiliyordu: çağrı başına ~130 sorgu ve
     * ölçülen 5,9 saniye. Ekran aynı anda bir aralık gösteriyor.
     */
    getPortfolioChart(range = 'yil') {
        return this.request<PortfolioChartData>(
            `/investment/portfolio/chart?range=${encodeURIComponent(range)}`,
        );
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
    getRiskQuestionnaire() {
        return this.request<RiskQuestionnaire>('/risk/questionnaire');
    }

    submitRiskAssessment(answers: Record<string, string>) {
        return this.post<RiskAssessmentResult>('/api/risk/assessment', { answers });
    }

    simulateRisk(
        changes: { symbol: string; quantity_delta: number }[],
        lookback?: RiskLookback,
    ) {
        return this.post<RiskSimulation>('/api/risk/simulate', {
            changes,
            ...(lookback ? { lookback } : {}),
        });
    }

    /** Bir enstrümanın teknik görünümü. Sohbet ile hisse detay sayfası AYNI
     *  uç noktayı okuyor; ayrı hesaplasalardı aynı hisse için farklı bir
     *  eğilim söyleyebilirlerdi. */
    getTechnicalSignals(symbol: string) {
        return this.request<TechnicalSignalsOut>(
            `/market/technicals?symbol=${encodeURIComponent(symbol)}`,
        );
    }

    // ---- Sohbete yüklenen belgeler --------------------------------------

    /** Bir dosyayı yükler. Metni çıkarılır ve KULLANICIYA AİT olarak gömülür;
     *  yalnızca yükleyenin aramalarında çıkar. */
    async uploadChatDocument(file: File, threadId?: string): Promise<ChatDocument> {
        const form = new FormData();
        form.append('file', file);
        if (threadId) form.append('thread_id', threadId);

        // `authedFetch` gövdeyi olduğu gibi geçiriyor; Content-Type ELLE
        // KURULMUYOR. multipart sınırını tarayıcı üretir ve elle yazılan bir
        // başlık onu ezip gövdeyi ayrıştırılamaz hâle getirir.
        const response = await this.authedFetch(
            `${this.baseUrl}/ai_orchestrator/documents`,
            { method: 'POST', body: form },
        );
        if (!response.ok) throw new Error(await describeError(response));
        return response.json();
    }

    getChatDocuments() {
        return this.request<ChatDocumentList>('/ai_orchestrator/documents');
    }

    /** Belgeyi hem listeden hem aramadan kaldırır. */
    async deleteChatDocument(id: string): Promise<void> {
        const response = await this.authedFetch(
            `${this.baseUrl}/ai_orchestrator/documents/${encodeURIComponent(id)}`,
            { method: 'DELETE' },
        );
        if (!response.ok) throw new Error(await describeError(response));
    }

    getRiskHistory(days?: number) {
        const suffix = days === undefined ? '' : `?days=${days}`;
        return this.request<RiskHistory>(`/risk/history${suffix}`);
    }

    getRiskProfile(lookback?: RiskLookback) {
        // Uç nokta bu parametreyi baştan beri kabul ediyordu; istemci hiç
        // geçmiyordu, dolayısıyla sayfa her zaman bir yıllık pencereyi
        // gösteriyor ve kullanıcı onu değiştiremiyordu.
        const suffix = lookback ? `?lookback=${lookback}` : '';
        return this.request<RiskProfile>(`/risk/profile${suffix}`);
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

    /**
     * Yatırım hesabının nakit hareketleri.
     *
     * Ayrı bir uç, çünkü nakit `banking.accounts` değil
     * `investment.investment_accounts` üzerinde duruyor. Yanıt bankacılık
     * dökümüyle aynı biçimde, böylece arayüz iki listeyi de aynı satır
     * bileşeniyle basabiliyor.
     */
    getInvestmentStatement(identifier: string, limit = 20) {
        return this.request<Statement>(
            `/investment/accounts/${encodeURIComponent(identifier)}/statement?limit=${limit}`,
        );
    }

    /**
     * Sembol ya da şirket adına göre enstrüman önerisi.
     *
     * Evren binin üzerinde enstrüman: bir açılır liste bunu taşıyamaz.
     * Türkçe katlama sunucu tarafında (`market_service._fold`), dolayısıyla
     * `sise` yazan `ŞİŞE`yi buluyor.
     */
    searchInstruments(query: string, limit = 10) {
        return this.request<InstrumentSuggestion[]>(
            `/market/search?q=${encodeURIComponent(query)}&limit=${limit}`,
        );
    }

    /**
     * Piyasa ısı haritası: piyasa değeri ve günlük değişim.
     *
     * `getHeatmap` ile karıştırılmamalı -- o, kullanıcının portföyünü pozisyon
     * ağırlığına göre gösteriyor. Bu, piyasanın kendisini gösteriyor.
     */
    getMarketHeatmap(market?: string, limit = 300) {
        const query = new URLSearchParams({ limit: String(limit) })
        if (market) query.set('market', market)
        return this.request<MarketHeatmap>(`/market/heatmap?${query}`)
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
    /**
     * Portföy analizi.
     *
     * İki ayrı boyut, iki ayrı soydan geldi ve ikisi de gerçek:
     *
     * - `lookback` ÖLÇÜM PENCERESİ (1A, 1Y…). Aynı pencere risk uç noktasına
     *   da gidiyor; Analiz ekranındaki tek dönem seçici ikisini birden
     *   sürüyor. Geçilmezse sunucu 1Y kullanır.
     * - `range='day'` ÇÖZÜNÜRLÜK: gün içi seriyi (5 dakikalık gerçek barlar)
     *   döndürür, varsayılan günlük barlardır.
     *
     * İkisini tek bir parametreye sıkıştırmak, "son bir yıl" ile "bugünü
     * dakika dakika" arasındaki farkı kaybetmek olurdu.
     */
    getPortfolioAnalysis(lookback?: RiskLookback, range?: 'all' | 'day') {
        const query = new URLSearchParams();
        if (lookback) query.set('lookback', lookback);
        if (range) query.set('range', range);
        const suffix = query.toString() ? `?${query}` : '';
        return this.request<PortfolioAnalysis>(`/analytics/portfolio${suffix}`);
    }

    /** Oturumdaki kullanıcının profili; token yoksa istek 401 ile döner. */
    /**
     * Para gönderilebilecek TÜM hesaplar: vadesiz, vadeli ve yatırım.
     *
     * Yatırım hesabının nakiti başka bir tabloda durur; bu uç onu da aynı
     * şekle getirir, `is_investment` ile işaretleyerek. Ekranın nerede
     * durduğunu bilmesi gerekmiyor.
     */
    getAllAccounts() {
        return this.request<PortfolioAccount[]>('/banking/accounts/all')
    }

    /** Kullanıcının kartları. `available_limit` türetilir, saklanmaz. */
    getCards() {
        return this.request<ApiCard[]>('/banking/cards')
    }

    /** Kart ayarları saklananın üzerine yazılır; tek anahtar gönderen bir
     *  ekran diğerlerini sıfırlamaz. */
    updateCardSettings(cardId: string, settings: Record<string, unknown>) {
        return this.patch<ApiCard>(
            `/banking/cards/${encodeURIComponent(cardId)}/settings`, { settings },
        )
    }

    getLoans() {
        return this.request<ApiLoan[]>('/banking/loans')
    }

    /** Abone numarasıyla açık fatura sorgular. Bulunamaması hata değildir. */
    lookupBill(institution: string, subscriberNo: string) {
        const q = new URLSearchParams({ institution, subscriber_no: subscriberNo })
        return this.request<BillLookup>(`/banking/bills/lookup?${q}`)
    }

    /**
     * Ödeme önerisi hazırlar. **Para hareket etmez.**
     *
     * Hisse alım-satımıyla aynı sözleşme: hazırlama ile onay ayrı iki adım.
     * Sohbetin kendi başına para göndermesini engelleyen şey bu ayrım.
     */
    stagePayment(request: StagePaymentRequest) {
        return this.post<PaymentProposal>('/api/banking/payments/stage', request)
    }

    /** Öneriyi uygular. Para yalnızca burada hareket eder. */
    confirmPayment(proposalId: string) {
        return this.post<PaymentConfirmation>(
            `/api/banking/payments/${encodeURIComponent(proposalId)}/confirm`, {},
        )
    }

    getSavedPayees() {
        return this.request<{ payees: SavedPayee[] }>('/banking/saved-payees')
    }

    addSavedPayee(request: { label: string; institution: string; subscriber_no: string }) {
        return this.post<SavedPayee>('/api/banking/saved-payees', request)
    }

    deleteSavedPayee(payeeId: string) {
        return this.request<void>(
            `/banking/saved-payees/${encodeURIComponent(payeeId)}`, 'DELETE',
        )
    }

    getCurrentUser() {
        return this.request<{
            id: string
            first_name: string
            last_name: string
            /** Kimlikten türetilen, kullanıcıya özel müşteri numarası. */
            customer_no?: string | null
        }>('/auth/me');
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
            /**
             * Backend'in `done`'dan sonra eklediği `saved` olayı. Ayrı bir
             * dal gerekiyor çünkü dispatch olay ADINA değil gövdenin ŞEKLİNE
             * bakıyor ve bu gövde ne `stage` ne de `final_output` içeriyor —
             * eklenmeden önce sessizce yere düşüyordu.
             */
            onSaved?: (payload: { conversation_id: string | null; persistence: string }) => void
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
                } else if (payload && 'persistence' in payload) {
                    handlers.onSaved?.(payload)
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

    // Generic put method
    async put<T>(url: string, data?: any): Promise<T> {
        const normalizedUrl = url.startsWith('/api') ? url.substring(4) : url;
        const fullUrl = url.startsWith('http') ? url : `${this.baseUrl}${normalizedUrl}`;
        try {
            const response = await this.authedFetch(fullUrl, {
                method: 'PUT',
                body: data ? JSON.stringify(data) : undefined,
            });
            if (!response.ok) {
                throw new Error(await describeError(response));
            }
            return await response.json();
        } catch (error) {
            console.error(`[API Ağ Hatası] PUT ${fullUrl} isteği başarısız oldu:`, error);
            throw error;
        }
    }

    /**
     * Oturum açmış kullanıcının profil bilgilerini günceller.
     * 
     * @param data - Güncellenecek profil bilgileri
     * @param data.email - Opsiyonel yeni e-posta adresi
     * @param data.phone_number - Opsiyonel yeni telefon numarası
     * @param data.notification_preferences - Backend'de PostgreSQL JSONB kolonunda saklanan, esnek bildirim tercihleri matrisi (Kategori -> Kanal -> Durum).
     * @param data.transaction_limit - Güvenlik Merkezi → İşlem Onay Limiti slider'ından ayarlanan eşik değeri (₺).
     * @param data.user_preferences - Görünüm & Format sekmesinden ayarlanan kullanıcı tercihleri (dil, para birimi, dashboard şablonu).
     */
    async updateProfile(data: {
        email?: string;
        phone_number?: string;
        notification_preferences?: Record<string, Record<string, boolean>>;
        transaction_limit?: number;
        user_preferences?: Record<string, string>;
    }) {
        return this.put<{ id: string; first_name: string; last_name: string }>('/auth/me', data);
    }

    /**
     * Oturum açmış kullanıcının şifresini güvenli bir şekilde değiştirir.
     * Mevcut şifrenin doğrulanmasını gerektirir.
     */
    async changePassword(data: { current_password: string; new_password: string }) {
        return this.post<void>('/auth/change-password', data);
    }

    /**
     * KVKK/GDPR kapsamında kullanıcının tüm kişisel verilerinin dışa
     * aktarılması talebini backend'e iletir. İstek başarılı olduğunda
     * backend bir arka plan görevi başlatır ve dosya hazırlandığında
     * kullanıcının kayıtlı e-posta adresine gönderir.
     */
    async requestDataExport() {
        return this.post<{ message: string }>('/auth/export-data', {});
    }

    /**
     * Kullanıcı hesabını kalıcı olarak kapatır (soft delete).
     *
     * GÜVENLİK & YASAL UYUM:
     * Bu metod backend'de `is_active=False` yaparak hesabı devre dışı bırakır;
     * MASAK ve finansal düzenleme gereklilikleri gereği kullanıcı kaydı
     * veritabanından fiziksel olarak silinmez. Frontend'deki çok adımlı onay
     * modalı (kullanıcının bilinçli olarak "KAPAT" yazması) bu çağrıyı korur.
     *
     * Başarılı dönüşte çağıran taraf localStorage'ı temizleyerek
     * kullanıcıyı /login sayfasına yönlendirmelidir.
     */
    async deleteAccount(data: { reason?: string }) {
        const normalizedUrl = `${this.baseUrl}/auth/me`;
        const response = await this.authedFetch(normalizedUrl, {
            method: 'DELETE',
            body: JSON.stringify(data),
        });
        if (!response.ok) {
            throw new Error(await describeError(response));
        }
        return await response.json();
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
