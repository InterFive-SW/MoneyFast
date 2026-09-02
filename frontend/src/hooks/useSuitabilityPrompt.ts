import { useCallback, useEffect, useState } from 'react'
import { apiClient } from '../api/client'

/**
 * "Uygunluk testini doldurun" davetinin durumu.
 *
 * SERT KAPI DEĞİL. Test ilk girişte isteniyor ama uygulamayı kilitlemiyor:
 * kullanıcıyı kendi portföyünden ve ölçümünden mahrum bırakmak, doldurma
 * ihtimalini artırmıyor -- yalnızca ürünü kullanılamaz kılıyor. Bunun yerine
 * üstte kalıcı bir şerit duruyor ve risk ekranı puanın yanında daveti
 * gösteriyor.
 *
 * "Sonra" demek şeridi O OTURUM için kapatıyor, kalıcı olarak değil. Kalıcı
 * kapatma seçeneği, mevzuatın istediği bir testi bir kere reddedip bir daha
 * hiç görmemek demek olurdu; oturum başına saklamak, ısrarı rahatsızlığa
 * çevirmeden koruyor.
 *
 * Mantık burada, bileşende değil: kapsama kapısı `src/hooks/**`'ı sayıyor,
 * JSX'i saymıyor.
 */
export const DISMISS_KEY = 'moneyfast.suitability.dismissed'

export interface SuitabilityPrompt {
    /** Şerit gösterilsin mi. */
    visible: boolean
    /** Test hiç doldurulmamış mı — davetin metnini bu belirliyor. */
    neverTaken: boolean
    /** Doldurulmuşsa hangi sürümle. Eski sürüm de bir davet sebebi. */
    version: string | null
    loading: boolean
    /** Bu oturum için gizle. */
    dismiss: () => void
    /** Test kaydedildikten sonra çağrılır; şerit kalıcı olarak kapanır. */
    markCompleted: () => void
    reload: () => Promise<void>
}

/** Yürürlükteki test sürümü. Bundan eski bir beyanı olan kullanıcı da davet
 *  görüyor: v1 tolerans ölçüyordu, ürün grubu yeterliliğini hiç sormadı. */
export const CURRENT_VERSION = 'v2'

function isDismissed(): boolean {
    try {
        return sessionStorage.getItem(DISMISS_KEY) === '1'
    } catch {
        // Erişilemeyen depolama, daveti göstermemek için bir sebep değil.
        return false
    }
}

export function useSuitabilityPrompt(): SuitabilityPrompt {
    const [version, setVersion] = useState<string | null>(null)
    const [neverTaken, setNeverTaken] = useState(false)
    const [loading, setLoading] = useState(true)
    const [dismissed, setDismissed] = useState(isDismissed)
    const [completed, setCompleted] = useState(false)

    const load = useCallback(async () => {
        setLoading(true)
        try {
            const profile = await apiClient.getRiskProfile('1Y')
            const declared = profile?.declared ?? null
            setNeverTaken(declared === null)
            setVersion(declared?.questionnaire_version ?? null)
        } catch {
            // Profil çekilemediyse davet GÖSTERİLMİYOR. Testi doldurmuş
            // birine "doldurun" demek, sistemin onu unuttuğunu düşündürür ve
            // bir kesintiyi kullanıcının görevi gibi gösterir.
            setNeverTaken(false)
            setVersion(null)
        } finally {
            setLoading(false)
        }
    }, [])

    useEffect(() => {
        void load()
    }, [load])

    const dismiss = useCallback(() => {
        setDismissed(true)
        try {
            sessionStorage.setItem(DISMISS_KEY, '1')
        } catch {
            // Yazılamazsa da bu oturumda gizli kalıyor: durum bellekte.
        }
    }, [])

    const markCompleted = useCallback(() => setCompleted(true), [])

    const outdated = version !== null && version !== CURRENT_VERSION

    return {
        visible: !loading && !dismissed && !completed && (neverTaken || outdated),
        neverTaken,
        version,
        loading,
        dismiss,
        markCompleted,
        reload: load,
    }
}
