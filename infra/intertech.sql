-- Senin yapay zeka işlemlerin için gereken vektör eklentisi
CREATE EXTENSION IF NOT EXISTS vector;

-- Şemaların Oluşturulması
-- Deployment açısından database'leri ayırmak yerine şemalara böldüm.
CREATE SCHEMA auth;
CREATE SCHEMA banking;
CREATE SCHEMA investment;
CREATE SCHEMA notification;
CREATE SCHEMA analytics;
CREATE SCHEMA ai;


-- AUTH --
CREATE TABLE auth.users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_number TEXT UNIQUE NOT NULL,
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    national_id TEXT UNIQUE NOT NULL,
    phone TEXT UNIQUE NOT NULL,
    email TEXT UNIQUE NOT NULL,
    status TEXT DEFAULT 'active',
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE auth.user_profiles (
    -- Hem Primary Key (PK) hem de users tablosuna bağlı Foreign Key (FK)
    user_id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    
    occupation TEXT,
    monthly_income NUMERIC(15, 2),            
    annual_transaction_volume NUMERIC(15, 2),
    annual_expense_volume NUMERIC(15, 2),
    residence_type TEXT,
    profile_answerS JSONB NULL,
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);

CREATE TABLE auth.otp_verifications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    purpose TEXT NOT NULL,             -- Örn: 'login', 'password_reset', 'transaction_approval'
    channel TEXT NOT NULL,             -- Örn: 'sms', 'email'
    code_hash TEXT NOT NULL,           -- Güvenlik için OTP'nin hash'lenmiş hali
    expires_at TIMESTAMPTZ NOT NULL,   -- OTP'nin son geçerlilik süresi
    verified_at TIMESTAMPTZ,           -- Doğrulama başarılı olursa o anın zaman damgası (boş olabilir)
    attempt_count INTEGER DEFAULT 0,   -- Yanlış girme denemelerini saymak için
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE auth.risk_profiles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    risk_level TEXT NOT NULL,          -- Örn: 'Düşük', 'Orta', 'Yüksek'
    score INTEGER NOT NULL,            -- Risk anketinden alınan genel puan
    investment_horizon TEXT,           -- Örn: 'Kısa Vadeli', 'Uzun Vadeli'
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE auth.risk_assessments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    questionnaire_version TEXT,        -- Örn: 'v1.0' (Zamanla anket soruları değişirse takip edebilmek için)
    score INTEGER NOT NULL,            -- Bu spesifik anketten alınan puan
    result TEXT NOT NULL,              -- Örn: 'Agresif Yatırımcı'
    completed_at TIMESTAMPTZ DEFAULT now()
);


