import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import Login from './Login'
import { api } from '../api/client'

function renderPage() {
  return render(
    <MemoryRouter>
      <Login />
    </MemoryRouter>
  )
}

function fillTc(value: string) {
  fireEvent.change(screen.getByPlaceholderText('11 haneli T.C. Kimlik No'), { target: { value } })
}

function fillPassword(value: string) {
  fireEvent.change(screen.getByPlaceholderText('Şifrenizi girin'), { target: { value } })
}

beforeEach(() => {
  localStorage.clear()
  vi.spyOn(console, 'error').mockImplementation(() => {})
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('Login', () => {
  it('TC no alanı yalnızca rakam kabul eder ve 11 haneyle sınırlar', () => {
    renderPage()
    const tcInput = screen.getByPlaceholderText('11 haneli T.C. Kimlik No') as HTMLInputElement
    fillTc('12a3-b45 678901234')
    expect(tcInput.value).toBe('12345678901')
  })

  it('şifre göster/gizle butonuna basınca input tipi değişir', () => {
    renderPage()
    const passwordInput = screen.getByPlaceholderText('Şifrenizi girin') as HTMLInputElement
    expect(passwordInput.type).toBe('password')
    fireEvent.click(screen.getByText('Göster'))
    expect(passwordInput.type).toBe('text')
    expect(screen.getByText('Gizle')).toBeInTheDocument()
  })

  it('boş alanlarla gönderilirse uyarı gösterir', () => {
    renderPage()
    fireEvent.click(screen.getByText('Giriş Yap'))
    expect(screen.getByRole('alert')).toHaveTextContent('Lütfen T.C. Kimlik No ve şifre alanlarını doldurun.')
  })

  it('TC no 11 haneden kısaysa uyarı gösterir', () => {
    renderPage()
    fillTc('123')
    fillPassword('sifre123')
    fireEvent.click(screen.getByText('Giriş Yap'))
    expect(screen.getByRole('alert')).toHaveTextContent('T.C. Kimlik No 11 haneli olmalıdır.')
  })

  it('geçerli bilgilerle giriş başarılı olursa token kaydeder ve /dashboard\'a yönlendirir', async () => {
    vi.spyOn(api, 'post').mockResolvedValue({ access_token: 'tok-123' })
    renderPage()
    fillTc('12345678901')
    fillPassword('sifre123')
    fireEvent.click(screen.getByText('Giriş Yap'))

    expect(screen.getByText('Giriş Yapılıyor...')).toBeInTheDocument()
    await waitFor(() => expect(localStorage.getItem('access_token')).toBe('tok-123'))
  })

  it('giriş başarısız olursa API mesajını gösterir', async () => {
    vi.spyOn(api, 'post').mockRejectedValue(new Error('Hatalı kimlik bilgisi'))
    renderPage()
    fillTc('12345678901')
    fillPassword('sifre123')
    fireEvent.click(screen.getByText('Giriş Yap'))

    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('Hatalı kimlik bilgisi'))
  })

  it('hata mesajı yoksa varsayılan hata metnini gösterir', async () => {
    vi.spyOn(api, 'post').mockRejectedValue({})
    renderPage()
    fillTc('12345678901')
    fillPassword('sifre123')
    fireEvent.click(screen.getByText('Giriş Yap'))

    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('Giriş yapılamadı. Bilgilerinizi kontrol edin.'))
  })
})
