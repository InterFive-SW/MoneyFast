import { Link } from 'react-router-dom'
import logo from '../assets/logo.png'
import logoInline from '../assets/logo-inline.png'
import interfiveLogo from '../assets/interfive.png'

// ─────────────────────────────────────────────────────────────────────────────
// Alt Bileşen: AnimatedBlob
// ─────────────────────────────────────────────────────────────────────────────

interface AnimatedBlobProps {
  className: string
  animationDelay: string
}

function AnimatedBlob({ className, animationDelay }: AnimatedBlobProps) {
  return (
    <div
      aria-hidden="true"
      className={`pointer-events-none absolute rounded-full blur-[100px] animate-pulse ${className}`}
      style={{ animationDelay }}
    />
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// Ana Bileşen
// ─────────────────────────────────────────────────────────────────────────────

export default function Landing() {
  return (
    <div className="relative min-h-screen overflow-x-hidden bg-slate-950 font-sans text-slate-300 selection:bg-brandBlue selection:text-white">
      
      {/* ── Üst Bölüm (Hero) ───────────────────────────────────────────────── */}
      <header className="absolute left-6 top-4 z-50 sm:left-10 sm:top-4 flex w-full justify-between items-center pr-12 sm:pr-20">
        <img src={logoInline} alt="MoneyFast Logo" className="h-20 sm:h-28 w-auto object-contain transition-transform duration-300 hover:scale-105" />
        <div className="hidden sm:flex items-center gap-4">
          <Link to="/login" className="text-sm font-medium text-slate-300 hover:text-white transition-colors">Giriş Yap</Link>
          <Link to="/register" className="text-sm font-medium bg-white/10 hover:bg-white/20 border border-white/10 px-5 py-2 rounded-full text-white backdrop-blur-md transition-all">Kayıt Ol</Link>
        </div>
      </header>

      <section className="relative min-h-screen flex flex-col items-center justify-center pt-20">
        {/* Katman 1: Animasyonlu Arka Plan Blob'ları (Glassmorphism & Glow) */}
        <AnimatedBlob
          className="h-[500px] w-[500px] -left-32 -top-32 bg-primary-500 opacity-40 mix-blend-screen"
          animationDelay="0s"
        />
        <AnimatedBlob
          className="h-[600px] w-[600px] -bottom-40 -right-24 bg-brandBlue opacity-30 mix-blend-screen"
          animationDelay="1.4s"
        />
        <AnimatedBlob
          className="h-[400px] w-[400px] left-1/2 top-1/3 -translate-x-1/2 bg-accent-400 opacity-20 mix-blend-screen"
          animationDelay="0.7s"
        />

        {/* Dekoratif Izgara Arka Plan */}
        <div className="absolute inset-0 bg-[url('data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iNjAiIGhlaWdodD0iNjAiIHhtbG5zPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyI+PGcgc3Ryb2tlPSIjZmZmZmZmIiBzdHJva2Utb3BhY2l0eT0iMC4wNSIgZmlsbD0ibm9uZSI+PHBhdGggZD0iTTAgNjBoNjBNNjAgMGwwIDYwIi8+PC9nPjwvc3ZnPg==')] opacity-50 pointer-events-none" />

        {/* Katman 3: Hero İçeriği */}
        <div className="relative z-10 flex flex-col items-center justify-center px-6 text-center mt-10">
          <div className="mb-8 inline-flex items-center gap-2 rounded-full border border-primary-400/30 bg-primary-900/30 px-4 py-1.5 backdrop-blur-md shadow-[0_0_15px_rgba(168,92,249,0.3)]">
            <span className="h-[6px] w-[6px] animate-pulse rounded-full bg-accent-400" aria-hidden="true" />
            <span className="text-[0.7rem] font-semibold uppercase tracking-[0.18em] text-accent-300">
              YENİ NESİL FİNANS UYGULAMASI
            </span>
          </div>

          <h1 className="max-w-4xl text-[clamp(2.4rem,6vw,4.5rem)] font-black leading-[1.1] tracking-tight text-white drop-shadow-lg">
            <span className="block mb-4">Paranızı Hızla Yönetin,</span>
            <div className="inline-flex items-center justify-center">
              <span className="bg-gradient-to-r from-accent-400 via-brandBlue to-primary-400 bg-clip-text text-transparent">MoneyFast</span>
            </div>
            <span className="block mt-4">ile Sınırları Aşın</span>
          </h1>

          <p className="mt-8 max-w-2xl text-[1.125rem] leading-relaxed text-slate-400 font-medium">
            Finansal özgürlüğünüze giden en kısa yol! Hesaplarınızı saniyeler içinde analiz edin, yapay zekâ destekli akıllı asistanımızla yatırımlarınızı büyütün.
          </p>

          <div className="mt-12 flex flex-wrap items-center justify-center gap-4">
            <Link
              to="/login"
              className="group relative inline-flex items-center gap-2 overflow-hidden rounded-2xl bg-gradient-to-r from-brandBlue to-primary-500 px-8 py-4 text-[1rem] font-semibold text-white shadow-[0_0_30px_rgba(75,123,229,0.4)] transition-all duration-300 hover:-translate-y-1 hover:shadow-[0_0_40px_rgba(75,123,229,0.6)] focus:outline-none focus:ring-4 focus:ring-brandBlue/50"
            >
              <span className="relative z-10 flex items-center gap-2">
                Hemen Başlayın
                <span aria-hidden="true" className="transition-transform duration-300 group-hover:translate-x-1">→</span>
              </span>
            </Link>

            <Link
              to="/register"
              className="inline-flex items-center gap-2 rounded-2xl border border-white/10 bg-white/5 backdrop-blur-md px-8 py-4 text-[1rem] font-semibold text-white transition-all duration-300 hover:-translate-y-1 hover:border-white/30 hover:bg-white/10 hover:shadow-lg focus:outline-none focus:ring-4 focus:ring-slate-700"
            >
              Ücretsiz Kayıt Ol
            </Link>
          </div>

          <p className="mt-6 text-sm font-medium text-slate-500">
            Kredi kartı gerektirmez &middot; 7/24 Kesintisiz Hizmet
          </p>
        </div>

        {/* Scroll indicator */}
        <div className="absolute bottom-10 left-1/2 -translate-x-1/2 animate-bounce text-slate-500">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 5v14M19 12l-7 7-7-7"/></svg>
        </div>
      </section>

      {/* ── Bento Grid Özellikler Bölümü ───────────────────────────────────── */}
      <section className="relative z-10 py-32 px-6">
        <div className="mx-auto max-w-7xl">
          <div className="mb-20 text-center">
            <h2 className="text-3xl font-bold tracking-tight text-white sm:text-5xl">
              Geleceğin Bankacılığı <br className="hidden sm:block" /> Bugün Cebinizde
            </h2>
            <p className="mx-auto mt-6 max-w-2xl text-lg text-slate-400">
              Geleneksel bankaların hantal süreçlerini unutun. Sizin hızınıza ayak uyduran, tamamen kişiselleştirilmiş bir deneyime hazır olun.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 md:grid-rows-2 gap-6 max-w-6xl mx-auto auto-rows-[250px]">
            
            {/* Bento Box 1 - Geniş (AI Finans Asistanı) */}
            <div className="group relative rounded-3xl border border-white/10 bg-slate-900/50 backdrop-blur-xl p-8 md:col-span-2 overflow-hidden transition-all hover:bg-slate-900/80 hover:border-primary-400/50 hover:shadow-[0_0_30px_rgba(85,52,165,0.3)] hover:-translate-y-1 flex flex-col justify-end">
              <div className="absolute top-0 right-0 w-64 h-64 bg-primary-500/20 rounded-full blur-[80px] -mr-20 -mt-20 transition-all group-hover:bg-primary-500/40"></div>
              <div className="relative z-10">
                <div className="mb-4 inline-flex h-12 w-12 items-center justify-center rounded-2xl bg-primary-500/20 text-primary-300 border border-primary-500/30 text-2xl shadow-sm transition-transform group-hover:scale-110">
                  <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 2a10 10 0 1 0 0 20 10 10 0 1 0 0-20zM12 16v-4M12 8h.01"/></svg>
                </div>
                <h3 className="mb-2 text-2xl font-bold text-white">Yapay Zekâ "Fibo"</h3>
                <p className="text-slate-400 leading-relaxed max-w-md">
                  Fibo ile portföyünüzü analiz edin, akıllı harcama uyarıları alın ve piyasa hareketlerini önceden tahmin edin. Size özel finans danışmanınız.
                </p>
              </div>
            </div>

            {/* Bento Box 2 - Dik (Işık Hızında Transfer) */}
            <div className="group relative rounded-3xl border border-white/10 bg-slate-900/50 backdrop-blur-xl p-8 md:row-span-2 overflow-hidden transition-all hover:bg-slate-900/80 hover:border-accent-400/50 hover:shadow-[0_0_30px_rgba(111,223,223,0.2)] hover:-translate-y-1">
              <div className="absolute bottom-0 left-0 w-full h-1/2 bg-gradient-to-t from-accent-500/10 to-transparent transition-all group-hover:from-accent-500/20"></div>
              <div className="relative z-10 flex flex-col h-full">
                <div className="mb-6 inline-flex h-12 w-12 items-center justify-center rounded-2xl bg-accent-500/20 text-accent-300 border border-accent-500/30 text-2xl shadow-sm transition-transform group-hover:scale-110">
                  <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/></svg>
                </div>
                <h3 className="mb-3 text-2xl font-bold text-white">Işık Hızında</h3>
                <p className="text-slate-400 leading-relaxed">
                  Dünyanın her yerine, 7/24 kesintisiz ve anında para gönderin. Beklemek, mesai saatleri veya gizli ücretler yok. Sadece saniyeler var.
                </p>
                <div className="mt-auto pt-6 opacity-30 group-hover:opacity-100 transition-opacity">
                  <div className="h-12 w-full rounded-xl bg-white/5 border border-white/10 flex items-center justify-between px-4">
                    <div className="h-2 w-16 bg-white/20 rounded-full"></div>
                    <div className="h-2 w-8 bg-accent-400 rounded-full shadow-[0_0_10px_rgba(111,223,223,0.8)]"></div>
                  </div>
                </div>
              </div>
            </div>

            {/* Bento Box 3 - Küçük (Güvenlik) */}
            <div className="group relative rounded-3xl border border-white/10 bg-slate-900/50 backdrop-blur-xl p-6 overflow-hidden transition-all hover:bg-slate-900/80 hover:border-brandBlue/50 hover:shadow-[0_0_30px_rgba(75,123,229,0.2)] hover:-translate-y-1 flex flex-col justify-center">
              <div className="relative z-10">
                <div className="mb-3 inline-flex h-10 w-10 items-center justify-center rounded-xl bg-brandBlue/20 text-brandBlue border border-brandBlue/30 text-xl transition-transform group-hover:scale-110">
                  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
                </div>
                <h3 className="mb-2 text-xl font-bold text-white">Askeri Düzey Güvenlik</h3>
                <p className="text-sm text-slate-400 leading-relaxed">
                  Biyometrik doğrulama ve uçtan uca şifreleme.
                </p>
              </div>
            </div>

            {/* Bento Box 4 - Küçük (Portföy) */}
            <div className="group relative rounded-3xl border border-white/10 bg-slate-900/50 backdrop-blur-xl p-6 overflow-hidden transition-all hover:bg-slate-900/80 hover:border-primary-300/50 hover:shadow-[0_0_30px_rgba(168,92,249,0.2)] hover:-translate-y-1 flex flex-col justify-center">
              <div className="relative z-10">
                <div className="mb-3 inline-flex h-10 w-10 items-center justify-center rounded-xl bg-primary-400/20 text-primary-300 border border-primary-400/30 text-xl transition-transform group-hover:scale-110">
                  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M3 3v18h18M18 9l-5 5-4-4-5 5"/></svg>
                </div>
                <h3 className="mb-2 text-xl font-bold text-white">Anlık Portföy Analizi</h3>
                <p className="text-sm text-slate-400 leading-relaxed">
                  Borsalarla entegre, canlı verilerle grafik analizi.
                </p>
              </div>
            </div>

          </div>
        </div>
      </section>

      {/* ── İstatistikler / Sosyal Kanıt ───────────────────────────────────── */}
      <section className="relative overflow-hidden border-y border-white/10 bg-primary-950/20 py-24 text-center sm:py-32">
        <div className="absolute inset-0 bg-gradient-to-r from-primary-900/30 via-slate-950 to-brandBlue/20 pointer-events-none"></div>
        <div className="relative z-10 mx-auto max-w-7xl px-6">
          <div className="grid grid-cols-1 gap-y-16 sm:grid-cols-3 sm:gap-x-8">
            <div className="flex flex-col gap-y-3">
              <dt className="text-base leading-7 text-primary-300">Aktif Kullanıcı</dt>
              <dd className="text-5xl font-extrabold tracking-tight text-white">500B+</dd>
            </div>
            <div className="flex flex-col gap-y-3">
              <dt className="text-base leading-7 text-accent-300">İşlem Hacmi (Aylık)</dt>
              <dd className="text-5xl font-extrabold tracking-tight text-white">₺2.4Mly</dd>
            </div>
            <div className="flex flex-col gap-y-3">
              <dt className="text-base leading-7 text-brandBlue">Müşteri Memnuniyeti</dt>
              <dd className="text-5xl font-extrabold tracking-tight text-white">%99.8</dd>
            </div>
          </div>
        </div>
      </section>

      {/* ── CTA Bölümü ─────────────────────────────────────────────────────── */}
      <section className="relative z-10 py-32 px-6 text-center">
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top,_var(--tw-gradient-stops))] from-primary-900/40 via-slate-950 to-slate-950 pointer-events-none"></div>
        <div className="relative z-10 mx-auto max-w-3xl">
          <h2 className="text-4xl font-black tracking-tight text-white sm:text-5xl">
            Kontrolü Ele Alma Vakti
          </h2>
          <p className="mx-auto mt-6 max-w-xl text-lg leading-8 text-slate-400">
            Hemen ücretsiz hesabınızı oluşturun ve finansal özgürlüğün tadını çıkarmaya başlayın. MoneyFast ile gelecek sizin ellerinizde.
          </p>
          <div className="mt-10 flex flex-col sm:flex-row items-center justify-center gap-4">
            <Link
              to="/login"
              className="w-full sm:w-auto rounded-2xl bg-gradient-to-r from-accent-400 to-brandBlue px-10 py-4 text-base font-semibold text-slate-950 shadow-[0_0_20px_rgba(111,223,223,0.4)] hover:shadow-[0_0_30px_rgba(111,223,223,0.6)] transition-all hover:scale-105"
            >
              Hemen Hesabını Oluştur
            </Link>
          </div>
        </div>
      </section>

      {/* ── Yasal Alt Bilgi ──────────────────────────────────────────────── */}
      <footer className="relative z-10 border-t border-white/10 bg-slate-950/80 backdrop-blur-md py-8 text-center">
        <div className="flex flex-col items-center justify-center gap-6 mb-6">
          <div className="flex items-center gap-10 opacity-80">
            <img src={logo} alt="MoneyFast" className="h-32 sm:h-40 object-contain" />
            <div className="h-12 w-px bg-slate-700"></div>
            <img src={interfiveLogo} alt="InterFive" className="h-32 sm:h-40 object-contain" />
          </div>
        </div>
        <p className="text-sm text-slate-500 font-medium">
          © {new Date().getFullYear()} MoneyFast — InternTech 2026, InterFive Takımı
        </p>
      </footer>

    </div>
  )
}