-- BANKING --
CREATE TABLE banking.banks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(100) NOT NULL,
    code VARCHAR(20) UNIQUE NOT NULL,       -- EFT/Banka Kodu
    swift_code VARCHAR(20),                 -- Uluslararası transferler için (boş olabilir)
    status VARCHAR(20) DEFAULT 'active',
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE banking.branches (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    bank_id UUID NOT NULL REFERENCES banking.banks(id) ON DELETE CASCADE,
    branch_code VARCHAR(20) NOT NULL,       -- Şube Kodu
    name VARCHAR(100) NOT NULL,
    city VARCHAR(100) NOT NULL,
    district VARCHAR(100),
    address TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE banking.accounts ( --source of truth değil asıl source of truth olan transactions
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    bank_id UUID REFERENCES banking.banks(id),
    branch_id UUID REFERENCES banking.branches(id),                  
    customer_number TEXT NOT NULL,
    account_number TEXT NOT NULL,
    iban TEXT UNIQUE,                 -- IBAN her zaman eşsiz (unique) olmalıdır
    account_type TEXT NOT NULL,       -- Örn: 'vadesiz', 'vadeli', 'birikim'
    currency_code VARCHAR(3) DEFAULT 'TRY', -- Örn: TRY, USD, EUR
    balance NUMERIC(19,4),
    available_balance NUMERIC(19,4),
    status TEXT DEFAULT 'active',
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE banking.transactions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    reference_number TEXT UNIQUE NOT NULL,  -- Dekont / Referans numarası eşsiz olmalıdır
    transaction_type TEXT NOT NULL,         -- Örn: 'havale', 'eft', 'fatura_odeme'
    status TEXT DEFAULT 'pending',          -- Örn: 'pending', 'completed', 'failed'
    amount NUMERIC(15, 2) NOT NULL,         -- İşlem tutarı
    currency_code VARCHAR(3) DEFAULT 'TRY',
    description TEXT,                       -- İşlem açıklaması
    created_at TIMESTAMPTZ DEFAULT now(),
    completed_at TIMESTAMPTZ,                -- İşlem onaylandığında doldurulacak zaman damgası
    failed_at TIMESTAMPTZ
);

CREATE TABLE banking.account_transactions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    -- Ana işlem kaydına ve ilgili hesaba bağlanan Foreign Key'ler
    transaction_id UUID NOT NULL REFERENCES banking.transactions(id) ON DELETE CASCADE,
    account_id UUID NOT NULL REFERENCES banking.accounts(id) ON DELETE CASCADE,

    direction VARCHAR(10) NOT NULL,           -- Örn: 'DEBIT' (Çıkış) veya 'CREDIT' (Giriş)
    amount NUMERIC(15, 2) NOT NULL,           -- İşlem gören tutar
    balance_before NUMERIC(15, 2),
    balance_after NUMERIC(15, 2),
    -- Alıcı veya Gönderici bilgileri
    counterparty_name VARCHAR(255),
    counterparty_iban VARCHAR(50),
    counterparty_bank VARCHAR(100),
    description TEXT,                         
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE banking.transfers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    transaction_id UUID UNIQUE NOT NULL REFERENCES banking.transactions(id) ON DELETE CASCADE, -- Ana işleme bağlanan fk
    source_account_id UUID NOT NULL REFERENCES banking.accounts(id) ON DELETE CASCADE,  -- Paranın çıktığı hesap
    destination_account_id UUID REFERENCES banking.accounts(id) ON DELETE SET NULL,  -- Paranın ulaştığı hesap
    
    -- Hedef hesap sistem dışındaysa doldurulacak alanlar
    destination_iban TEXT,
    destination_name TEXT,
    destination_bank TEXT,
    
    transfer_type TEXT NOT NULL,         -- Örn: 'havale', 'eft', 'swift'
    status TEXT DEFAULT 'pending',       -- Örn: 'pending', 'processing', 'completed', 'failed'
    scheduled_at TIMESTAMPTZ,            -- İleri tarihli transferler için planlanan zaman
    completed_at TIMESTAMPTZ,            -- İşlemin başarıyla bittiği an
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE banking.savings_goals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    -- Hedefin kime ve hangi hesaba bağlı olduğu
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    account_id UUID REFERENCES banking.accounts(id) ON DELETE CASCADE,
    
    name TEXT NOT NULL,                  -- Örn: 'Yaz Tatili', 'Araba Peşinatı'
    purpose TEXT,                        -- Hedefin daha detaylı açıklaması
    target_amount NUMERIC(19, 4) NOT NULL,
    current_amount NUMERIC(19, 4) DEFAULT 0,
    currency_code VARCHAR(3) DEFAULT 'TRY',
    target_date DATE,                    -- Hedefe ulaşılması planlanan tarih
    status TEXT DEFAULT 'active',        -- Örn: 'active', 'completed', 'cancelled'
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    completed_at TIMESTAMPTZ             -- Hedefe ulaşıldığı anın zaman damgası
);

