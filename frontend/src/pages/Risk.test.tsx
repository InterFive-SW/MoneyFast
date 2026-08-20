import { act, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import Risk from './Risk'

beforeEach(() => {
  vi.useFakeTimers()
})

afterEach(() => {
  vi.useRealTimers()
})

describe('Risk', () => {
  it('yüklenirken dönen animasyonu gösterir, ardından risk verilerini render eder', () => {
    render(<Risk />)
    expect(screen.getByText('Risk profiliniz analiz ediliyor...')).toBeInTheDocument()

    act(() => {
      vi.advanceTimersByTime(1200)
    })

    expect(screen.getByText('Genel Risk Skoru')).toBeInTheDocument()
    expect(screen.getByText('Finansal Denge')).toBeInTheDocument()
    expect(screen.getByText('Öne Çıkan Risk Faktörleri')).toBeInTheDocument()
    expect(screen.getByText('İyileştirme Önerileri')).toBeInTheDocument()
  })

  it('unmount edilirse zamanlayıcı temizlenir (hata fırlatmaz)', () => {
    const { unmount } = render(<Risk />)
    expect(() => unmount()).not.toThrow()
  })
})
