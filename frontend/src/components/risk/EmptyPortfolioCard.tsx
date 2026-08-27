import { Link } from 'react-router-dom'

/**
 * Pozisyonu olmayan kullanıcının gördüğü ekran.
 *
 * Eskiden tek bir cümleydi: "Portföyünüzde değerlenebilir pozisyon bulunmadığı
 * için risk ölçütleri hesaplanamadı." Doğru ama çıkmaz sokak — kullanıcı ne
 * yapması gerektiğini de, buranın ne işe yaradığını da öğrenmiyordu.
 *
 * Yerine sayfanın ne göstereceğini anlatan ve Piyasalar'a yönlendiren bir
 * kart. Yeni bir hesabın ilk gördüğü ekran, ürünü öğrendiği yerdir.
 */
const WHAT_YOU_GET = [
    {
        title: 'Ne kadar dalgalandığınız',
        body: 'Portföyünüzün değeri bir yıl içinde tipik olarak ne kadar oynuyor.',
    },
    {
        title: 'En derin düşüşünüz',
        body: 'Zirveden dibe en büyük kayıp, tarihleriyle ve toparlanma süresiyle.',
    },
    {
        title: 'Değerin nereye yığıldığı',
        body: 'Kaç isme, hangi sektörlere ve hangi para birimlerine dağıldığı.',
    },
]

export default function EmptyPortfolioCard() {
    return (
        <div className="rounded-2xl border border-white/10 bg-slate-900/50 p-6 shadow-2xl backdrop-blur-xl">
            <h3 className="text-base font-semibold text-white">
                Risk ölçümü için önce bir portföy gerekiyor
            </h3>
            <p className="mt-2 text-sm leading-relaxed text-slate-400">
                Buradaki her sayı gerçek fiyat geçmişinden hesaplanıyor, dolayısıyla
                ölçülecek bir pozisyon olmadan gösterilecek bir şey de yok. İlk
                yatırımınızı yaptığınızda bu sayfa şunları gösterecek:
            </p>

            <ul className="mt-4 flex flex-col gap-3">
                {WHAT_YOU_GET.map((item) => (
                    <li key={item.title} className="flex gap-3">
                        <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-brandBlue" />
                        <span>
                            <span className="block text-sm font-medium text-slate-200">
                                {item.title}
                            </span>
                            <span className="block text-xs leading-relaxed text-slate-500">
                                {item.body}
                            </span>
                        </span>
                    </li>
                ))}
            </ul>

            <div className="mt-5 flex flex-wrap gap-3">
                <Link
                    to="/investment/hisseler"
                    className="rounded-lg bg-brandBlue px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-600"
                >
                    Piyasalara göz at
                </Link>
                <Link
                    to="/chat"
                    className="rounded-lg border border-white/10 px-4 py-2 text-sm font-medium text-slate-300 transition-colors hover:bg-white/5"
                >
                    Asistana sor
                </Link>
            </div>
        </div>
    )
}