CREATE TABLE banking.savings_deposits (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    goal_id UUID NOT NULL REFERENCES banking.savings_goals(id) ON DELETE CASCADE, -- Hangi hedefe para yatırıldığını gösteren bağlantı
    transaction_id UUID REFERENCES banking.transactions(id) ON DELETE SET NULL, -- Eğer bu yatırma işlemi bir hesap hareketine bağlıysa doldurulur
    amount NUMERIC(19, 4) NOT NULL,
    currency_code VARCHAR(3) DEFAULT 'TRY',
    deposit_type TEXT NOT NULL,          -- Örn: 'auto_transfer', 'manual_deposit'
    description TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE banking.cash_advances (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    account_id UUID NOT NULL REFERENCES banking.accounts(id) ON DELETE CASCADE,
    transaction_id UUID REFERENCES banking.transactions(id) ON DELETE SET NULL,    -- Eğer avans onaylanıp hesaba yatırıldıysa, o para transferi işleminin ID'si
    
    -- Finansal Tutarlar
    requested_amount NUMERIC(19, 4) NOT NULL,
    approved_amount NUMERIC(19, 4),
    currency_code VARCHAR(3) DEFAULT 'TRY',
    
    -- Faiz, Ücret ve Geri Ödeme
    interest_rate NUMERIC(8, 4),             -- Örn: %3.50 için 3.5000
    fee_amount NUMERIC(19, 4) DEFAULT 0,     -- İşlem/Tahsis ücreti
    total_repayment NUMERIC(19, 4),          -- Toplam geri ödenecek tutar (Anapara + Faiz + Ücret)
    
    status TEXT DEFAULT 'pending',           -- Örn: 'pending', 'approved', 'rejected', 'paid'
    requested_at TIMESTAMPTZ DEFAULT now(),
    approved_at TIMESTAMPTZ,                 -- Onaylandığı an
    due_date DATE,                           -- Son ödeme tarihi
    paid_at TIMESTAMPTZ,                     -- Tamamen geri ödendiği an
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE banking.findeks_applications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE, -- Başvuruyu yapan kullanıcı
    application_number TEXT UNIQUE NOT NULL, 
    status TEXT DEFAULT 'pending',        
    requested_at TIMESTAMPTZ DEFAULT now(),
    completed_at TIMESTAMPTZ,                -- Findeks'ten yanıt gelip sürecin bittiği an
    
    -- Findeks API'den dönen veriler
    report_reference TEXT,                   -- Findeks tarafındaki rapor ID'si
    score INTEGER,                           -- Kredi risk notu (Örn: 1500)
    report_url TEXT,                         -- Raporun PDF/HTML linki

    error_message TEXT,                      -- Başvuru başarısız olursa API'den dönen hata mesajı
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);



-- INVESMENT --
CREATE TABLE investment.investment_products (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    symbol VARCHAR(20) UNIQUE NOT NULL,      -- Örn: 'THYAO', 'AAPL'
    name VARCHAR(255) NOT NULL,              -- Örn: 'Türk Hava Yolları A.O.'
    product_type VARCHAR(50) NOT NULL,       -- Örn: 'stock', 'fund', 'bond'
    market VARCHAR(50),                      -- Örn: 'BIST', 'NASDAQ'
    currency_code VARCHAR(3) DEFAULT 'TRY',
    description TEXT,
    risk_level VARCHAR(20),                  -- Örn: 'Düşük', 'Orta', 'Yüksek' (veya 1-7 arası derece)
    week52_low NUMERIC(19, 4),               -- 52 haftanın en düşüğü
    week52_high NUMERIC(19, 4),              -- 52 haftanın en yükseği
    status VARCHAR(20) DEFAULT 'active',
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- CREATE TABLE investment.investment_prices (
--     id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
--     product_id UUID NOT NULL REFERENCES investment.investment_products(id) ON DELETE CASCADE,
--     timestamp TIMESTAMPTZ NOT NULL,          -- Fiyatın geçerli olduğu an/gün
--     buy_price NUMERIC(19, 4),                -- Anlık alış fiyatı
--     open_price NUMERIC(19, 4),               -- Gün açılış fiyatı
--     close_price NUMERIC(19, 4),              -- Gün kapanış fiyatı
--     low_price NUMERIC(19, 4),                -- Günün en düşüğü
--     high_price NUMERIC(19, 4),               -- Günün en yükseği
--     week52_low NUMERIC(19, 4),               -- 52 haftanın en düşüğü
--     week52_high NUMERIC(19, 4),              -- 52 haftanın en yükseği
--     volume BIGINT,                           -- İşlem Hacmi (Çok yüksek olabileceği için BIGINT)
--     market_value NUMERIC(24, 4),             -- Piyasa Değeri (Trilyonları aşabileceği için 24 basamak)
--     created_at TIMESTAMPTZ DEFAULT now()
-- );

--anlık fiyat için
CREATE TABLE investment.market_quotes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    product_id UUID NOT NULL
        REFERENCES investment.investment_products(id)
        ON DELETE CASCADE,

    price NUMERIC(19,4) NOT NULL,
    change_amount NUMERIC(19,4),
    change_percent NUMERIC(10,4),

    bid_price NUMERIC(19,4),
    ask_price NUMERIC(19,4),

    volume BIGINT,

    market_timestamp TIMESTAMPTZ NOT NULL,
    received_at TIMESTAMPTZ DEFAULT now(),

    source VARCHAR(50) NOT NULL
);

--grafik için
CREATE TABLE investment.market_candles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    product_id UUID NOT NULL
        REFERENCES investment.investment_products(id)
        ON DELETE CASCADE,

    interval VARCHAR(10) NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,

    open_price NUMERIC(19,4) NOT NULL,
    high_price NUMERIC(19,4) NOT NULL,
    low_price NUMERIC(19,4) NOT NULL,
    close_price NUMERIC(19,4) NOT NULL,

    volume BIGINT,

    source VARCHAR(50),

    UNIQUE(product_id, interval, timestamp)
);

