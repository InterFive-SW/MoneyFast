import DengelemePaneli from '../../components/analiz/DengelemePaneli'
import SablonSecici from '../../components/analiz/SablonSecici'

/**
 * Analiz > Dengeleme — hedefimden ne kadar saptım, karşılığı kaç lot.
 *
 * İki parça: üstte hedef formu (şablonlar başlangıç değerini veriyor), altta
 * sapmanın emir karşılığı. Hesap yok, koşul yok: mantığın tamamı hook'larda,
 * çünkü kapsama kapısı `src/hooks/**` altını sayıyor ve JSX'i saymıyor.
 */
export default function Dengeleme() {
    return (
        <div className="flex flex-col gap-6">
            <SablonSecici />
            <DengelemePaneli />
        </div>
    )
}
