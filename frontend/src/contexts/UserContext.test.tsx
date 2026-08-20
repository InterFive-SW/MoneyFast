import { render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { UserProvider, useUser } from './UserContext'
import { api } from '../api/client'

function base64Url(obj: object): string {
  return btoa(JSON.stringify(obj)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
}

function makeJwt(payload: object): string {
  return `${base64Url({ alg: 'HS256' })}.${base64Url(payload)}.signature`
}

function TestConsumer() {
  const { profile, isLoading, refetch } = useUser()
  return (
    <div>
      <span data-testid="loading">{String(isLoading)}</span>
      <span data-testid="fullName">{profile?.fullName ?? ''}</span>
      <span data-testid="initials">{profile?.initials ?? ''}</span>
      <span data-testid="tcNo">{profile?.tcNo ?? ''}</span>
      <button onClick={() => refetch()}>refetch</button>
    </div>
  )
}

function BadConsumer() {
  useUser()
  return null
}

beforeEach(() => {
  localStorage.clear()
  vi.spyOn(console, 'error').mockImplementation(() => {})
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('useUser', () => {
  it('UserProvider dışında kullanılırsa hata fırlatır', () => {
    expect(() => render(<BadConsumer />)).toThrow(
      'useUser, UserProvider bileşeni kapsayıcısı dışında kullanılamaz.'
    )
  })
})

describe('UserProvider — token yok/geçersiz senaryoları', () => {
  it('token yoksa fallback profil kullanılır', async () => {
    render(<UserProvider><TestConsumer /></UserProvider>)
    await waitFor(() => expect(screen.getByTestId('loading').textContent).toBe('false'))
    expect(screen.getByTestId('fullName').textContent).toBe('Kullanıcı')
    expect(screen.getByTestId('initials').textContent).toBe('KL')
  })

  it('nokta içermeyen bozuk bir token fallback\'e düşürür', async () => {
    localStorage.setItem('access_token', 'bozuk-token-noktasiz')
    render(<UserProvider><TestConsumer /></UserProvider>)
    await waitFor(() => expect(screen.getByTestId('loading').textContent).toBe('false'))
    expect(screen.getByTestId('fullName').textContent).toBe('Kullanıcı')
  })

  it('payload segmenti geçerli JSON değilse (decode hatası) fallback\'e düşürür', async () => {
    const token = `header.${btoa('bu bir json degil')}.signature`
    localStorage.setItem('access_token', token)
    render(<UserProvider><TestConsumer /></UserProvider>)
    await waitFor(() => expect(screen.getByTestId('loading').textContent).toBe('false'))
    expect(screen.getByTestId('fullName').textContent).toBe('Kullanıcı')
  })

  it('exp claim\'i sayı değilse süresi dolmuş sayılır', async () => {
    const token = makeJwt({ exp: 'sayi-degil', sub: '11111111111' })
    localStorage.setItem('access_token', token)
    render(<UserProvider><TestConsumer /></UserProvider>)
    await waitFor(() => expect(screen.getByTestId('loading').textContent).toBe('false'))
    expect(screen.getByTestId('fullName').textContent).toBe('Kullanıcı')
  })

  it('exp geçmiş bir zamansa süresi dolmuş sayılır, /me hiç çağrılmaz', async () => {
    const getSpy = vi.spyOn(api, 'get')
    const pastExp = Math.floor(Date.now() / 1000) - 3600
    const token = makeJwt({ exp: pastExp, sub: '22222222222' })
    localStorage.setItem('access_token', token)
    render(<UserProvider><TestConsumer /></UserProvider>)
    await waitFor(() => expect(screen.getByTestId('loading').textContent).toBe('false'))
    expect(screen.getByTestId('fullName').textContent).toBe('Kullanıcı')
    expect(getSpy).not.toHaveBeenCalled()
  })
})

describe('UserProvider — geçerli token senaryoları', () => {
  it('geçerli token + başarılı /me yanıtı gerçek profili oluşturur', async () => {
    const futureExp = Math.floor(Date.now() / 1000) + 3600
    const token = makeJwt({ exp: futureExp, sub: '33333333333' })
    localStorage.setItem('access_token', token)
    vi.spyOn(api, 'get').mockResolvedValue({ first_name: 'Ahmet', last_name: 'Yılmaz' })

    render(<UserProvider><TestConsumer /></UserProvider>)

    await waitFor(() => expect(screen.getByTestId('loading').textContent).toBe('false'))
    expect(screen.getByTestId('fullName').textContent).toBe('Ahmet Yılmaz')
    expect(screen.getByTestId('initials').textContent).toBe('AY')
    expect(screen.getByTestId('tcNo').textContent).toBe('33333333333')
  })

  it('/me isteği başarısız olursa (sunucu hatası) fallback isimle ama gerçek tcNo ile devam eder', async () => {
    const futureExp = Math.floor(Date.now() / 1000) + 3600
    const token = makeJwt({ exp: futureExp, sub: '44444444444' })
    localStorage.setItem('access_token', token)
    vi.spyOn(api, 'get').mockRejectedValue(new Error('sunucu hatası'))

    render(<UserProvider><TestConsumer /></UserProvider>)

    await waitFor(() => expect(screen.getByTestId('loading').textContent).toBe('false'))
    expect(screen.getByTestId('fullName').textContent).toBe('Kullanıcı')
    expect(screen.getByTestId('tcNo').textContent).toBe('44444444444')
  })

  it('first_name/last_name boşsa fallback isim ve tek harfli initials kullanılır', async () => {
    const futureExp = Math.floor(Date.now() / 1000) + 3600
    const token = makeJwt({ exp: futureExp, sub: '55555555555' })
    localStorage.setItem('access_token', token)
    vi.spyOn(api, 'get').mockResolvedValue({ first_name: '   ', last_name: '' })

    render(<UserProvider><TestConsumer /></UserProvider>)

    await waitFor(() => expect(screen.getByTestId('loading').textContent).toBe('false'))
    expect(screen.getByTestId('fullName').textContent).toBe('Kullanıcı')
    expect(screen.getByTestId('initials').textContent).toBe('K')
  })

  it('JWT\'de sub claim\'i yoksa tcNo boş string olur', async () => {
    const futureExp = Math.floor(Date.now() / 1000) + 3600
    const token = makeJwt({ exp: futureExp })
    localStorage.setItem('access_token', token)
    vi.spyOn(api, 'get').mockResolvedValue({ first_name: 'Ali', last_name: 'Demir' })

    render(<UserProvider><TestConsumer /></UserProvider>)

    await waitFor(() => expect(screen.getByTestId('loading').textContent).toBe('false'))
    expect(screen.getByTestId('tcNo').textContent).toBe('')
  })

  it('refetch çağrıldığında profil yeniden çekilir', async () => {
    const futureExp = Math.floor(Date.now() / 1000) + 3600
    const token = makeJwt({ exp: futureExp, sub: '66666666666' })
    localStorage.setItem('access_token', token)
    const getSpy = vi.spyOn(api, 'get').mockResolvedValue({ first_name: 'Zeynep', last_name: 'Kaya' })

    render(<UserProvider><TestConsumer /></UserProvider>)
    await waitFor(() => expect(screen.getByTestId('loading').textContent).toBe('false'))
    expect(getSpy).toHaveBeenCalledTimes(1)

    screen.getByText('refetch').click()
    await waitFor(() => expect(getSpy).toHaveBeenCalledTimes(2))
  })
})
