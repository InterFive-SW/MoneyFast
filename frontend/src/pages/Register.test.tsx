import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import Register from './Register'

const navigateMock = vi.fn()
vi.mock('react-router-dom', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router-dom')>()
  return { ...actual, useNavigate: () => navigateMock }
})

function renderPage() {
  return render(
    <MemoryRouter>
      <Register />
    </MemoryRouter>
  )
}

function fillValidForm(overrides: Partial<{ name: string; surname: string; tcNo: string; email: string; phone: string }> = {}) {
  const v = { name: 'Ada', surname: 'Lovelace', tcNo: '12345678901', email: 'test@example.com', phone: '5551234567', ...overrides }
  fireEvent.change(screen.getByPlaceholderText('Adınızı girin'), { target: { value: v.name } })
  fireEvent.change(screen.getByPlaceholderText('Soyadınızı girin'), { target: { value: v.surname } })
  fireEvent.change(screen.getByPlaceholderText('11 haneli T.C. Kimlik No'), { target: { value: v.tcNo } })
  fireEvent.change(screen.getByPlaceholderText('ornek@posta.com'), { target: { value: v.email } })
  fireEvent.change(screen.getByPlaceholderText('5XX XXX XX XX'), { target: { value: v.phone } })
}

function acceptAllTerms() {
  const [terms, kvkk] = screen.getAllByRole('checkbox')
  fireEvent.click(terms)
  fireEvent.click(kvkk)
}

beforeEach(() => {
  navigateMock.mockClear()
})

describe('Register', () => {
  it('T.C. no ve telefon alanları yalnızca rakam kabul eder ve hane sınırı uygular', () => {
    renderPage()
    const tcInput = screen.getByPlaceholderText('11 haneli T.C. Kimlik No') as HTMLInputElement
    fireEvent.change(tcInput, { target: { value: '12a34-56 78901234' } })
    expect(tcInput.value).toBe('12345678901')

    const phoneInput = screen.getByPlaceholderText('5XX XXX XX XX') as HTMLInputElement
    fireEvent.change(phoneInput, { target: { value: '5a5-5123456789' } })
    expect(phoneInput.value).toBe('5551234567') // rakam dışı karakterler atılır, 10 haneyle sınırlanır
  })

  it('boş alanlarla gönderilirse uyarı gösterir', () => {
    renderPage()
    fireEvent.click(screen.getByText('Devam'))
    expect(screen.getByRole('alert')).toHaveTextContent('Lütfen tüm alanları doldurun.')
  })

  it('sözleşmeler onaylanmadan gönderilirse uyarı gösterir', () => {
    renderPage()
    fillValidForm()
    fireEvent.click(screen.getByText('Devam'))
    expect(screen.getByRole('alert')).toHaveTextContent('Lütfen Kullanıcı Sözleşmesi ve KVKK metinlerini onaylayın.')
  })

  it('geçersiz e-posta girilirse uyarı gösterir', () => {
    renderPage()
    // jsdom native HTML5 email doğrulamasını @ işaretsiz değerlerde submit'i engelliyor —
    // native'i geçen ama uygulamanın nokta zorunlu regex'ini geçemeyen bir değer kullanıyoruz.
    fillValidForm({ email: 'test@localhost' })
    acceptAllTerms()
    fireEvent.click(screen.getByText('Devam'))
    expect(screen.getByRole('alert')).toHaveTextContent('Lütfen geçerli bir e-posta adresi girin.')
  })

  it('T.C. no 11 haneden kısaysa uyarı gösterir', () => {
    renderPage()
    fillValidForm({ tcNo: '123' })
    acceptAllTerms()
    fireEvent.click(screen.getByText('Devam'))
    expect(screen.getByRole('alert')).toHaveTextContent('T.C. Kimlik No 11 haneli olmalıdır.')
  })

  it('telefon 10 haneden kısaysa uyarı gösterir', () => {
    renderPage()
    fillValidForm({ phone: '555' })
    acceptAllTerms()
    fireEvent.click(screen.getByText('Devam'))
    expect(screen.getByRole('alert')).toHaveTextContent('Telefon numarası 10 haneli olmalıdır.')
  })

  it('geçerli bilgilerle gönderilince 2. adıma verilerle birlikte yönlendirir', () => {
    renderPage()
    fillValidForm()
    acceptAllTerms()
    fireEvent.click(screen.getByText('Devam'))

    expect(navigateMock).toHaveBeenCalledWith('/register/password', {
      state: { name: 'Ada', surname: 'Lovelace', tcNo: '12345678901', phone: '5551234567', email: 'test@example.com' },
    })
  })
})
