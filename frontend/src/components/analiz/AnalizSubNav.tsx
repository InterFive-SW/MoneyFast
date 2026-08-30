import { NavLink } from 'react-router-dom'

const TABS = [
    { to: '/analiz/genel', label: 'Genel Bakış' },
    { to: '/analiz/risk', label: 'Risk' },
    { to: '/analiz/senaryo', label: 'Senaryo & Geçmiş' },
]

/**
 * Analiz ekranının üç bölümü. `MarketsSubNav` ile aynı desen — Piyasalar ve
 * Banka İşlemleri zaten böyle çalışıyor, dördüncü bir sekme dili eklemenin
 * sebebi yok.
 *
 * Bölünme "portföy / risk" değil, SORUYA göre: ne kadarım var ve nasıl gitti,
 * ne kadar risk taşıyorum, değiştirsem ne olur. İlk ikisine göre bölmek
 * kullanıcıyı "max düşüş hangi sekmede" diye düşündürürdü — ikisinde de var.
 */
export default function AnalizSubNav() {
    return (
        <div
            className="mb-6 flex w-fit flex-wrap rounded-lg bg-slate-800/5 p-1 backdrop-blur-sm"
            role="tablist"
            aria-label="Analiz bölümleri"
        >
            {TABS.map((tab) => (
                <NavLink
                    key={tab.to}
                    to={tab.to}
                    className={({ isActive }) =>
                        `rounded-md px-4 py-1.5 text-sm font-semibold transition-all ${
                            isActive
                                ? 'bg-slate-800 text-white shadow-sm'
                                : 'text-slate-400 hover:text-slate-200'
                        }`
                    }
                >
                    {tab.label}
                </NavLink>
            ))}
        </div>
    )
}
