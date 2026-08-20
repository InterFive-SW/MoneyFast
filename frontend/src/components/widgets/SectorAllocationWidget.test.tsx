import { render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import SectorAllocationWidget, { formatSectorTooltip } from './SectorAllocationWidget'
import { apiClient } from '../../api/client'
import type { SectorAllocationItem } from '../../api/client'

const items: SectorAllocationItem[] = [
  { sector: 'Bankacılık', percentage: 35, color: '#3b82f6' },
  { sector: 'Sanayi', percentage: 20, color: '#10b981' },
]

beforeEach(() => {
  vi.spyOn(console, 'error').mockImplementation(() => {})
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('SectorAllocationWidget', () => {
  it('yüklenirken dönen animasyonu gösterir', () => {
    vi.spyOn(apiClient, 'getSectorAllocation').mockReturnValue(new Promise(() => {}))
    render(<SectorAllocationWidget />)
    expect(document.querySelector('.animate-spin')).not.toBeNull()
  })

  it('veri geldiğinde sektör lejantını render eder', async () => {
    vi.spyOn(apiClient, 'getSectorAllocation').mockResolvedValue(items)
    render(<SectorAllocationWidget />)
    await waitFor(() => expect(screen.getByText('Bankacılık')).toBeInTheDocument())
    expect(screen.getByText('Sanayi')).toBeInTheDocument()
    expect(screen.getByText('35%')).toBeInTheDocument()
  })

  it('istek başarısız olursa hatayı loglar ve boş liste gösterir', async () => {
    vi.spyOn(apiClient, 'getSectorAllocation').mockRejectedValue(new Error('network'))
    render(<SectorAllocationWidget />)
    await waitFor(() => expect(console.error).toHaveBeenCalled())
  })
})

describe('formatSectorTooltip', () => {
  it('değeri yüzde ve "Oran" etiketiyle biçimlendirir', () => {
    expect(formatSectorTooltip(35)).toEqual(['35%', 'Oran'])
  })
})
