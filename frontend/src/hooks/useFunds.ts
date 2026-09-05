import { useEffect, useState } from 'react'
import { apiClient } from '../api/client'
import type { ApiFund } from '../api/client'

/**
 * TEFAS fon listesi.
 *
 * `Fonlar` ekranı `MOCK_FUNDS` üzerinden çiziliyordu. Bu hook onun arkasına
 * gerçek veriyi koyuyor.
 *
 * **Süzgeçler sunucuya gidiyor.** Evren 2.602 fon; hepsini çekip tarayıcıda
 * süzmek her açılışta birkaç yüz kilobayt ve süzgeç mantığının ikinci bir
 * kopyası demekti. Açılır listelerin içeriği de sunucudan geliyor: elle
 * yazılmış bir kurucu listesi, TEFAS yeni bir kurucu eklediğinde sessizce
 * eksik kalırdı.
 */

export const FUNDS_ERROR = 'Fon listesi yüklenemedi.'

export interface FundFilters {
    founder?: string
    umbrella?: string
    fundType?: string
    q?: string
}

export interface FundsData {
    funds: ApiFund[]
    founders: string[]
    umbrellas: string[]
    loading: boolean
    error: string | null
    /** Hic fon yazilmamis mi -- bos bir suzgec sonucundan AYRI. */
    empty: boolean
}

/** Suzgecleri kararli bir anahtara indirger.
 *
 *  Suzgec nesnesi her render'da yeni bir referans; bagimliligi degerlerin
 *  kendisine baglamak, ayni suzgecle sonsuz istek atmayi onluyor. */
function filterKey(filters: FundFilters): string {
    return JSON.stringify([
        filters.founder ?? '', filters.umbrella ?? '',
        filters.fundType ?? '', filters.q ?? '',
    ])
}

export function useFunds(filters: FundFilters = {}): FundsData {
    const [funds, setFunds] = useState<ApiFund[]>([])
    const [founders, setFounders] = useState<string[]>([])
    const [umbrellas, setUmbrellas] = useState<string[]>([])
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState<string | null>(null)

    const key = filterKey(filters)

    useEffect(() => {
        let cancelled = false
        setLoading(true)
        setError(null)
        const [founder, umbrella, fundType, q] = JSON.parse(key) as string[]
        apiClient
            .getFunds({
                founder: founder || undefined,
                umbrella: umbrella || undefined,
                fundType: fundType || undefined,
                q: q || undefined,
            })
            .then((response) => {
                if (cancelled) return
                setFunds(response.items ?? [])
                // Acilir listeler yalnizca doluyken guncelleniyor: suzulmus
                // bir sorgu daralmis bir kurucu listesi dondururse, kullanici
                // sectigi suzgeci geri alamaz hale gelirdi.
                if (response.founders?.length) setFounders(response.founders)
                if (response.umbrellas?.length) setUmbrellas(response.umbrellas)
            })
            .catch(() => {
                if (cancelled) return
                // Ulasilamayan uc ile bos liste AYRI: biri "fon yok" diyor,
                // digeri hicbir sey demiyor.
                setError(FUNDS_ERROR)
                setFunds([])
            })
            .finally(() => {
                if (!cancelled) setLoading(false)
            })
        return () => {
            cancelled = true
        }
    }, [key])

    return {
        funds,
        founders,
        umbrellas,
        loading,
        error,
        // Suzgec YOKKEN bos donen liste, henuz hic fon yazilmadigi anlamina
        // geliyor; suzgecliyken bos donen liste "bu suzgece uyan fon yok".
        empty: !loading && !error && funds.length === 0 && key === filterKey({}),
    }
}
