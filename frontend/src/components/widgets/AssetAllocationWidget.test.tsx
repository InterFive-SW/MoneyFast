import { render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import AssetAllocationWidget, { formatAllocationTooltip } from './AssetAllocationWidget'
import { apiClient } from '../../api/client'
import type { AssetAllocationItem } from '../../api/client'

const items: AssetAllocationItem[] = [
  { assetClass: 'Hisse Senedi', percentage: 42, amount: 52_815.17, color: '#10b981' },
  { assetClass: 'Nakit', percentage: 4, amount: 5_030.02, color: '#94a3b8' },
]

beforeEach(() => {
  vi.spyOn(console, 'error').mockImplementation(() => {})
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('AssetAllocationWidget', () => {
  it('yüklenirken dönen animasyonu gösterir', () => {
    vi.spyOn(apiClient, 'getAssetAllocation').mockReturnValue(new Promise(() => {}))
    render(<AssetAllocationWidget />)
    expect(document.querySelector('.animate-spin')).not.toBeNull()
  })

  it('veri geldiğinde toplam tutarı ve varlık listesini render eder', async () => {
    vi.spyOn(apiClient, 'getAssetAllocation').mockResolvedValue(items)
    render(<AssetAllocationWidget />)
    await waitFor(() => expect(screen.getByText('Hisse Senedi')).toBeInTheDocument())
    expect(screen.getByText('Nakit')).toBeInTheDocument()
    expect(screen.getByText(/₺57\.845/)).toBeInTheDocument() // toplam
  })

  it('istek başarısız olursa hatayı loglar ve boş liste gösterir', async () => {
    vi.spyOn(apiClient, 'getAssetAllocation').mockRejectedValue(new Error('network'))
    render(<AssetAllocationWidget />)
    await waitFor(() => expect(console.error).toHaveBeenCalled())
  })
})

describe('formatAllocationTooltip', () => {
  it('yüzde ve tutarı birlikte biçimlendirir', () => {
    const [label, name] = formatAllocationTooltip(42, 'Hisse Senedi', { payload: { amount: 52_815.17 } })
    expect(label).toBe('%42 - ₺52.815')
    expect(name).toBe('Hisse Senedi')
  })
})
