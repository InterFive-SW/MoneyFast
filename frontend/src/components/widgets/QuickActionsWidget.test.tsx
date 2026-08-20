import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import QuickActionsWidget from './QuickActionsWidget'

const navigateMock = vi.fn()
vi.mock('react-router-dom', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router-dom')>()
  return { ...actual, useNavigate: () => navigateMock }
})

beforeEach(() => {
  navigateMock.mockClear()
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('QuickActionsWidget', () => {
  it('tüm hızlı işlem butonlarını render eder', () => {
    render(<QuickActionsWidget />)
    for (const label of ['Para Gönder', 'Yatırım', 'Portföy', 'Risk']) {
      expect(screen.getByText(label)).toBeInTheDocument()
    }
  })

  it('her butona tıklanınca kendi rotasına yönlendirir', () => {
    render(<QuickActionsWidget />)

    fireEvent.click(screen.getByText('Para Gönder'))
    expect(navigateMock).toHaveBeenCalledWith('/banking/transfer')

    fireEvent.click(screen.getByText('Yatırım'))
    expect(navigateMock).toHaveBeenCalledWith('/investment')

    fireEvent.click(screen.getByText('Portföy'))
    expect(navigateMock).toHaveBeenCalledWith('/portfolio')

    fireEvent.click(screen.getByText('Risk'))
    expect(navigateMock).toHaveBeenCalledWith('/risk')
  })
})
