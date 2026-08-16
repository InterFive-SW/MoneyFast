import time
import random

MOCK_INVESTMENT_BALANCE = {
    "totalTRY": 125750.40,
    "totalUSD": 3262.85,
    "breakdown": {
        "cashTRY": 15420.00,
        "stocksBIST": 85120.40,
        "stocksUS": 25210.00,
    }
}

MOCK_POSITIONS = [
    { "symbol": "TEST-THYAO", "price": 295.50, "quantity": 120, "avgCost": 280.00, "totalValue": 35460.00, "dailyReturn": 420.00, "dailyReturnPercent": 1.20, "totalReturn": 1860.00, "totalReturnPercent": 5.53 },
    { "symbol": "TEST-SISE", "price": 54.20, "quantity": 500, "avgCost": 56.10, "totalValue": 27100.00, "dailyReturn": -250.00, "dailyReturnPercent": -0.91, "totalReturn": -950.00, "totalReturnPercent": -3.38 },
    { "symbol": "TEST-TUPRS", "price": 174.50, "quantity": 150, "avgCost": 160.20, "totalValue": 26175.00, "dailyReturn": 315.00, "dailyReturnPercent": 1.21, "totalReturn": 2145.00, "totalReturnPercent": 8.92 },
    { "symbol": "TEST-KCHOL", "price": 212.00, "quantity": 80, "avgCost": 190.50, "totalValue": 16960.00, "dailyReturn": 110.00, "dailyReturnPercent": 0.65, "totalReturn": 1720.00, "totalReturnPercent": 11.28 },
    { "symbol": "TEST-FROTO", "price": 1150.00, "quantity": 25, "avgCost": 1050.00, "totalValue": 28750.00, "dailyReturn": -125.00, "dailyReturnPercent": -0.43, "totalReturn": 2500.00, "totalReturnPercent": 9.52 },
    { "symbol": "TEST-EREGL", "price": 42.80, "quantity": 1000, "avgCost": 45.00, "totalValue": 42800.00, "dailyReturn": -400.00, "dailyReturnPercent": -0.92, "totalReturn": -2200.00, "totalReturnPercent": -4.88 },
    { "symbol": "TEST-AAPL", "price": 215.30, "quantity": 15, "avgCost": 195.00, "totalValue": 113032.50, "dailyReturn": 155.00, "dailyReturnPercent": 0.25, "totalReturn": 304.50, "totalReturnPercent": 10.41 },
    { "symbol": "TEST-MSFT", "price": 435.20, "quantity": 10, "avgCost": 410.00, "totalValue": 152320.00, "dailyReturn": 215.00, "dailyReturnPercent": 0.50, "totalReturn": 252.00, "totalReturnPercent": 6.14 },
    { "symbol": "TEST-NVDA", "price": 128.50, "quantity": 25, "avgCost": 95.00, "totalValue": 112437.50, "dailyReturn": 540.00, "dailyReturnPercent": 1.70, "totalReturn": 837.50, "totalReturnPercent": 35.26 },
]

MOCK_ORDERS = [
    { "id": "ORD-1001", "symbol": "TEST-TUPRS", "status": "Bekliyor", "type": "Alış", "quantity": 50, "price": 172.50, "total": 8625.00, "date": "2026-08-14T10:15:00" },
    { "id": "ORD-1002", "symbol": "TEST-THYAO", "status": "Gerçekleşti", "type": "Satış", "quantity": 20, "price": 298.00, "total": 5960.00, "date": "2026-08-14T09:45:00" },
    { "id": "ORD-1003", "symbol": "TEST-NVDA", "status": "Gerçekleşti", "type": "Alış", "quantity": 10, "price": 115.20, "total": 40320.00, "date": "2026-08-13T16:30:00" },
    { "id": "ORD-1004", "symbol": "TEST-KCHOL", "status": "İptal", "type": "Alış", "quantity": 100, "price": 210.00, "total": 21000.00, "date": "2026-08-13T09:20:00" },
    { "id": "ORD-1005", "symbol": "TEST-SISE", "status": "Gerçekleşti", "type": "Alış", "quantity": 500, "price": 54.10, "total": 27050.00, "date": "2026-08-12T14:15:00" },
    { "id": "ORD-1006", "symbol": "TEST-FROTO", "status": "Gerçekleşti", "type": "Satış", "quantity": 15, "price": 1180.00, "total": 17700.00, "date": "2026-08-12T11:05:00" },
    { "id": "ORD-1007", "symbol": "TEST-EREGL", "status": "İptal", "type": "Satış", "quantity": 200, "price": 46.00, "total": 9200.00, "date": "2026-08-11T15:50:00" },
    { "id": "ORD-1008", "symbol": "TEST-AAPL", "status": "Bekliyor", "type": "Satış", "quantity": 5, "price": 220.00, "total": 38500.00, "date": "2026-08-11T10:30:00" },
]