CREATE TABLE investment.investment_accounts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    account_id UUID REFERENCES banking.accounts(id) ON DELETE RESTRICT, -- Yatırım hesabının bağlı olduğu ana vadesiz banka hesabı
    account_number VARCHAR(50) UNIQUE NOT NULL,
    currency_code VARCHAR(3) DEFAULT 'TRY',
    cash_balance NUMERIC(19, 4) DEFAULT 0,       -- Toplam nakit bakiye
    available_cash NUMERIC(19, 4) DEFAULT 0,     -- Çekilebilir/Kullanılabilir nakit
    buying_power NUMERIC(19, 4) DEFAULT 0,       -- Alım gücü (Kredili işlemler dahil olabilir)
    pending_settlement NUMERIC(19, 4) DEFAULT 0, -- Takas bekleyen bakiye (Örn: T+2 kuralı)
    status VARCHAR(20) DEFAULT 'active',
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE investment.portfolio_positions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    investment_account_id UUID NOT NULL REFERENCES investment.investment_accounts(id) ON DELETE CASCADE,
    product_id UUID NOT NULL REFERENCES investment.investment_products(id) ON DELETE CASCADE,
    quantity NUMERIC(19, 6) NOT NULL DEFAULT 0,  -- Küsuratlı fon/hisse adetleri için hassasiyet yüksek (6 basamak)
    average_buy_price NUMERIC(19, 4) NOT NULL,   -- Ortalama maliyet
    current_price NUMERIC(19, 4),                -- Anlık fiyat (Sürekli güncellenir)
    market_value NUMERIC(19, 4),                 -- Güncel piyasa değeri (quantity * current_price)
    unrealized_pnl NUMERIC(19, 4),               -- Gerçekleşmemiş Kar/Zarar tutarı
    unrealized_pnl_percent NUMERIC(8, 4),        -- Gerçekleşmemiş Kar/Zarar yüzdesi (Örn: %15.5)
    updated_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(investment_account_id, product_id)
    
    -- Bir hesapta aynı üründen sadece bir satır (pozisyon) olmalıdır.
    -- Bu yüzden account ve product ikilisi UNIQUE constraint
);

CREATE TABLE investment.portfolio_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Hangi yatırım hesabının anlık görüntüsü olduğunu bağlayan Foreign Key
    investment_account_id UUID NOT NULL REFERENCES investment.investment_accounts(id) ON DELETE CASCADE,
    
    -- Bu görüntünün (snapshot) alındığı an (Günde bir kez veya anlık alınabilir)
    timestamp TIMESTAMPTZ NOT NULL DEFAULT now(),
    
    -- Varlık Durumu
    total_market_value NUMERIC(19, 4) NOT NULL DEFAULT 0,  -- Sadece hisse/fon gibi varlıkların toplam değeri
    cash_balance NUMERIC(19, 4) NOT NULL DEFAULT 0,        -- O anki boşta duran nakit
    total_value NUMERIC(19, 4) NOT NULL DEFAULT 0,         -- Toplam portföy büyüklüğü (Varlıklar + Nakit)
    
    -- Günlük Performans
    daily_pnl NUMERIC(19, 4),                              -- Düne göre miktar bazında kâr/zarar (Örn: +1500.50)
    daily_pnl_percent NUMERIC(8, 4),                       -- Düne göre yüzde bazında kâr/zarar (Örn: +2.4500)
    
    -- Toplam (Kümülatif) Performans
    total_pnl NUMERIC(19, 4),                              -- Hesabın açılışından beri toplam kâr/zarar
    total_pnl_percent NUMERIC(8, 4)                        -- Toplam kâr/zarar yüzdesi
);

