/**
 * Adres -> başlık.
 *
 * Bileşenden ayrı bir dosyada, çünkü bu JSX değil kural: tablo
 * `location.pathname` ile TAM eşleşiyordu ve alt rotası olan her ekran
 * başlıksız kalıyordu. Kapsama kapısı (`vitest.config.ts`) `src/lib/**`
 * altını sayıyor, bileşenleri saymıyor -- geri gelmesini istemediğimiz bir
 * hatanın testi burada durabiliyor.
 */
const ROUTE_TITLE_MAP: Record<string, string> = {
  '/dashboard':     'Gösterge Paneli',
  '/hizli-finans':  'Hızlı Finans',
  '/banking':       'Cüzdan & İşlemler',
  '/investment':    'Piyasalar',
  '/chat':          'AI Finansal Asistan',
  '/analiz':        'Analiz',
  '/portfolio':     'Portföy',
  '/settings':      'Ayarlar',
}

const FALLBACK_TITLE = 'MoneyFast'

/**
 * Adresin başlığı — EN UZUN önek eşleşmesi.
 *
 * Tablo `location.pathname` ile TAM eşleşiyordu, dolayısıyla alt rotası olan
 * her ekran başlıksız kalıyordu: `/investment/hisseler` `/investment`'i
 * ıskalayıp "MoneyFast"e düşüyordu, `/analiz/genel`, `/banking/accounts` ve
 * `/settings/profile` de öyle. Ekranın kendi adı yerine uygulamanın adını
 * göstermek, kullanıcıya nerede olduğunu söylememektir.
 *
 * En uzun önek, çünkü bir gün `/investment/fonlar` kendi başlığını isterse
 * `/investment`'ten önce eşleşmesi gerekir.
 */
export function titleFor(
  pathname: string,
  //: Tabloyu dışarıdan almak, "en uzun önek kazanır" iddiasının test
  //: edilebilmesi için: bugünkü haritada iç içe iki rota YOK, dolayısıyla
  //: sıralama gerçek kullanımda hiç iki elemanla çalışmıyor. Doğrulanmayan
  //: bir kural, bir gün `/investment/fonlar` eklendiğinde sessizce yanlış
  //: başlık gösterirdi.
  titles: Record<string, string> = ROUTE_TITLE_MAP,
): string {
  const match = Object.keys(titles)
    .filter((route) => pathname === route || pathname.startsWith(`${route}/`))
    .sort((a, b) => b.length - a.length)[0]
  return match ? titles[match] : FALLBACK_TITLE
}
