import { act, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import Header from './Header'
import { UserProvider } from '../../contexts/UserContext'
import { api } from '../../api/client'

function renderHeader(title = 'Gösterge Paneli') {
  return render(
    <UserProvider>
      <Header pageTitle={title} />
    </UserProvider>
  )
}

beforeEach(() => {
  localStorage.clear()
  vi.spyOn(console, 'error').mockImplementation(() => {})
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('Header', () => {
  it('profil yüklenirken iskelet (skeleton) gösterir, sonra gerçek içeriğe geçer', async () => {
    let resolveGet!: (value: unknown) => void
    vi.spyOn(api, 'get').mockReturnValue(new Promise((resolve) => { resolveGet = resolve }))
    const futureExp = Math.floor(Date.now() / 1000) + 3600
    const token = `h.${btoa(JSON.stringify({ exp: futureExp })).replace(/=+$/, '')}.s`
    localStorage.setItem('access_token', token)

    renderHeader()
    // api.get henüz çözülmediği için isLoading=true, iskelet görünür olmalı
    expect(document.querySelector('.animate-pulse')).not.toBeNull()

    resolveGet({ first_name: 'Test', last_name: 'Kullanıcı' })
    await waitFor(() => expect(document.querySelector('.animate-pulse')).toBeNull())
  })

  it('sayfa başlığını prop\'tan render eder', async () => {
    renderHeader('Portföy')
    expect(screen.getByText('Portföy')).toBeInTheDocument()
    await waitFor(() => expect(document.querySelector('.animate-pulse')).toBeNull())
  })

  it('bugünün tarihini Türkçe uzun formatta gösterir', async () => {
    renderHeader()
    const expected = new Date().toLocaleDateString('tr-TR', {
      weekday: 'long', day: 'numeric', month: 'long', year: 'numeric',
    })
    await waitFor(() => expect(screen.getByText(expected, { exact: false })).toBeInTheDocument())
  })

  it('profil yüklenince kullanıcı adı ve baş harfleri gösterir', async () => {
    vi.spyOn(api, 'get').mockResolvedValue({ first_name: 'Elif', last_name: 'Şahin' })
    const futureExp = Math.floor(Date.now() / 1000) + 3600
    const token = `h.${btoa(JSON.stringify({ exp: futureExp })).replace(/=+$/, '')}.s`
    localStorage.setItem('access_token', token)

    renderHeader()

    await waitFor(() => expect(screen.getByText('Elif Şahin')).toBeInTheDocument())
    expect(screen.getByText('EŞ')).toBeInTheDocument()
  })

  it('bildirim butonu erişilebilir etikete sahiptir', () => {
    renderHeader()
    expect(screen.getByLabelText('Bildirimleri görüntüle')).toBeInTheDocument()
  })

  it('unmount edildiğinde gece yarısı zamanlayıcısı temizlenir (hata fırlatmaz)', async () => {
    const { unmount } = renderHeader()
    await waitFor(() => expect(document.querySelector('.animate-pulse')).toBeNull())
    expect(() => unmount()).not.toThrow()
  })

  it('gece yarısı geçişinde tarih etiketi otomatik günceller', async () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date(2026, 0, 1, 23, 59, 59, 500))

    renderHeader()
    act(() => {
      vi.advanceTimersByTime(1000)
    })

    const expected = new Date(2026, 0, 2).toLocaleDateString('tr-TR', {
      weekday: 'long', day: 'numeric', month: 'long', year: 'numeric',
    })
    expect(screen.getByText(expected, { exact: false })).toBeInTheDocument()

    vi.useRealTimers()
  })
})
