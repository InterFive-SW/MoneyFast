import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import DashboardLayout from './DashboardLayout'
import { UserProvider } from '../../contexts/UserContext'
import { api } from '../../api/client'

function renderLayout(initialPath = '/dashboard') {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <UserProvider>
        <Routes>
          <Route element={<DashboardLayout />}>
            <Route path="dashboard" element={<div>Panel İçeriği</div>} />
            <Route path="chat" element={<div>Sohbet İçeriği</div>} />
            <Route path="unknown-route" element={<div>Bilinmeyen</div>} />
          </Route>
        </Routes>
      </UserProvider>
    </MemoryRouter>
  )
}

beforeEach(() => {
  localStorage.clear()
  vi.spyOn(console, 'error').mockImplementation(() => {})
  vi.spyOn(api, 'get').mockResolvedValue({ first_name: 'Ada', last_name: 'Lovelace' })
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('DashboardLayout', () => {
  it('bilinen rotada eşlenmiş Türkçe başlığı Header\'a geçirir', () => {
    renderLayout('/dashboard')
    expect(screen.getByText('Gösterge Paneli')).toBeInTheDocument()
    expect(screen.getByText('Panel İçeriği')).toBeInTheDocument()
  })

  it('eşlemede olmayan bir rotada varsayılan MoneyFast başlığını gösterir', () => {
    renderLayout('/unknown-route')
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('MoneyFast')
  })

  it('AI asistan FAB\'ına tıklanınca sohbet popup\'ı açılır ve kapanır', () => {
    renderLayout('/dashboard')
    const fab = screen.getByLabelText('AI Finansal Asistan\'ı aç')
    fireEvent.click(fab)
    expect(screen.getByText('Yapay Zeka Asistanı')).toBeInTheDocument()

    fireEvent.click(fab)
    expect(screen.queryByText('Yapay Zeka Asistanı')).not.toBeInTheDocument()
  })

  it('sohbet popup\'ının kendi kapat butonuna basınca popup kapanır', () => {
    renderLayout('/dashboard')
    fireEvent.click(screen.getByLabelText('AI Finansal Asistan\'ı aç'))
    expect(screen.getByText('Yapay Zeka Asistanı')).toBeInTheDocument()

    fireEvent.click(screen.getByTitle('Kapat'))
    expect(screen.queryByText('Yapay Zeka Asistanı')).not.toBeInTheDocument()
  })

  it('/chat sayfasında FAB gösterilmez', () => {
    renderLayout('/chat')
    expect(screen.queryByLabelText('AI Finansal Asistan\'ı aç')).not.toBeInTheDocument()
  })

  it('sohbet popup\'ı açıkken /chat\'e gidilirse otomatik kapanır', () => {
    renderLayout('/dashboard')
    fireEvent.click(screen.getByLabelText('AI Finansal Asistan\'ı aç'))
    expect(screen.getByText('Yapay Zeka Asistanı')).toBeInTheDocument()

    // Sidebar nav linki — aynı metin CSS tooltip'inde de tekrarlandığı için "a" içindekini seçiyoruz.
    const navLink = screen.getAllByText('Yapay Zeka Asistan').find((el) => el.closest('a'))!
    fireEvent.click(navLink)
    expect(screen.getByText('Sohbet İçeriği')).toBeInTheDocument()
    expect(screen.queryByText('Yapay Zeka Asistanı')).not.toBeInTheDocument()
  })
})
