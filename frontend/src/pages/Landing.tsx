/**
 * @module Landing
 * @description MoneyFast platformunun giriş (karşılama) sayfası bileşeni.
 *
 * Mimari notlar:
 *  - Bu bileşen Layout sarmalayıcısından bağımsız, tam ekran (standalone) render edilir.
 *  - Navigasyon, react-router-dom'un `Link` bileşeni aracılığıyla gerçekleştirilir;
 *    tam sayfa yenileme olmaksızın istemci tarafı geçiş sağlanır.
 *  - Animasyonlar yalnızca Tailwind CSS yardımcı sınıfları ile uygulanmıştır;
 *    harici animasyon kütüphanesi bağımlılığı yoktur.
 *  - Floating placeholder konteynerler, ilerleyen geliştirme döngüsünde
 *    Blender çıktısı flat grafik ikonlarla doldurulacak şekilde konumlandırılmıştır.
 */

import { Link } from 'react-router-dom'

// ─────────────────────────────────────────────────────────────────────────────
// Alt Bileşen: AnimatedBlob
// ─────────────────────────────────────────────────────────────────────────────

/**
 * @interface AnimatedBlobProps
 * @description Dekoratif arka plan lekesinin boyut, renk ve konum parametreleri.
 */
interface AnimatedBlobProps {
  /** Tailwind `absolute` konumlandırma ve boyut sınıfları. */
  className: string
  /** Pulse animasyonu gecikme süresi — lekelerin eş zamanlı titreşmesini önler. */
  animationDelay: string
}

/**
 * @component AnimatedBlob
 * @description Arka planda yavaşça nefes alan dekoratif renk lekesi.
 * `blur-3xl` ve `animate-pulse` kombinasyonu ile canlı glassmorphism efekti üretir.
 */
