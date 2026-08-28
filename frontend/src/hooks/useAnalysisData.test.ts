/**
 * Analiz ekranının paylaşılan veri katmanı.
 *
 * Korunan iki özellik: iki uç AYNI dönemi alır (yoksa kullanıcı 3 aya
 * geçtiğinde metrikler değişir, yanındaki grafik bir yılı göstermeye devam
 * eder), ve biri düşerse diğeri gösterilmeye devam eder.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, renderHook, waitFor } from '@testing-library/react'
import { ANALYSIS_ERROR, useAnalysisData } from './useAnalysisData'
import { apiClient } from '../api/client'

const ANALYSIS = { total_value: 55000, base_currency: 'TRY' }
const RISK = { score: 83.4, level: 'Düşük', position_count: 14 }

beforeEach(() => {
    vi.spyOn(apiClient, 'getPortfolioAnalysis').mockResolvedValue(ANALYSIS as never)
    vi.spyOn(apiClient, 'getRiskProfile').mockResolvedValue(RISK as never)
})
afterEach(() => vi.restoreAllMocks())

describe('useAnalysisData', () => {
    it('iki ucu da yükler', async () => {
        const { result } = renderHook(() => useAnalysisData())
        await waitFor(() => expect(result.current.loading).toBe(false))
        expect(result.current.analysis).toEqual(ANALYSIS)
        expect(result.current.risk).toEqual(RISK)
        expect(result.current.error).toBeNull()
    })

    it('aynı dönemi iki uca birden geçirir', async () => {
        /* Ayrı bıraksaydık tek seçici iki farklı pencere sürerdi. */
        const { result } = renderHook(() => useAnalysisData('3M'))
        await waitFor(() => expect(result.current.loading).toBe(false))
        expect(apiClient.getPortfolioAnalysis).toHaveBeenCalledWith('3M')
        expect(apiClient.getRiskProfile).toHaveBeenCalledWith('3M')
    })

    it('varsayılan dönem bir yıl', async () => {
        const { result } = renderHook(() => useAnalysisData())
        await waitFor(() => expect(result.current.loading).toBe(false))
        expect(apiClient.getRiskProfile).toHaveBeenCalledWith('1Y')
    })

    it('dönem değişince ikisini birden yeniden çeker', async () => {
        const { result } = renderHook(() => useAnalysisData())
        await waitFor(() => expect(result.current.loading).toBe(false))
        act(() => result.current.setLookback('6M'))
        await waitFor(() => expect(result.current.lookback).toBe('6M'))
        await waitFor(() =>
            expect(apiClient.getPortfolioAnalysis).toHaveBeenCalledWith('6M'),
        )
        expect(apiClient.getRiskProfile).toHaveBeenCalledWith('6M')
    })

    it('portföy analizi düşerse risk yine gösterilir', async () => {
        /* Elde olan veriyi, yanındaki istek başarısız oldu diye saklamak
           kullanıcıya olmayan bir kesinti bildirmek olurdu. */
        vi.mocked(apiClient.getPortfolioAnalysis).mockRejectedValue(new Error('boom'))
        const { result } = renderHook(() => useAnalysisData())
        await waitFor(() => expect(result.current.loading).toBe(false))
        expect(result.current.analysis).toBeNull()
        expect(result.current.risk).toEqual(RISK)
        expect(result.current.error).toBe(ANALYSIS_ERROR)
    })

    it('risk düşerse portföy analizi yine gösterilir', async () => {
        vi.mocked(apiClient.getRiskProfile).mockRejectedValue(new Error('boom'))
        const { result } = renderHook(() => useAnalysisData())
        await waitFor(() => expect(result.current.loading).toBe(false))
        expect(result.current.analysis).toEqual(ANALYSIS)
        expect(result.current.risk).toBeNull()
        expect(result.current.error).toBe(ANALYSIS_ERROR)
    })

    it('ikisi de düşerse söyler', async () => {
        vi.mocked(apiClient.getPortfolioAnalysis).mockRejectedValue(new Error('a'))
        vi.mocked(apiClient.getRiskProfile).mockRejectedValue(new Error('b'))
        const { result } = renderHook(() => useAnalysisData())
        await waitFor(() => expect(result.current.error).toBe(ANALYSIS_ERROR))
        expect(result.current.analysis).toBeNull()
        expect(result.current.risk).toBeNull()
    })

    it('bir hatadan sonra yeniden yükleme temizler', async () => {
        vi.mocked(apiClient.getRiskProfile).mockRejectedValueOnce(new Error('boom'))
        const { result } = renderHook(() => useAnalysisData())
        await waitFor(() => expect(result.current.error).toBe(ANALYSIS_ERROR))
        await act(() => result.current.reload())
        expect(result.current.error).toBeNull()
        expect(result.current.risk).toEqual(RISK)
    })
})
