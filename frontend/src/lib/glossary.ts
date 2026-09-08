/**
 * Finansal terim sözlüğü — uygulama geneli, tek kaynak.
 *
 * Risk sayfası için yazıldı ama oraya kilitlenmedi: aynı terimler Portföy'de
 * (F/K, PD/DD), Piyasalar'da (hacim, piyasa değeri) ve sohbet balonlarında da
 * geçiyor. Tanımı tek yerde tutmak, aynı kelimenin iki ekranda iki farklı
 * şekilde açıklanmasını engelliyor.
 *
 * Üç kural:
 *
 * 1. **Tanım, yorum değil.** "Oynaklığınız yüksek" bir eşik yargısıdır ve
 *    `ORCHESTRATOR_SYSTEM_PROMPT`'un yasakladığı şeydir; "bir yıl içinde
 *    ortalamadan ne kadar saptığının ölçüsü" bir tanımdır. Ekranın sözü ile
 *    asistanın sözü aynı çizgide durmalı.
 * 2. **Referans, eşik değil.** `anchors` alanı ölçeğin uçlarını gösterir
 *    ("tek pozisyon = 1,0"), "şu değerin altı iyidir" demez. Yeni başlayan
 *    için 6,1 sayısını anlamlı kılan şey ölçek; ona nerede durması
 *    gerektiğini söylemek bize düşmez.
 * 3. **Hiçbir alan adı geçmez.** CLAUDE.md'nin NAMING kuralı burada da
 *    geçerli: kullanıcı `max_drawdown` değil "en derin düşüş" okur.
 */

export interface GlossaryEntry {
    /** Başlık — açıklama kutusunun tepesinde. */
    title: string
    /** Kartın altında kalıcı duran tek cümle. */
    short: string
    /** (i) ikonuna basıldığında açılan uzun açıklama. */
    long: string
    /** Somut bir örnek. Sayı vermek, tanımı üç kat anlaşılır yapıyor. */
    example?: string
    /** Ölçeğin uçları. Yargı değil, cetvel. */
    anchors?: string[]
}

