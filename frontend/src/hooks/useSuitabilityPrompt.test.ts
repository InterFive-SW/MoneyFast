/**
 * Uygunluk testi davetinin durumu.
 *
 * Korunan asıl karar: bu bir SERT KAPI DEĞİL. Testi bir route guard'ın
 * arkasına koymak, kullanıcıyı kendi portföyünden ve ölçümünden mahrum
 * bırakırdı — bu, doldurma ihtimalini artırmıyor, yalnızca ürünü
 * kullanılamaz kılıyor.
 *
 * İkinci karar: "Sonra" demek daveti O OTURUM için kapatıyor, kalıcı olarak
 * değil. Kalıcı kapatma, mevzuatın istediği bir testi bir kere reddedip bir
 * daha hiç görmemek demek olurdu.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { renderHook, waitFor, act } from '@testing-library/react'
import {
    CURRENT_VERSION, DISMISS_KEY, useSuitabilityPrompt,
} from './useSuitabilityPrompt'
import { apiClient } from '../api/client'

const declared = (version: string) => ({
    tolerance_level: 'Orta', investment_horizon: '3-5 yıl',
    assessed_at: '2026-09-01T10:00:00Z', questionnaire_version: version,
})

function profile(value: unknown) {
    vi.spyOn(apiClient, 'getRiskProfile').mockResolvedValue({ declared: value } as never)
}

beforeEach(() => {
    sessionStorage.clear()
    profile(null)
})
afterEach(() => vi.restoreAllMocks())

describe('useSuitabilityPrompt', () => {
    it('test hiç doldurulmadıysa davet görünür', async () => {
        const { result } = renderHook(() => useSuitabilityPrompt())
        await waitFor(() => expect(result.current.loading).toBe(false))
        expect(result.current.visible).toBe(true)
        expect(result.current.neverTaken).toBe(true)
    })

    it('yürürlükteki sürümle doldurulmuşsa davet görünmez', async () => {
        profile(declared(CURRENT_VERSION))
        const { result } = renderHook(() => useSuitabilityPrompt())
        await waitFor(() => expect(result.current.loading).toBe(false))
        expect(result.current.visible).toBe(false)
        expect(result.current.version).toBe(CURRENT_VERSION)
    })

    it('eski sürümle doldurulmuşsa davet yine görünür', async () => {
        // v1 tolerans ölçüyordu, ürün grubu yeterliliğini hiç sormadı.
        profile(declared('v1'))
        const { result } = renderHook(() => useSuitabilityPrompt())
        await waitFor(() => expect(result.current.loading).toBe(false))
        expect(result.current.visible).toBe(true)
        expect(result.current.neverTaken).toBe(false)
    })

    it('yüklenirken davet gösterilmez', () => {
        const { result } = renderHook(() => useSuitabilityPrompt())
        expect(result.current.loading).toBe(true)
        expect(result.current.visible).toBe(false)
    })

    it('profil çekilemezse davet gösterilmez', async () => {
        // Testi doldurmuş birine "doldurun" demek, sistemin onu unuttuğunu
        // düşündürür ve bir kesintiyi kullanıcının görevi gibi gösterir.
        vi.spyOn(apiClient, 'getRiskProfile').mockRejectedValue(new Error('500'))
        const { result } = renderHook(() => useSuitabilityPrompt())
        await waitFor(() => expect(result.current.loading).toBe(false))
        expect(result.current.visible).toBe(false)
    })

    it('gövde beyan alanı taşımıyorsa doldurulmamış sayılır', async () => {
        vi.spyOn(apiClient, 'getRiskProfile').mockResolvedValue({} as never)
        const { result } = renderHook(() => useSuitabilityPrompt())
        await waitFor(() => expect(result.current.loading).toBe(false))
        expect(result.current.neverTaken).toBe(true)
    })

    it('"Sonra" daveti bu oturum için kapatır', async () => {
        const { result } = renderHook(() => useSuitabilityPrompt())
        await waitFor(() => expect(result.current.loading).toBe(false))
        await act(async () => { result.current.dismiss() })
        expect(result.current.visible).toBe(false)
        expect(sessionStorage.getItem(DISMISS_KEY)).toBe('1')
    })

    it('kapatma oturum boyunca hatırlanır', async () => {
        sessionStorage.setItem(DISMISS_KEY, '1')
        const { result } = renderHook(() => useSuitabilityPrompt())
        await waitFor(() => expect(result.current.loading).toBe(false))
        expect(result.current.visible).toBe(false)
    })

    it('depolama yazılamıyorsa da bu oturumda gizli kalır', async () => {
        const setItem = vi.spyOn(Storage.prototype, 'setItem')
            .mockImplementation(() => { throw new Error('gizli sekme') })
        const { result } = renderHook(() => useSuitabilityPrompt())
        await waitFor(() => expect(result.current.loading).toBe(false))
        await act(async () => { result.current.dismiss() })
        expect(result.current.visible).toBe(false)
        setItem.mockRestore()
    })

    it('depolama okunamıyorsa davet yine gösterilir', async () => {
        // Erişilemeyen depolama, daveti göstermemek için bir sebep değil.
        const getItem = vi.spyOn(Storage.prototype, 'getItem')
            .mockImplementation(() => { throw new Error('erişim yok') })
        const { result } = renderHook(() => useSuitabilityPrompt())
        await waitFor(() => expect(result.current.loading).toBe(false))
        expect(result.current.visible).toBe(true)
        getItem.mockRestore()
    })

    it('test tamamlanınca davet kalıcı olarak kapanır', async () => {
        const { result } = renderHook(() => useSuitabilityPrompt())
        await waitFor(() => expect(result.current.loading).toBe(false))
        await act(async () => { result.current.markCompleted() })
        expect(result.current.visible).toBe(false)
    })

    it('yeniden yükleme profili tekrar okur', async () => {
        const read = vi.spyOn(apiClient, 'getRiskProfile')
            .mockResolvedValue({ declared: null } as never)
        const { result } = renderHook(() => useSuitabilityPrompt())
        await waitFor(() => expect(result.current.loading).toBe(false))
        await act(async () => { await result.current.reload() })
        expect(read).toHaveBeenCalledTimes(2)
    })
})
