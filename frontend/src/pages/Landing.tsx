/**
 * Landing — MoneyFast Koyu Tema Giriş Sayfası (Poppins, Fixes)
 */

import { useState, useEffect, useRef } from 'react'
import { Link } from 'react-router-dom'
import logo from '../assets/logo.png'
import interfiveLogo from '../assets/interfive.png'
import logoIcon from '../assets/logo-icon.png'

// ═══════════════════════════════════════════════════════════════════
// HOOKS
// ═══════════════════════════════════════════════════════════════════

function useTextRevealProgress(ref: React.RefObject<HTMLElement | null>) {
  const [progress, setProgress] = useState(0)

  useEffect(() => {
    const onScroll = () => {
      if (!ref.current) return
      const rect = ref.current.getBoundingClientRect()
      const windowHeight = window.innerHeight
      const start = windowHeight * 0.8
      const end = windowHeight * 0.3
      const raw = (start - rect.top) / (start - end)
      setProgress(Math.max(0, Math.min(1, raw)))
    }
    window.addEventListener('scroll', onScroll, { passive: true })
    onScroll()
    return () => window.removeEventListener('scroll', onScroll)
  }, [ref])

  return progress
}

function useTimelineProgress(ref: React.RefObject<HTMLElement | null>) {
  const [progress, setProgress] = useState(0)

  useEffect(() => {
    const onScroll = () => {
      if (!ref.current) return
      const rect = ref.current.getBoundingClientRect()
      const windowHeight = window.innerHeight
      const startTrigger = windowHeight / 2
      const raw = (startTrigger - rect.top) / (rect.height * 0.8) 
      setProgress(Math.max(0, Math.min(1, raw)))
    }
    window.addEventListener('scroll', onScroll, { passive: true })
    onScroll()
    return () => window.removeEventListener('scroll', onScroll)
  }, [ref])

  return progress
}

function useInView(threshold = 0.15) {
  const ref = useRef<HTMLDivElement>(null)
  const [isVisible, setVisible] = useState(false)

  useEffect(() => {
    const el = ref.current
    if (!el) return
    const obs = new IntersectionObserver(
      ([entry]) => { if (entry.isIntersecting) setVisible(true) },
      { threshold }
    )
    obs.observe(el)
    return () => obs.disconnect()
  }, [threshold])

  return { ref, isVisible }
}

// ═══════════════════════════════════════════════════════════════════
// DATA
// ═══════════════════════════════════════════════════════════════════

const WHY_CHOOSE_US = [
  {
    icon: <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 2l3 6 6 3-6 3-3 6-3-6-6-3 6-3 3-6z"/></svg>,
    title: 'Fibo AI Asistanı',
    desc: 'Risk profilinize göre kişiye özel hisseleri filtreler, karmaşık verileri derler ve stratejinize uygun al-sat işlemlerini tasarlar.',
    colorClass: 'text-emerald-300',
  },
  {
    icon: <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M2 12h4l3-9 5 18 3-9h5"/></svg>,
    title: 'Anlık Haber & Piyasa Yorumu',
    desc: 'Küresel finans haberlerini saniyeler içinde çeker, yapay zeka ile analiz edip portföyünüze olası etkilerini yorumlayarak sizi uyarır.',
    colorClass: 'text-amber-200',
  },
  {
    icon: <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="3" y="3" width="7" height="7" rx="1" /><rect x="14" y="3" width="7" height="7" rx="1" /><rect x="14" y="14" width="7" height="7" rx="1" /><rect x="3" y="14" width="7" height="7" rx="1" /></svg>,
    title: 'Kullanıcı Dostu Dashboard',
    desc: 'Gelişmiş modüler yapı sayesinde banka hesapları, portföyler ve haber akışları tek ekranda, son derece anlaşılır ve karmaşadan uzak sunulur.',
    colorClass: 'text-rose-300',
  },
  {
    icon: <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" /></svg>,
    title: 'Risk ve Bütçe Takibi',
    desc: 'Yatırımlarınızdaki volatiliteyi ölçerken aynı zamanda günlük harcamalarınızı kategorize ederek bütçe sapmalarına karşı sizi uyarır.',
    colorClass: 'text-pink-300',
  },
  {
    icon: <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="2" y="5" width="20" height="14" rx="2"/><path d="M2 10h20"/></svg>,
    title: 'Tüm Bankalar Tek Çatıda',
    desc: 'Farklı bankalardaki vadesiz hesaplarınızı ve kredi kartlarınızı MoneyFast\'e bağlayıp, net varlık durumunuzu anlık olarak tek panelden yönetin.',
    colorClass: 'text-purple-300',
  },
  {
    icon: <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/></svg>,
    title: 'Akıllı Alarm Sistemi',
    desc: 'Sadece fiyatlara değil; doğrudan spesifik hisse haberlerine, piyasa trendlerine veya kur değişimlerine kişiselleştirilmiş alarmlar kurun.',
    colorClass: 'text-sky-300',
  },
]

