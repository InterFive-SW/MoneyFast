import DengelemePaneli from '../../components/analiz/DengelemePaneli'
import HedefDagilimPaneli from '../../components/risk/HedefDagilimPaneli'

/**
 * Analiz > Dengeleme — hedefimden ne kadar saptım, karşılığı kaç lot ve neden.
 *
 * **Şablon seçici kaldırıldı.** Hedef artık bir addan değil, iki ölçümden
 * çıkıyor: kullanıcının kendi girdiği dağılım, ya da o yoksa ölçülen risk ile
 * ankette beyan ettiği toleransın daha temkinli olanı. Kullanıcının bir
 * "Dengeli" adı seçmesi, o iki ölçümün söylediğinden bağımsız bir üçüncü
 * girdi olurdu.
 *
 * Kullanıcının KENDİ hedefi hâlâ kazanıyor ve hâlâ buradan giriliyor: sistem
 * hedefi ancak kullanıcı hiç koymadıysa banttan okuyor.
 *
 * Hesap yok, koşul yok: mantığın tamamı hook'larda, çünkü kapsama kapısı
 * `src/hooks/**` altını sayıyor ve JSX'i saymıyor.
 */
export default function Dengeleme() {
    return (
        <div className="flex flex-col gap-6">
            <HedefDagilimPaneli />
            <DengelemePaneli />
        </div>
    )
}