CREATE TABLE investment.investment_orders (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_number VARCHAR(50) UNIQUE NOT NULL,    -- Borsaya/Sisteme iletilen eşsiz emir numarası
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    investment_account_id UUID NOT NULL REFERENCES investment.investment_accounts(id) ON DELETE CASCADE,
    product_id UUID NOT NULL REFERENCES investment.investment_products(id) ON DELETE CASCADE,
    side VARCHAR(10) NOT NULL,                   -- 'BUY' (Alış) veya 'SELL' (Satış)
    order_type VARCHAR(20) NOT NULL,             -- 'MARKET', 'LIMIT', 'STOP' vb.
    
    -- Emir Miktarları ve Fiyatları
    quantity NUMERIC(19, 6) NOT NULL,            -- Talep edilen miktar
    limit_price NUMERIC(19, 4),                  -- Limit emirler için hedeflenen fiyat
    stop_price NUMERIC(19, 4),                   -- Stop emirler için tetiklenme fiyatı
    
    -- Gerçekleşme Durumu
    executed_quantity NUMERIC(19, 6) DEFAULT 0,  -- Şu ana kadar gerçekleşen miktar
    remaining_quantity NUMERIC(19, 6),           -- Kalan miktar
    average_execution_price NUMERIC(19, 4),      -- Gerçekleşen kısmın ortalama fiyatı
    
    status VARCHAR(20) DEFAULT 'pending',        -- 'pending', 'executed', 'partial', 'cancelled'
    
    -- Zaman Çizelgesi
    submitted_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    cancelled_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ
);

CREATE TABLE investment.investment_trades (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    trade_number VARCHAR(50) UNIQUE NOT NULL,    -- İşlem (Borsa/Takas) onay numarası
    order_id UUID NOT NULL REFERENCES investment.investment_orders(id) ON DELETE CASCADE,
    investment_account_id UUID NOT NULL REFERENCES investment.investment_accounts(id) ON DELETE CASCADE,
    product_id UUID NOT NULL REFERENCES investment.investment_products(id) ON DELETE CASCADE,
    side VARCHAR(10) NOT NULL,                   -- 'BUY' veya 'SELL'
    quantity NUMERIC(19, 6) NOT NULL,            -- Bu spesifik işlemde gerçekleşen miktar
    price NUMERIC(19, 4) NOT NULL,               -- Bu işlemin gerçekleştiği fiyat
    commission NUMERIC(19, 4) DEFAULT 0,         -- Kesilen aracı kurum komisyonu
    tax NUMERIC(19, 4) DEFAULT 0,                -- BSMV vb. vergiler
    total_amount NUMERIC(19, 4) NOT NULL,        -- Nihai yansıyan tutar (Miktar * Fiyat + Komisyon/Vergi)
    executed_at TIMESTAMPTZ NOT NULL,            -- İşlemin borsada gerçekleştiği an
    created_at TIMESTAMPTZ DEFAULT now()
);


-- NOTIFICATION --
CREATE TABLE notification.notifications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    notification_type TEXT NOT NULL,         -- Örn: 'security', 'transfer', 'price_alert'
    title TEXT NOT NULL,                     -- Bildirim başlığı
    message TEXT NOT NULL,                   -- Bildirimin tam metni
    
    -- Bildirim bir bankacılık veya yatırım işlemiyle ilgiliyse doğrudan o kayda bağlanır
    related_transaction_id UUID REFERENCES banking.transactions(id) ON DELETE SET NULL,
    related_order_id UUID REFERENCES investment.investment_orders(id) ON DELETE SET NULL,
    
    is_read BOOLEAN DEFAULT FALSE,           -- Okundu bilgisi
    read_at TIMESTAMPTZ,                     -- Okunduğu an
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE notification.notification_preferences (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    notification_type TEXT NOT NULL,         -- Örn: 'campaigns', 'security_alerts', 'account_activity'
    
    -- Varsayılan olarak mantıklı olan kanalları aktif/pasif başlatıyoruz
    in_app_enabled BOOLEAN DEFAULT TRUE,     
    email_enabled BOOLEAN DEFAULT TRUE,
    sms_enabled BOOLEAN DEFAULT FALSE,       -- SMS maliyetli olduğu için genelde opsiyoneldir
    
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(user_id, notification_type) -- Bir kullanıcının aynı bildirim türü için sadece bir ayar kaydı olabilir
);


