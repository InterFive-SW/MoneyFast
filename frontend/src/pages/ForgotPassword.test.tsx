import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import ForgotPassword from './ForgotPassword'
import { api } from '../api/client'

function renderPage() {
  return render(
    <MemoryRouter>
      <ForgotPassword />
    </MemoryRouter>
  )
}

function fillTc(value: string) {
  fireEvent.change(screen.getByPlaceholderText('11 haneli T.C. kimlik numaranız'), { target: { value } })
}

function fillEmail(value: string) {
  fireEvent.change(screen.getByPlaceholderText('ornek@email.com'), { target: { value } })
}

beforeEach(() => {
  vi.spyOn(console, 'error').mockImplementation(() => {})
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('ForgotPassword', () => {
  it('TC no alanı yalnızca rakam kabul eder ve 11 haneyle sınırlar', () => {
    renderPage()
    const tcInput = screen.getByPlaceholderText('11 haneli T.C. kimlik numaranız') as HTMLInputElement
    fillTc('12a3-b45 678901234')
    expect(tcInput.value).toBe('12345678901')
  })

  it('boş alanlarla gönderilirse uyarı gösterir', () => {
    renderPage()
    fireEvent.click(screen.getByText('Şifremi Sıfırla'))
    expect(screen.getByText('Lütfen tüm alanları doldurun.')).toBeInTheDocument()
  })

  it('geçersiz e-posta girilirse uyarı gösterir', () => {
    renderPage()
    fillTc('12345678901')
    // jsdom, native HTML5 email doğrulamasını uyguluyor ve @ işareti olmayan
    // değerlerde tıklamayı submit'e hiç ulaştırmıyor — bu yüzden native
    // doğrulamayı geçen ama uygulamanın daha katı regex'ini (nokta zorunlu)
    // geçemeyen bir değer kullanıyoruz.
    fillEmail('test@localhost')
    fireEvent.click(screen.getByText('Şifremi Sıfırla'))
    expect(screen.getByText('Lütfen geçerli bir e-posta adresi girin.')).toBeInTheDocument()
  })

  it('TC no 11 haneden kısaysa uyarı gösterir', () => {
    renderPage()
    fillTc('123')
    fillEmail('test@example.com')
    fireEvent.click(screen.getByText('Şifremi Sıfırla'))
    expect(screen.getByText('T.C. Kimlik No 11 haneli olmalıdır.')).toBeInTheDocument()
  })

  it('geçerli bilgilerle gönderilince başarı mesajı gösterir', async () => {
    vi.spyOn(api, 'post').mockResolvedValue({})
    renderPage()
    fillTc('12345678901')
    fillEmail('test@example.com')
    fireEvent.click(screen.getByText('Şifremi Sıfırla'))

    expect(screen.getByText('Gönderiliyor...')).toBeInTheDocument()
    await waitFor(() => expect(screen.getByText('Şifre yenileme bağlantısı e-posta adresinize gönderildi.')).toBeInTheDocument())
  })

  it('istek başarısız olursa API mesajını, yoksa varsayılan mesajı gösterir', async () => {
    vi.spyOn(api, 'post').mockRejectedValue(new Error('Sunucu hatası'))
    renderPage()
    fillTc('12345678901')
    fillEmail('test@example.com')
    fireEvent.click(screen.getByText('Şifremi Sıfırla'))

    await waitFor(() => expect(screen.getByText('Sunucu hatası')).toBeInTheDocument())
  })

  it('istek hata mesajı yoksa varsayılan hata metnini gösterir', async () => {
    vi.spyOn(api, 'post').mockRejectedValue({})
    renderPage()
    fillTc('12345678901')
    fillEmail('test@example.com')
    fireEvent.click(screen.getByText('Şifremi Sıfırla'))

    await waitFor(() => expect(screen.getByText('Bir hata oluştu. Lütfen bilgilerinizi kontrol edin.')).toBeInTheDocument())
  })
})