def generate_data(days: int, start_price: float, volatility: float):
    data = []
    current_price = start_price
    
    now_ms = int(time.time() * 1000)
    start_ms = now_ms - (days * 24 * 60 * 60 * 1000)

    for i in range(days):
        t = int((start_ms + i * 24 * 60 * 60 * 1000) / 1000)
        
        open_p = current_price + (random.random() - 0.5) * volatility
        high_p = open_p + random.random() * volatility
        low_p = open_p - random.random() * volatility
        close_p = low_p + random.random() * (high_p - low_p)
        
        is_up = close_p >= open_p
        volume = int(random.random() * 10000) + 5000

        data.append({
            "time": t,
            "open": open_p,
            "high": high_p,
            "low": low_p,
            "close": close_p,
            "value": volume,
            "color": 'rgba(38, 166, 154, 0.5)' if is_up else 'rgba(239, 83, 80, 0.5)'
        })
        
        current_price = close_p
    return data

MOCK_CHART_DATA = {
    "Gün": generate_data(1, 120000, 500),
    "Hafta": generate_data(7, 120000, 1000),
    "Ay": generate_data(30, 115000, 1500),
    "3 Ay": generate_data(90, 100000, 2000),
    "Yıl": generate_data(365, 80000, 3000),
}

MOCK_ASSET_ALLOCATION = [
    { "assetClass": "Hisse Senedi", "percentage": 42, "amount": 52815.17, "color": "#10b981" },
    { "assetClass": "Döviz (USD/EUR)", "percentage": 28, "amount": 35210.11, "color": "#3b82f6" },
    { "assetClass": "Altın", "percentage": 18, "amount": 22635.07, "color": "#f59e0b" },
    { "assetClass": "Yatırım Fonu", "percentage": 8, "amount": 10060.03, "color": "#8b5cf6" },
    { "assetClass": "Nakit", "percentage": 4, "amount": 5030.02, "color": "#94a3b8" },
]

MOCK_WATCHLIST = {
    "bist": [
        { "symbol": "BIMAS", "price": 412.50, "change": 2.15, "changePercent": 0.52 },
        { "symbol": "AKBNK", "price": 48.20, "change": -1.10, "changePercent": -2.23 },
        { "symbol": "SAHOL", "price": 86.40, "change": 0.85, "changePercent": 0.99 },
        { "symbol": "ASELS", "price": 52.10, "change": 1.25, "changePercent": 2.46 },
    ],
    "us": [
        { "symbol": "TSLA", "price": 185.30, "change": -4.20, "changePercent": -2.21 },
        { "symbol": "GOOGL", "price": 142.15, "change": 1.50, "changePercent": 1.06 },
        { "symbol": "AMZN", "price": 178.40, "change": 3.20, "changePercent": 1.82 },
        { "symbol": "META", "price": 465.20, "change": 8.50, "changePercent": 1.86 },
    ],
    "crypto": [
        { "symbol": "BTC/USD", "price": 64250.00, "change": 1250.00, "changePercent": 1.98 },
        { "symbol": "ETH/USD", "price": 3150.40, "change": -45.60, "changePercent": -1.42 },
        { "symbol": "SOL/USD", "price": 145.20, "change": 5.80, "changePercent": 4.16 },
        { "symbol": "AVAX/USD", "price": 28.50, "change": 1.10, "changePercent": 4.01 },
    ]
}