const HOW_WE_WORK_STEPS = [
  {
    num: '01',
    title: 'Hesap & Profil Oluşturma',
    desc: 'Saniyeler içinde MoneyFast hesabınızı açın. Finansal hedeflerinizi ve risk toleransınızı belirleyerek size özel deneyimi başlatın.',
    icon: <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>,
  },
  {
    num: '02',
    title: 'Yapay Zeka Destekli Analiz',
    desc: 'Fibo, mevcut bütçenizi ve finansal geçmişinizi tarayarak, piyasa verileri ışığında size en uygun tasarruf ve yatırım stratejisini çizer.',
    icon: <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="11" cy="11" r="8" /><line x1="21" y1="21" x2="16.65" y2="16.65" /></svg>,
  },
  {
    num: '03',
    title: 'Portföy Yönetimi',
    desc: 'Akıllı önerilerle hisse senetlerinizi veya döviz yatırımlarınızı şekillendirin, nakit akışınızı kolayca takip edin.',
    icon: <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="2" y="7" width="20" height="14" rx="2" ry="2"/><path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16"/></svg>,
  },
  {
    num: '04',
    title: 'Sürekli Büyüme & Takip',
    desc: 'Gerçek zamanlı piyasa haberleri ve anlık bildirimlerle finansal hedeflerinize doğru emin adımlarla ilerleyin.',
    icon: <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="22 7 13.5 15.5 8.5 10.5 2 17"/><polyline points="16 7 22 7 22 13"/></svg>,
  },
]

// ═══════════════════════════════════════════════════════════════════
// SUB-COMPONENTS
// ═══════════════════════════════════════════════════════════════════

function SectionBadge({ num, label }: { num: string; label: string }) {
  return (
    <div className="mb-8 inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-4 py-1.5 text-xs font-semibold tracking-wider uppercase shadow-sm">
      <span className="text-[#D4C5A9] font-bold">{num}</span> 
      <span className="h-1.5 w-1.5 rounded-full bg-slate-400" /> 
      <span className="text-[#D4C5A9] font-bold">{label}</span>
    </div>
  )
}