function AnimatedBlob({ className, animationDelay }: AnimatedBlobProps) {
  return (
    <div
      aria-hidden="true"
      className={`pointer-events-none absolute rounded-full blur-3xl animate-pulse ${className}`}
      style={{ animationDelay }}
    />
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// Alt Bileşen: FloatingPlaceholder
// ─────────────────────────────────────────────────────────────────────────────

/**
 * @interface FloatingPlaceholderProps
 * @description Süzülen görsel konteynerin konumlandırma ve animasyon parametreleri.
 */
interface FloatingPlaceholderProps {
  /** Tailwind `absolute` konum ve boyut sınıfları. */
  className: string
  /** CSS animasyon gecikmesi — her konteynerin farklı fazda süzülmesini sağlar. */
  animationDelay: string
}

/**
 * @component FloatingPlaceholder
 * @description Blender çıktısı flat grafik ikonlar için rezerve edilmiş, süzülen görsel konteyneri.
 * Glassmorphism kart yapısını benimser; üretim aşamasında `<img>` veya SVG ile doldurulacaktır.
 * Keyframe tanımlı CSS yerine `translate-y` tabanlı `animate-bounce` tercih edilmiştir;
 * animasyon süresi `animation-duration` ile yumuşatılmıştır.
 */
function FloatingPlaceholder({ className, animationDelay }: FloatingPlaceholderProps) {
  return (
    <div
      aria-hidden="true"
      className={`pointer-events-none absolute flex items-center justify-center rounded-[2rem] border border-white/60 bg-white/40 backdrop-blur-sm shadow-[0_8px_32px_rgba(15,23,42,0.08)] ${className}`}
      style={{ animationDelay, animation: `bounce 3s ease-in-out ${animationDelay} infinite` }}
    >
      {/* İkon yer tutucu — üretimde Blender çıktısıyla değiştirilecek */}
      <div className="flex flex-col items-center gap-2 opacity-30">
        <div className="h-8 w-8 rounded-lg bg-slate-400" />
        <div className="h-2 w-12 rounded-full bg-slate-400" />
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// Ana Bileşen
// ─────────────────────────────────────────────────────────────────────────────

/**
 * @component Landing
 * @description MoneyFast'ın vizyon ve karşılama sayfası.
 *
 * Sayfa yapısı:
 *  1. Dekoratif arka plan katmanı (animasyonlu blob'lar, pointer-events: none)
 *  2. Süzülen görsel placeholder konteynerleri (gelecek Blender ikonları için)
 *  3. Hero bölümü — ana slogan, alt metin, CTA butonları
 *  4. Yasal alt bilgi
 */
export default function Landing() {
  return (
    <div className="relative min-h-screen overflow-x-hidden bg-slate-50 font-sans selection:bg-emerald-200">

      {/* ── Üst Bölüm (Hero) ───────────────────────────────────────────────── */}
      <section className="relative min-h-screen flex flex-col items-center justify-center">
        {/* Katman 1: Animasyonlu Arka Plan Blob'ları */}
        <AnimatedBlob
          className="h-[640px] w-[640px] -left-32 -top-32 bg-emerald-200 opacity-30"
          animationDelay="0s"
        />
        <AnimatedBlob
          className="h-[560px] w-[560px] -bottom-40 -right-24 bg-teal-200 opacity-25"
          animationDelay="1.4s"
        />
        <AnimatedBlob
          className="h-[300px] w-[300px] left-1/2 top-1/3 -translate-x-1/2 bg-emerald-100 opacity-20"
          animationDelay="0.7s"
        />

        {/* Katman 2: Süzülen Görsel Placeholder Konteynerleri */}
        <FloatingPlaceholder
          className="hidden md:flex h-28 w-28 left-[8%] top-[18%]"
          animationDelay="0s"
        />
        <FloatingPlaceholder
          className="hidden md:flex h-24 w-24 right-[9%] top-[22%]"
          animationDelay="0.6s"
        />
        <FloatingPlaceholder
          className="hidden lg:flex h-20 w-20 left-[14%] bottom-[22%]"
          animationDelay="1.1s"
        />

        {/* Katman 3: Hero İçeriği */}
        <div className="relative z-10 flex flex-col items-center justify-center px-6 text-center mt-20">
          <div className="mb-8 inline-flex items-center gap-2 rounded-full border border-emerald-200 bg-white/80 px-4 py-1.5 backdrop-blur-sm shadow-sm">
            <span className="h-[6px] w-[6px] animate-pulse rounded-full bg-emerald-500" aria-hidden="true" />
            <span className="text-[0.7rem] font-semibold uppercase tracking-[0.18em] text-emerald-700">
              YENİ NESİL FİNANS UYGULAMASI
            </span>
          </div>

          <h1 className="max-w-4xl text-[clamp(2.4rem,6vw,4.5rem)] font-extrabold leading-[1.05] tracking-tight text-slate-950">
            Paranızı Hızla Yönetin,{' '}
            <span className="bg-gradient-to-r from-emerald-500 via-teal-500 to-emerald-400 bg-clip-text text-transparent">
              MoneyFast
            </span>{' '}
            ile Sınırları Aşın
          </h1>

          <p className="mt-8 max-w-2xl text-[1.125rem] leading-relaxed text-slate-500">
            Finansal özgürlüğünüze giden en kısa yol! Hesaplarınızı saniyeler içinde analiz edin, yapay zekâ destekli akıllı asistanımızla yatırımlarınızı büyütün. Masrafsız, anında ve güvenli işlem ayrıcalığıyla kontrol tamamen sizde.
          </p>

          <div className="mt-12 flex flex-wrap items-center justify-center gap-4">
            <Link
              to="/login"
              className="group relative inline-flex items-center gap-2 overflow-hidden rounded-2xl bg-slate-950 px-8 py-4 text-[1rem] font-semibold text-white shadow-lg shadow-slate-900/20 transition-all duration-300 hover:-translate-y-1 hover:bg-slate-800 hover:shadow-xl hover:shadow-slate-900/30 focus:outline-none focus:ring-4 focus:ring-slate-300"
            >
              <span className="relative z-10 flex items-center gap-2">
                Oturum Aç
                <span aria-hidden="true" className="transition-transform duration-300 group-hover:translate-x-1">→</span>
              </span>
              <div className="absolute inset-0 z-0 h-full w-full bg-gradient-to-r from-emerald-500/0 via-emerald-500/10 to-emerald-500/0 opacity-0 transition-opacity duration-300 group-hover:opacity-100" />
            </Link>

            <Link
              to="/register"
              className="inline-flex items-center gap-2 rounded-2xl border-2 border-slate-200 bg-white/50 backdrop-blur-sm px-8 py-4 text-[1rem] font-semibold text-slate-700 transition-all duration-300 hover:-translate-y-1 hover:border-slate-300 hover:bg-white hover:shadow-lg focus:outline-none focus:ring-4 focus:ring-slate-200"
            >
              Kayıt Ol
            </Link>
          </div>

          <p className="mt-6 text-sm font-medium text-slate-400">
            Kredi kartı gerektirmez &middot; Ücretsiz kayıt
          </p>
        </div>

        {/* Scroll indicator */}
        <div className="absolute bottom-10 left-1/2 -translate-x-1/2 animate-bounce text-slate-300">
          ↓
        </div>
      </section>

      {/* ── Özellikler Bölümü (Features) ───────────────────────────────────── */}
      <section className="relative z-10 bg-white py-32 px-6">
        <div className="mx-auto max-w-7xl">
          <div className="mb-20 text-center">
            <h2 className="text-3xl font-bold tracking-tight text-slate-900 sm:text-5xl">
              Geleceğin Bankacılığı <br className="hidden sm:block" /> Bugün Cebinizde
            </h2>
            <p className="mx-auto mt-6 max-w-2xl text-lg text-slate-500">
              Geleneksel bankaların hantal süreçlerini unutun. Sizin hızınıza ayak uyduran, tamamen kişiselleştirilmiş bir deneyime hazır olun.
            </p>
          </div>

          <div className="grid gap-10 sm:grid-cols-2 lg:grid-cols-3">
            {/* Feature 1 */}
            <div className="group relative rounded-3xl border border-slate-100 bg-slate-50 p-8 transition-all hover:bg-white hover:shadow-2xl hover:shadow-emerald-500/5 hover:-translate-y-2">
              <div className="mb-6 flex h-14 w-14 items-center justify-center rounded-2xl bg-emerald-100 text-2xl shadow-sm transition-transform group-hover:scale-110">
                ⚡️
              </div>
              <h3 className="mb-3 text-xl font-bold text-slate-900">Işık Hızında Transfer</h3>
              <p className="text-slate-500 leading-relaxed">
                Dünyanın her yerine, 7/24 kesintisiz ve anında para gönderin. Beklemek, mesai saatleri veya gizli ücretler yok. Sadece saniyeler var.
              </p>
            </div>

            {/* Feature 2 */}
            <div className="group relative rounded-3xl border border-slate-100 bg-slate-50 p-8 transition-all hover:bg-white hover:shadow-2xl hover:shadow-emerald-500/5 hover:-translate-y-2">
              <div className="mb-6 flex h-14 w-14 items-center justify-center rounded-2xl bg-teal-100 text-2xl shadow-sm transition-transform group-hover:scale-110">
                🤖
              </div>
              <h3 className="mb-3 text-xl font-bold text-slate-900">AI Finans Asistanı</h3>
              <p className="text-slate-500 leading-relaxed">
                Harcama alışkanlıklarınızı analiz eden ve size özel tasarruf tavsiyeleri veren yapay zekâ asistanınız her an yanınızda.
              </p>
            </div>

            {/* Feature 3 */}
            <div className="group relative rounded-3xl border border-slate-100 bg-slate-50 p-8 transition-all hover:bg-white hover:shadow-2xl hover:shadow-emerald-500/5 hover:-translate-y-2">
              <div className="mb-6 flex h-14 w-14 items-center justify-center rounded-2xl bg-blue-100 text-2xl shadow-sm transition-transform group-hover:scale-110">
                🛡️
              </div>
              <h3 className="mb-3 text-xl font-bold text-slate-900">Askeri Düzey Güvenlik</h3>
              <p className="text-slate-500 leading-relaxed">
                Biyometrik doğrulama, uçtan uca şifreleme ve anlık dolandırıcılık tespiti ile paranız her zaman en üst düzey koruma altında.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* ── İstatistikler / Sosyal Kanıt ───────────────────────────────────── */}
      <section className="relative overflow-hidden bg-slate-950 py-24 text-center sm:py-32">
        <div className="absolute inset-0 opacity-10 bg-[radial-gradient(ellipse_at_center,_var(--tw-gradient-stops))] from-emerald-500 via-slate-950 to-slate-950"></div>
        <div className="relative z-10 mx-auto max-w-7xl px-6">
          <div className="grid grid-cols-1 gap-y-16 sm:grid-cols-3 sm:gap-x-8">
            <div className="flex flex-col gap-y-3">
              <dt className="text-base leading-7 text-slate-400">Aktif Kullanıcı</dt>
              <dd className="text-5xl font-extrabold tracking-tight text-white">500B+</dd>
            </div>
            <div className="flex flex-col gap-y-3">
              <dt className="text-base leading-7 text-slate-400">İşlem Hacmi (Aylık)</dt>
              <dd className="text-5xl font-extrabold tracking-tight text-white">₺2.4Mly</dd>
            </div>
            <div className="flex flex-col gap-y-3">
              <dt className="text-base leading-7 text-slate-400">Müşteri Memnuniyeti</dt>
              <dd className="text-5xl font-extrabold tracking-tight text-white">%99.8</dd>
            </div>
          </div>
        </div>
      </section>

      {/* ── CTA Bölümü ─────────────────────────────────────────────────────── */}
      <section className="relative z-10 bg-slate-50 py-32 px-6 text-center">
        <div className="mx-auto max-w-3xl">
          <h2 className="text-4xl font-bold tracking-tight text-slate-900 sm:text-5xl">
            Kontrolü Ele Alma Vakti
          </h2>
          <p className="mx-auto mt-6 max-w-xl text-lg leading-8 text-slate-500">
            Hemen ücretsiz hesabınızı oluşturun ve finansal özgürlüğün tadını çıkarmaya başlayın.
            MoneyFast ile gelecek sizin ellerinizde.
          </p>
          <div className="mt-10 flex items-center justify-center gap-x-6">
            <Link
              to="/login"
              className="rounded-full bg-emerald-500 px-8 py-4 text-sm font-semibold text-white shadow-sm hover:bg-emerald-400 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-500 transition-all hover:scale-105"
            >
              Hemen Hesabını Oluştur
            </Link>
          </div>
        </div>
      </section>

      {/* ── Yasal Alt Bilgi ──────────────────────────────────────────────── */}
      <footer className="relative z-10 border-t border-slate-200 bg-white py-8 text-center">
        <p className="text-sm text-slate-400">
          © {new Date().getFullYear()} MoneyFast — InternTech 2026, InterFive Takımı
        </p>
      </footer>

    </div>
  )
}
