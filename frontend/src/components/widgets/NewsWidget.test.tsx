import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import NewsWidget from './NewsWidget'
import type { NewsItem } from '../../api/client'

// NOT: Gerçek API tipi olan NewsItem'da `category` alanı yok (bkz. memory:
// project-tsc-build-gap) — widget yine de item.category okuyor. Testler widget'ın
// gerçek çalışma zamanı davranışını, sahte veriyi widget'ın beklediği şekle
// zorlayarak (as unknown as) doğruluyor; tip uyuşmazlığını burada düzeltmiyoruz.
const news = [
  { id: 'N-1', title: 'THYAO bilanço açıkladı', source: 'KAP', category: 'BIST', time: '09:15' },
  { id: 'N-2', title: 'Fed faiz sinyali verdi', source: 'Reuters', category: 'ABD', time: 'Dün' },
] as unknown as NewsItem[]

describe('NewsWidget', () => {
  it('varsayılan "Tümü" filtresinde tüm haberleri render eder', () => {
    render(<NewsWidget news={news} />)
    expect(screen.getByText('THYAO bilanço açıkladı')).toBeInTheDocument()
    expect(screen.getByText('Fed faiz sinyali verdi')).toBeInTheDocument()
  })

  it('haber listesi boşsa boş durum mesajını gösterir', () => {
    render(<NewsWidget news={[]} />)
    expect(screen.getByText('Bu kategoride haber bulunamadı.')).toBeInTheDocument()
  })

  it('"Piyasa" filtresine tıklanınca kategori eşleşmediği için boş durum gösterilir', () => {
    render(<NewsWidget news={news} />)
    fireEvent.click(screen.getByRole('button', { name: 'Piyasa' }))
    expect(screen.getByText('Bu kategoride haber bulunamadı.')).toBeInTheDocument()
  })

  it('"KAP" filtresine tıklanınca aktif sekme stiline geçer', () => {
    render(<NewsWidget news={news} />)
    const kapButton = screen.getByRole('button', { name: 'KAP' })
    fireEvent.click(kapButton)
    expect(kapButton.className).toContain('text-white')
  })
})
