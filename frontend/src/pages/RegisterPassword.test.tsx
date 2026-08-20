import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import RegisterPassword from './RegisterPassword'
import { api } from '../api/client'

const navigateMock = vi.fn()
vi.mock('react-router-dom', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router-dom')>()
  return { ...actual, useNavigate: () => navigateMock }
})

const step1State = { name: 'Ada', surname: 'Lovelace', tcNo: '12345678901', phone: '5551234567', email: 'test@example.com' }

function renderPage(state: unknown = step1State) {
  return render(
    <MemoryRouter initialEntries={[{ pathname: '/register/password', state }]}>
      <RegisterPassword />
    </MemoryRouter>
  )
}

function fillPasswords(password: string, confirm = password) {
  fireEvent.change(screen.getByPlaceholderText('Şifrenizi oluşturun'), { target: { value: password } })
  fireEvent.change(screen.getByPlaceholderText('Şifrenizi tekrar girin'), { target: { value: confirm } })
}

function acceptTerms() {
  fireEvent.click(screen.getByRole('checkbox'))
}

beforeEach(() => {
  navigateMock.mockClear()
  vi.spyOn(console, 'error').mockImplementation(() => {})
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('RegisterPassword', () => {
  it('1. adım verisi (location.state) yoksa /register\'a geri döner', () => {
    renderPage(null)
    expect(navigateMock).toHaveBeenCalledWith('/register')
  })

  it('şifre göster/gizle her iki alanı birlikte değiştirir', () => {
    renderPage()
    const pwInput = screen.getByPlaceholderText('Şifrenizi oluşturun') as HTMLInputElement
    const confirmInput = screen.getByPlaceholderText('Şifrenizi tekrar girin') as HTMLInputElement
    expect(pwInput.type).toBe('password')
    expect(confirmInput.type).toBe('password')

    fireEvent.click(screen.getByText('Göster'))
    expect(pwInput.type).toBe('text')
    expect(confirmInput.type).toBe('text')
  })

  it('boş alanlarla gönderilirse uyarı gösterir', () => {
    renderPage()
    fireEvent.click(screen.getByRole('button', { name: /Hesap Oluştur/ }))
    expect(screen.getByRole('alert')).toHaveTextContent('Lütfen şifre alanlarını doldurun.')
  })

  it('şifre 8 karakterden kısaysa uyarı gösterir', () => {
    renderPage()
    fillPasswords('Ab1')
    fireEvent.click(screen.getByRole('button', { name: /Hesap Oluştur/ }))
    expect(screen.getByRole('alert')).toHaveTextContent('Şifreniz en az 8 karakter olmalıdır.')
  })

  it('büyük harf içermezse uyarı gösterir', () => {
    renderPage()
    fillPasswords('abcdefg1')
    fireEvent.click(screen.getByRole('button', { name: /Hesap Oluştur/ }))
    expect(screen.getByRole('alert')).toHaveTextContent('Şifreniz en az bir büyük harf içermelidir.')
  })

  it('küçük harf içermezse uyarı gösterir', () => {
    renderPage()
    fillPasswords('ABCDEFG1')
    fireEvent.click(screen.getByRole('button', { name: /Hesap Oluştur/ }))
    expect(screen.getByRole('alert')).toHaveTextContent('Şifreniz en az bir küçük harf içermelidir.')
  })

  it('rakam içermezse uyarı gösterir', () => {
    renderPage()
    fillPasswords('Abcdefgh')
    fireEvent.click(screen.getByRole('button', { name: /Hesap Oluştur/ }))
    expect(screen.getByRole('alert')).toHaveTextContent('Şifreniz en az bir rakam içermelidir.')
  })

  it('şifreler eşleşmezse uyarı gösterir', () => {
    renderPage()
    fillPasswords('Abcdefg1', 'Abcdefg2')
    fireEvent.click(screen.getByRole('button', { name: /Hesap Oluştur/ }))
    expect(screen.getByRole('alert')).toHaveTextContent('Şifreler birbiriyle eşleşmiyor.')
  })

  it('sözleşme onaylanmadan gönderilirse uyarı gösterir', () => {
    renderPage()
    fillPasswords('Abcdefg1')
    fireEvent.click(screen.getByRole('button', { name: /Hesap Oluştur/ }))
    expect(screen.getByRole('alert')).toHaveTextContent('Devam etmek için kullanıcı sözleşmesini onaylamalısınız.')
  })

  it('geçerli bilgilerle gönderilince kayıt olur, login\'e yönlendirir (telefon zaten +90 ile başlıyorsa aynen kullanılır)', async () => {
    vi.spyOn(api, 'post').mockResolvedValue({})
    renderPage({ ...step1State, phone: '+905551234567' })
    fillPasswords('Abcdefg1')
    acceptTerms()
    fireEvent.click(screen.getByRole('button', { name: /Hesap Oluştur/ }))

    expect(screen.getByText('Hesap Oluşturuluyor...')).toBeInTheDocument()
    await waitFor(() => expect(navigateMock).toHaveBeenCalledWith('/login'))
    expect(api.post).toHaveBeenCalledWith('/api/auth/register', expect.objectContaining({ phone_number: '+905551234567' }))
  })

  it('telefon +90 ile başlamıyorsa öneki eklenir', async () => {
    vi.spyOn(api, 'post').mockResolvedValue({})
    renderPage()
    fillPasswords('Abcdefg1')
    acceptTerms()
    fireEvent.click(screen.getByRole('button', { name: /Hesap Oluştur/ }))

    await waitFor(() => expect(api.post).toHaveBeenCalled())
    expect(api.post).toHaveBeenCalledWith('/api/auth/register', expect.objectContaining({ phone_number: '+905551234567' }))
  })

  it('kayıt başarısız olursa API mesajını gösterir', async () => {
    vi.spyOn(api, 'post').mockRejectedValue(new Error('Bu TC ile zaten kayıt var'))
    renderPage()
    fillPasswords('Abcdefg1')
    acceptTerms()
    fireEvent.click(screen.getByRole('button', { name: /Hesap Oluştur/ }))

    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('Bu TC ile zaten kayıt var'))
  })

  it('hata mesajı yoksa varsayılan hata metnini gösterir', async () => {
    vi.spyOn(api, 'post').mockRejectedValue({})
    renderPage()
    fillPasswords('Abcdefg1')
    acceptTerms()
    fireEvent.click(screen.getByRole('button', { name: /Hesap Oluştur/ }))

    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('Kayıt olurken bir hata oluştu. Lütfen bilgilerinizi kontrol edin.'))
  })
})