function CoinVideo() {
  const videoRef = useRef<HTMLVideoElement>(null)
  const [isPlaying, setIsPlaying] = useState(false)

  const handleMouseEnter = () => {
    if (videoRef.current) {
      videoRef.current.currentTime = 0
      videoRef.current.play()
      setIsPlaying(true)
    }
  }

  const handleEnded = () => {
    setIsPlaying(false)
  }

  return (
    <div 
      className="relative w-full max-w-[450px] aspect-square mx-auto bg-black overflow-hidden group cursor-pointer flex items-center justify-center rounded-3xl"
      onMouseEnter={handleMouseEnter}
    >
      <video
        ref={videoRef}
        muted
        playsInline
        onEnded={handleEnded}
        className="w-full h-full object-cover transition-transform duration-700 rounded-3xl "
        src="/coin.mp4" 
      />
      
      {/* Fallback & Indicator overlay - Gri arkaplan kaldırıldı, sadece tamamen saydam, üzerine gelince kaybolan incecik bir text var */}
      <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none text-white/10 text-xs transition-opacity duration-300 group-hover:opacity-0">
        <span className="text-center px-4 tracking-widest font-light">

        </span>
      </div>
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════
// SECTIONS
// ═══════════════════════════════════════════════════════════════════

function HeroSection() {
  return (
    <section className="relative z-10 min-h-screen flex items-center">
      {/* ─── VİDEO ARKASI KESİN KORUMA (Merkezi tamamen siyah, dışa doğru eriyen devasa kalkan) ─── */}
      <div className="absolute top-1/2 left-[20%] -translate-x-1/2 -translate-y-1/2 w-[1200px] h-[1200px] bg-[radial-gradient(circle_at_center,rgba(0,0,0,1)_35%,rgba(0,0,0,0)_70%)] pointer-events-none z-0" />

      {/* ─── SAĞ KENARDAN GELEN HOLOGRAM (Parlaklık ve göz yorma azaltıldı) ─── */}
      <div className="absolute top-0 right-0 w-[50%] h-full pointer-events-none z-0">
        <div className="absolute top-[10%] right-[-25%] w-[1000px] h-[1000px] bg-[radial-gradient(circle_at_center,rgba(139,92,246,0.12)_0%,rgba(0,0,0,0)_60%)] rounded-full blur-[120px]" />
        <div className="absolute top-[60%] right-[-15%] w-[800px] h-[800px] bg-[radial-gradient(circle_at_center,rgba(56,189,248,0.10)_0%,rgba(0,0,0,0)_60%)] rounded-full blur-[120px]" />
      </div>

      {/* ─── ÜST MENÜ ─── */}
      <nav className="absolute top-0 inset-x-0 z-50 flex items-center justify-between p-6 sm:p-10 text-xs font-semibold tracking-widest uppercase text-slate-400">
        <div className="flex gap-8 sm:gap-12 pl-2 sm:pl-8">
          <a href="#who-we-are" className="hover:text-white transition-colors">Hikayemiz</a>
          <a href="#faq" className="hover:text-white transition-colors">SSS</a>
          <a href="#contact" className="hover:text-white transition-colors">İletişim</a>
        </div>
        <div className="flex items-center gap-8 pr-2 sm:pr-8">
          <Link to="/login" className="hover:text-white transition-colors hidden sm:block">
            Giriş Yap
          </Link>
          <Link
            to="/register"
            className="bg-[#D4C5A9] text-black px-6 py-3 font-bold tracking-widest hover:bg-white transition-colors rounded-sm"
          >
            HESAP AÇ
          </Link>
        </div>
      </nav>

      <div className="w-full max-w-[1400px] mx-auto px-6 pt-32 pb-16 grid grid-cols-1 lg:grid-cols-2 gap-12 items-center">
        {/* Sol Taraf: Coin Videosu */}
        <div className="order-2 lg:order-1 flex justify-center lg:justify-start lg:pl-10">
          <CoinVideo />
        </div>

        {/* Sağ Taraf: Temiz ve Vurucu Logo + Slogan */}
        <div className="order-1 lg:order-2 flex flex-col items-center lg:items-start text-center lg:text-left pr-4 mt-8 lg:mt-0">
          
          <div className="flex items-center gap-5 sm:gap-6 mb-8">
            <img src={logoIcon} alt="MF" className="h-16 sm:h-[5.5rem] object-contain drop-shadow-lg" />
            <h1 className="text-5xl sm:text-[5rem] font-bold tracking-tight text-gradient-hero">
              MoneyFast
            </h1>
          </div>

          <p className="text-xl sm:text-2xl lg:text-3xl font-medium text-white max-w-lg leading-snug">
            Geleceği dileme, biz senin için gerçekleştiriyoruz.
          </p>

        </div>
      </div>
    </section>
  )
}

function LogoStrip() {
  return (
    <section className="relative z-10 border-y border-white/5 py-12 overflow-hidden">
      <div className="flex flex-col sm:flex-row items-center justify-center gap-16 sm:gap-32 opacity-70 transition-all duration-700 hover:opacity-100">
        <img src={logo} alt="MoneyFast" className="h-16 sm:h-24 object-contain" />
        <img src={interfiveLogo} alt="InterFive" className="h-16 sm:h-24 object-contain" />
      </div>
    </section>
  )
}

function WhoWeAreSection() {
  const sectionRef = useRef<HTMLDivElement>(null)
  const progress = useTextRevealProgress(sectionRef)

  const text = 'MoneyFast, bireysel ve kurumsal kullanıcılar için tasarlanmış yeni nesil dijital finans platformudur. Yapay zeka destekli araçlarımızla bankacılık, yatırım ve portföy yönetimini tek bir çatı altında birleştiriyoruz. Hedefimiz, finansal özgürlüğü herkes için erişilebilir kılmaktır.'
  const words = text.split(' ')

  return (
    <section id="who-we-are" ref={sectionRef} className="relative z-10 py-32 sm:py-48 px-6">
      <div className="mx-auto max-w-4xl text-center">
        <SectionBadge num="001" label="BİZ KİMİZ" />
        <p className="text-2xl md:text-3xl lg:text-4xl font-medium leading-relaxed tracking-tight">
          {words.map((word, i) => {
            const threshold = (i / words.length) * 0.7 + 0.1
            const isRevealed = progress > threshold
            return (
              <span
                key={i}
                className={`inline transition-colors duration-500 ${isRevealed ? 'text-white' : 'text-white/20'}`}
              >
                {word}{' '}
              </span>
            )
          })}
        </p>
      </div>
    </section>
  )
}

function WhyChooseUsSection() {
  const { ref, isVisible } = useInView(0.1)

  return (
    <section ref={ref} className="relative z-10 py-24 sm:py-32 px-6">
      <div className="mx-auto max-w-6xl">
        <div className="text-center mb-24">
          <SectionBadge num="002" label="NEDEN BİZ?" />
          <h2 className="text-4xl sm:text-[3.5rem] font-bold tracking-tight text-white mb-6">Neden MoneyFast?</h2>
          <p className="max-w-2xl mx-auto text-base text-slate-400 font-medium">
            Manuel finansal takip süreçlerini ortadan kaldırıyor, yapay zeka ile yatırımlarınızı daha kârlı ve güvenilir hale getiriyoruz.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
          {WHY_CHOOSE_US.map((item, i) => (
            <div
              key={i}
              className={`group flex flex-col items-center text-center px-8 py-12 rounded-[2.5rem] bg-white/5 border border-white/5 transition-all duration-700 hover:bg-white/10 hover:border-white/10 ${isVisible ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-12'}`}
              style={{ transitionDelay: `${i * 150}ms` }}
            >
              <div className="relative mb-12 flex flex-col items-center">
                <div className="w-[140px] h-[140px] rounded-[2.5rem] bg-white/5 border border-white/10 flex items-center justify-center text-white/70 shadow-2xl transition-all duration-500 group-hover:scale-105 group-hover:text-white group-hover:bg-gradient-to-b group-hover:from-white/15 group-hover:to-transparent">
                  {item.icon}
                </div>
                <div className="absolute -bottom-4 flex items-center justify-center px-4 py-1.5 rounded-full bg-[#111] border border-white/10 text-sm font-semibold text-white/90 backdrop-blur-md shadow-lg">
                  <span className="text-white font-bold">0{i + 1}</span>
                </div>
              </div>

              <h3 className={`text-lg font-bold mb-4 px-4 ${item.colorClass}`}>{item.title}</h3>
              <p className="text-slate-400 font-medium leading-relaxed text-sm px-2">{item.desc}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

function HowWeWorkSection() {
  const containerRef = useRef<HTMLDivElement>(null)
  const progress = useTimelineProgress(containerRef)

  return (
    <section id="how-we-work" className="relative z-10 py-24 sm:py-32 px-6">
      <div className="mx-auto max-w-5xl">
        <div className="text-center mb-32">
          <SectionBadge num="003" label="SÜREÇ" />
          <h2 className="text-4xl sm:text-[3.5rem] font-bold tracking-tight text-white mb-6">Nasıl Çalışır?</h2>
          <p className="max-w-2xl mx-auto text-base text-slate-400 font-medium">
            Sadece birkaç adımda finansal profilinizi oluşturun ve yönetimi Fibo'nun güçlü altyapısına bırakın.
          </p>
        </div>

        <div className="relative" ref={containerRef}>
          <div className="timeline-track hidden md:block" />
          
          <div
            className="timeline-progress hidden md:block transition-all duration-100 ease-out"
            style={{ height: `${progress * 100}%` }}
          />

          <div className="space-y-16">
            {HOW_WE_WORK_STEPS.map((step, i) => {
              const stepThreshold = i * 0.25
              const isActive = progress >= stepThreshold
              const isLeft = i % 2 === 0

              return (
                <div key={i} className="relative flex flex-col md:flex-row items-center gap-8 md:gap-16">
                  
                  <div className={`md:w-[45%] flex justify-end ${isLeft ? '' : 'order-2 md:order-1'}`}>
                    {isLeft ? (
                      <div className={`w-full p-8 rounded-3xl transition-all duration-700 flex items-center gap-6 ${isActive ? 'bg-white/5 border border-white/10' : 'bg-transparent border border-transparent opacity-40'}`}>
                        <div className={`shrink-0 w-16 h-16 rounded-2xl flex items-center justify-center transition-all duration-500 ${isActive ? 'bg-white/10 text-white shadow-xl scale-110' : 'bg-white/5 text-white/50'}`}>
                          {step.icon}
                        </div>
                        <div className="text-left">
                          <div className="text-xs font-semibold text-slate-500 mb-1">{step.num}</div>
                          <h3 className="text-base font-semibold text-white mb-1">{step.title}</h3>
                          <p className="text-sm text-slate-400 font-medium leading-relaxed">{step.desc}</p>
                        </div>
                      </div>
                    ) : null}
                  </div>

                  <div className={`hidden md:flex items-center justify-center z-10 ${!isLeft && 'order-2'}`}>
                    <div className={`flex items-center justify-center w-8 h-8 rounded-full transition-all duration-500 ${isActive ? 'bg-gradient-to-tr from-[#FDE68A] via-[#F472B6] to-[#60A5FA] p-[2px]' : 'border-2 border-white/10 bg-black'}`}>
                      {isActive && <div className="w-full h-full bg-black rounded-full border border-black/50" />}
                    </div>
                  </div>

                  <div className={`md:w-[45%] flex justify-start ${!isLeft ? 'order-3' : 'order-3'}`}>
                    {!isLeft ? (
                      <div className={`w-full p-8 rounded-3xl transition-all duration-700 flex items-center gap-6 ${isActive ? 'bg-white/5 border border-white/10' : 'bg-transparent border border-transparent opacity-40'}`}>
                        <div className={`shrink-0 w-16 h-16 rounded-2xl flex items-center justify-center transition-all duration-500 ${isActive ? 'bg-white/10 text-white shadow-xl scale-110' : 'bg-white/5 text-white/50'}`}>
                          {step.icon}
                        </div>
                        <div className="text-left">
                          <div className="text-xs font-semibold text-slate-500 mb-1">{step.num}</div>
                          <h3 className="text-base font-semibold text-white mb-1">{step.title}</h3>
                          <p className="text-sm text-slate-400 font-medium leading-relaxed">{step.desc}</p>
                        </div>
                      </div>
                    ) : null}
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      </div>
    </section>
  )
}

function FooterSection() {
  return (
    <footer className="relative z-10 border-t border-white/5 pt-20 pb-12 text-center px-6 mt-12">
      <div className="flex flex-col items-center justify-center gap-6 mb-12">
        <div className="flex items-center gap-16 sm:gap-32 opacity-70 transition-all duration-700 hover:opacity-100">
          <img src={logo} alt="MoneyFast" className="h-16 sm:h-24 object-contain" />
          <div className="h-10 w-px bg-white/20" />
          <img src={interfiveLogo} alt="InterFive" className="h-16 sm:h-24 object-contain" />
        </div>
      </div>
      <p className="text-sm text-slate-600 font-medium tracking-wide">
        © Copyright 2025 | Design & Developed By InterFive - License | Powered By InterTech
      </p>
    </footer>
  )
}

// ═══════════════════════════════════════════════════════════════════
// MAIN LANDING COMPONENT
// ═══════════════════════════════════════════════════════════════════

export default function Landing() {
  return (
    <div className="antialiased bg-hologram-global min-h-screen text-slate-300 overflow-x-hidden">
      <HeroSection />
      <LogoStrip />
      <WhoWeAreSection />
      <WhyChooseUsSection />
      <HowWeWorkSection />
      <FooterSection />
    </div>
  )
}