MOCK_TOP_MOVERS = {
    "gainers": [
        { "symbol": "MIATK", "price": 65.40, "changePercent": 9.95 },
        { "symbol": "ASTOR", "price": 112.50, "changePercent": 8.45 },
        { "symbol": "KONTRO", "price": 245.10, "changePercent": 7.20 },
    ],
    "losers": [
        { "symbol": "GUBRF", "price": 154.20, "changePercent": -8.50 },
        { "symbol": "SASA", "price": 38.40, "changePercent": -5.60 },
        { "symbol": "HEKTS", "price": 14.20, "changePercent": -4.80 },
    ]
}

MOCK_DIVIDENDS = [
    { "symbol": "DOAS", "exDate": "2026-08-25", "paymentDate": "2026-08-28", "amount": 12.50, "yieldPercent": 4.5 },
    { "symbol": "TUPRS", "exDate": "2026-09-10", "paymentDate": "2026-09-12", "amount": 8.40, "yieldPercent": 4.8 },
    { "symbol": "ENJSA", "exDate": "2026-09-15", "paymentDate": "2026-09-17", "amount": 2.80, "yieldPercent": 5.2 },
    { "symbol": "FROTO", "exDate": "2026-10-05", "paymentDate": "2026-10-07", "amount": 25.00, "yieldPercent": 2.1 },
]

MOCK_SECTOR_ALLOCATION = [
    { "sector": "Sanayi & Üretim", "percentage": 35, "color": "#3b82f6" },
    { "sector": "Finans & Bankacılık", "percentage": 25, "color": "#8b5cf6" },
    { "sector": "Teknoloji", "percentage": 20, "color": "#10b981" },
    { "sector": "Enerji", "percentage": 15, "color": "#f59e0b" },
    { "sector": "Diğer", "percentage": 5, "color": "#94a3b8" },
]

MOCK_HEATMAP = [
    { "symbol": "THYAO", "weight": 15, "changePercent": 1.20, "sector": "Ulaştırma" },
    { "symbol": "TUPRS", "weight": 12, "changePercent": 8.92, "sector": "Enerji" },
    { "symbol": "KCHOL", "weight": 10, "changePercent": 0.65, "sector": "Holding" },
    { "symbol": "AKBNK", "weight": 8, "changePercent": -2.23, "sector": "Banka" },
    { "symbol": "ISCTR", "weight": 8, "changePercent": -1.15, "sector": "Banka" },
    { "symbol": "FROTO", "weight": 7, "changePercent": -0.43, "sector": "Otomotiv" },
    { "symbol": "SISE", "weight": 6, "changePercent": -0.91, "sector": "Sanayi" },
    { "symbol": "EREGL", "weight": 5, "changePercent": -0.92, "sector": "Metal" },
    { "symbol": "BIMAS", "weight": 5, "changePercent": 0.52, "sector": "Perakende" },
    { "symbol": "SAHOL", "weight": 4, "changePercent": 0.99, "sector": "Holding" },
    { "symbol": "ASELS", "weight": 4, "changePercent": 2.46, "sector": "Teknoloji" },
    { "symbol": "GARAN", "weight": 4, "changePercent": 1.05, "sector": "Banka" },
    { "symbol": "ENKAI", "weight": 3, "changePercent": -0.50, "sector": "İnşaat" },
    { "symbol": "TOASO", "weight": 3, "changePercent": 1.80, "sector": "Otomotiv" },
    { "symbol": "PGSUS", "weight": 3, "changePercent": 3.40, "sector": "Ulaştırma" },
    { "symbol": "TCELL", "weight": 3, "changePercent": -1.20, "sector": "İletişim" },
]