export const GLOSSARY: Record<string, GlossaryEntry> = {
    volatility: {
        title: 'Yıllık oynaklık',
        short: 'Portföy değerinin bir yıl içinde ortalamadan ne kadar saptığının ölçüsü.',
        long:
            'Fiyatın ne kadar hareketli olduğunu anlatır, ne yönde hareket ettiğini değil. ' +
            'Yukarı ve aşağı hareketler eşit sayılır: sert yükselen bir portföyün de ' +
            'oynaklığı yüksek çıkar. Geçmiş günlük değişimlerden hesaplanır ve yıllığa çevrilir.',
        example:
            '%20 oynaklık, portföyün bir yıl içinde tipik olarak %20 kadar yukarı ya da ' +
            'aşağı salınması demek.',
        anchors: [
            'Geniş bir hisse endeksi genelde %15–25 aralığında salınır',
            'Tek bir hissede %40 ve üzeri sık görülür',
        ],
    },
    downside_deviation: {
        title: 'Aşağı yönlü sapma',
        short: 'Yalnızca kayıp günlerinin dalgalanması; yukarı hareketler sayılmaz.',
        long:
            'Oynaklık yükselişi de düşüş kadar "risk" sayar. Bu ölçü yalnızca değer ' +
            'kaybettiğiniz günlere bakar, dolayısıyla "kötü tarafın" ne kadar sert ' +
            'olduğunu oynaklıktan daha doğrudan anlatır.',
        example:
            'Oynaklığı yüksek ama düşüşleri ılımlı bir portföyde bu sayı oynaklığın ' +
            'belirgin biçimde altında kalır.',
    },
    sharpe: {
        title: 'Sharpe oranı',
        short: 'Alınan dalgalanma başına elde edilen getiri.',
        long:
            'Getiriyi tek başına değil, o getiriyi elde ederken katlanılan dalgalanmayla ' +
            'birlikte ölçer. Faizde durarak elde edilebilecek getirinin üzerine ne ' +
            'eklendiğini, oynaklığa bölerek verir. Negatif değer, dönem boyunca faizin ' +
            'altında kalındığı anlamına gelir.',
        example:
            'Aynı getiriyi yarı yarıya daha az dalgalanmayla elde eden bir portföyün ' +
            'Sharpe oranı iki katıdır.',
        anchors: [
            'Sıfır: faizle aynı sonuç',
            'Negatif: dönem boyunca faizin altında kalınmış',
        ],
    },
    beta: {
        title: 'Endekse duyarlılık',
        short: 'Endeks %1 hareket ettiğinde portföyün tarihsel olarak ne kadar hareket ettiği.',
        long:
            'Portföyün piyasayla birlikte ne kadar sert hareket ettiğini gösterir. ' +
            'Geçmişe bakarak hesaplanır ve piyasanın gelecekte ne yapacağını söylemez. ' +
            'Endeksin kendisiyle ölçüldüğünde sonuç tanımı gereği 1,0’dır.',
        anchors: [
            '1,0: endeksle aynı ölçüde hareket',
            '1,0 üzeri: endeksten daha sert',
            'Sıfıra yakın: endeksten büyük ölçüde bağımsız',
        ],
    },
    correlation: {
        title: 'Endeksle birlikte hareket',
        short: '1’e yakın değer endeksle aynı yönde, 0 ilişkisiz, -1 ters yönde demek.',
        long:
            'Duyarlılıktan farkı: bu ölçü hareketin ŞİDDETİNİ değil, YÖN BİRLİKTELİĞİNİ ' +
            'anlatır. Portföy endeksle aynı günlerde mi yükseliyor sorusunun cevabıdır.',
        anchors: ['1,0: her zaman aynı yönde', '0: ilişkisiz', '-1,0: her zaman ters yönde'],
    },
    var: {
        title: 'Günlük kayıp eşiği',
        short: 'Geçmiş günlerin büyük çoğunluğunda günlük kaybın altında kaldığı seviye.',
        long:
            'Geçmiş günlük değişimler sıralanır ve en kötü uçtan bir kesit alınır. ' +
            'GEÇMİŞTE ölçülen bir eşiktir; geleceğe dair bir sınır ya da bir tahmin ' +
            'DEĞİLDİR. Kalan günlerde kayıp bu seviyenin üzerine çıkmıştır ve yine ' +
            'çıkabilir.',
        example:
            '%95 güvenle %4’lük bir eşik, geçmiş 100 günün yaklaşık 95’inde günlük ' +
            'kaybın %4’ün altında kaldığı anlamına gelir — kalan 5 günde daha fazlası.',
    },
    cvar: {
        title: 'Eşik aşıldığında ortalama kayıp',
        short: 'Kaybın eşiği aştığı günlerde ortalama olarak ne kadar kaybedildiği.',
        long:
            'Kayıp eşiği "ne kadar sık" sorusunu yanıtlar, bu ölçü "aşıldığında ne ' +
            'kadar kötü" sorusunu. Kötü günlerin ortalamasıdır ve her zaman kayıp ' +
            'eşiğinden büyüktür. Yine geçmiş bir ölçümdür, tahmin değildir.',
    },
    max_drawdown: {
        title: 'En derin düşüş',
        short: 'Zirveden dibe yaşanan en büyük değer kaybı.',
        long:
            'Ortalama bir dalgalanmayı değil, dönemin en kötü anını ölçer: portföy bir ' +
            'zirveye çıktıktan sonra en fazla ne kadar geri verdi. Toparlanma tarihi, ' +
            'değerin o zirveye geri döndüğü günü gösterir; boşsa henüz dönmemiştir.',
        example:
            '%30 düşen bir portföyün başa dönmesi için %43 yükselmesi gerekir — düşüş ' +
            've toparlanma simetrik değildir.',
    },
    effective_n: {
        title: 'Etkin dağılım',
        short: 'Portföyün kaç eşit ağırlıklı pozisyona denk geldiği.',
        long:
            'Kaç pozisyonunuz olduğunu değil, değerin gerçekte kaç isme dağıldığını ' +
            'söyler. Yirmi hisseniz olsa bile değerin çoğu birindeyse bu sayı 1’e ' +
            'yaklaşır. Yoğunlaşma ölçüsünün okunabilir hâlidir.',
        anchors: [
            '10 eşit pozisyon ≈ 10,0',
            'Tek pozisyon = 1,0',
            'Biri %90, dokuzu %1 olan portföy ≈ 1,2',
        ],
    },
    concentration: {
        title: 'Yoğunlaşma',
        short: 'Portföy değerinin ne kadar az isimde toplandığı.',
        long:
            'Değerin dar bir alanda toplanması, tek bir şirketin ya da sektörün ' +
            'kaderini portföyün kaderi hâline getirir. Fiyat geçmişi gerektirmez, ' +
            'yalnızca bugünkü ağırlıklardan hesaplanır — bu yüzden yeni bir portföyde ' +
            'bile ölçülebilir.',
    },
    risk_score: {
        title: 'Risk puanı',
        short: '100’e yakın puan daha sakin bir portföy demek.',
        long:
            'Ölçek TERSTİR: yüksek puan düşük risk anlamına gelir. Puan üç ölçümden ' +
            'oluşur — oynaklık (%45), yoğunlaşma (%35) ve en derin düşüş (%20). ' +
            'Ölçülemeyen bir bileşen sıfır sayılmaz, hesaptan çıkarılır ve kalan ' +
            'ağırlıklar yeniden dağıtılır.',
        anchors: [
            '85 ve üzeri: Risksiz',
            '70–85 arası: Düşük',
            '45–70 arası: Orta',
            '45 altı: Yüksek',
        ],
    },
    risk_contribution: {
        title: 'Riskteki pay',
        short: 'Portföyün dalgalanmasının ne kadarının o pozisyondan geldiği.',
        long:
            'Ağırlıkla aynı şey DEĞİLDİR. Ağırlık, pozisyonun portföydeki büyüklüğü; ' +
            'riskteki pay ise dalgalanmaya ne kadar katkı verdiği. Birlikte hareket ' +
            'eden pozisyonlar — örneğin hepsi aynı sektörden olanlar — ağırlıklarının ' +
            'toplamından daha fazla risk taşır. Portföyün geri kalanının tersine ' +
            'hareket eden bir pozisyonun payı eksi çıkabilir: dalgalanmayı azaltmış ' +
            'demektir. Paylar toplamı %100’dür.',
        anchors: [
            'Pay > ağırlık: geri kalanla birlikte hareket ediyor',
            'Pay < ağırlık: bağımsız hareket etmiş',
            'Pay eksi: dalgalanmayı azaltmış',
        ],
    },
    reliability: {
        title: 'İstatistiksel güvenilirlik',
        short: 'Ölçümün arkasında yeterli gözlem olup olmadığı.',
        long:
            'Kısa bir geçmişten hesaplanan oynaklık, tesadüfen sakin ya da tesadüfen ' +
            'sert geçmiş birkaç haftayı yansıtabilir. Altmış işlem gününün altındaki ' +
            'ölçümler ve portföyün onda birinden fazlasının fiyatsız kaldığı durumlar ' +
            'güvenilir sayılmaz ve bu ayrıca belirtilir.',
    },
    // --- Risk dışı, uygulama geneli --------------------------------------
    pe_ratio: {
        title: 'F/K oranı',
        short: 'Hisse fiyatının, şirketin hisse başına kârına oranı.',
        long:
            'Şirketin bir liralık yıllık kârı için kaç lira ödendiğini gösterir. ' +
            'Sektörler arasında doğal olarak farklıdır; bir bankayla bir teknoloji ' +
            'şirketini bu oranla doğrudan karşılaştırmak yanıltıcıdır.',
    },
    pb_ratio: {
        title: 'PD/DD oranı',
        short: 'Piyasa değerinin, şirketin defter değerine oranı.',
        long:
            'Şirketin bilançosundaki öz kaynağa göre piyasada kaça değerlendiğini ' +
            'gösterir. Varlık ağırlıklı şirketlerde daha anlamlı, hizmet ve yazılım ' +
            'şirketlerinde daha az bilgilendiricidir.',
    },
    market_cap: {
        title: 'Piyasa değeri',
        short: 'Şirketin borsadaki toplam değeri.',
        long: 'Hisse fiyatı ile toplam hisse sayısının çarpımı. Şirketin büyüklüğünün ölçüsüdür.',
    },
    volume: {
        title: 'Günlük işlem hacmi',
        short: 'Gün içinde el değiştiren hisse miktarı.',
        long:
            'Alıcı ve satıcı bulmanın ne kadar kolay olduğuna dair bir göstergedir. ' +
            'Hacmi düşük bir hissede istediğiniz fiyattan işlem yapmak zorlaşır.',
    },
}

/** Sözlükte olmayan bir anahtar sessizce yok sayılır, ekranı bozmaz. */
export function lookupTerm(key: string): GlossaryEntry | null {
    return GLOSSARY[key] ?? null
}