-- ANALYTICS --
CREATE TABLE analytics.user_interactions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    interaction_type TEXT NOT NULL,          -- Örn: 'page_view', 'button_click', 'search'

    -- Kullanıcının etkileşime girdiği nesne (Örn: 'investment_product' tablosundaki 'X' ID'li hisse)
    entity_type TEXT,                        
    entity_id UUID,                          

    metadata JSONB,   -- İşleme dair diğer tüm esnek detaylar (Örn: {"duration_seconds": 45, "device": "mobile"})                       
    
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE analytics.audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id) ON DELETE SET NULL, 
    action TEXT NOT NULL,                    -- Örn: 'login_attempt', 'password_change', 'large_transfer'
    entity_type TEXT,                        -- Hangi tablo/nesne üzerinde işlem yapıldığı
    entity_id UUID,                          -- İşlem yapılan nesnenin ID'si
    status TEXT NOT NULL,                    -- Örn: 'success', 'failed', 'blocked'

    -- Güvenlik Bilgileri
    ip_address INET,                         -- PostgreSQL'in özel IP adresi veri tipi (IPv4 ve IPv6 destekler)
    user_agent TEXT,                         -- Kullanıcının tarayıcı/uygulama ve cihaz bilgisi
    
    metadata JSONB,                          -- Örn: {"old_email": "x@x.com", "new_email": "y@y.com"}
    created_at TIMESTAMPTZ DEFAULT now()
);



-- AI --
CREATE TABLE ai.conversations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    
    title TEXT,                              -- Chat geçmişinde görünecek başlık (AI tarafından özetlenebilir)
    status TEXT DEFAULT 'active',            -- 'active', 'archived', 'deleted'
    
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE ai.messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID NOT NULL REFERENCES ai.conversations(id) ON DELETE CASCADE,
    
    role TEXT NOT NULL,                      -- 'user', 'assistant' veya 'system'
    content TEXT NOT NULL,                   -- Mesajın kendisi
    
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE ai.rag_documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    title TEXT NOT NULL,                     -- Doküman başlığı
    source TEXT,                             -- 'KAP', 'Reuters', 'Internal_PDF' vb.
    source_url TEXT,                         -- Varsa dokümanın orijinal linki
    document_type TEXT,                      -- 'news', 'financial_report', 'faq'
    
    metadata JSONB,                          -- Yazar, yayın tarihi gibi ekstra esnek bilgiler
    
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE ai.rag_chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL REFERENCES ai.rag_documents(id) ON DELETE CASCADE,
    
    content TEXT NOT NULL,                   -- Parçalanmış saf metin
    chunk_index INTEGER NOT NULL,            -- Doküman içindeki sıra numarası (0, 1, 2...)
    
    -- 1536 boyutu OpenAI (text-embedding-ada-002 veya text-embedding-3-small) için standarttır.
    -- Eğer açık kaynaklı (örneğin BAAI/bge-m3) kullanacaksan 1024 gibi modelin boyutunu yazmalısın.
    embedding VECTOR(1536),                  
    
    metadata JSONB,                          -- O chunk'a özel etiketler
    
    created_at TIMESTAMPTZ DEFAULT now()
);


CREATE INDEX idx_market_quotes_product_time
ON investment.market_quotes(product_id, market_timestamp DESC);

CREATE INDEX idx_market_candles_product_interval_time
ON investment.market_candles(product_id, interval, timestamp DESC);

CREATE INDEX idx_user_interactions_user_time
ON analytics.user_interactions(user_id, created_at DESC);

CREATE INDEX idx_ai_messages_conversation
ON ai.messages(conversation_id, created_at);

ALTER TABLE auth.risk_profiles 
ADD COLUMN latest_assessment_id UUID REFERENCES auth.risk_assessments(id);

ALTER TABLE auth.user_profiles 
ADD COLUMN dashboard_layout JSONB;  --hareketli widget düzeni için

-- JSON:
-- {
--   "top_left": "portfolio_summary",
--   "top_right": "market_news",
--   "bottom_center": "quick_transfer"
-- }