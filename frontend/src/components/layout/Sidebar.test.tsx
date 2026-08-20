import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import Sidebar from './Sidebar'
import { UserProvider } from '../../contexts/UserContext'
import { api } from '../../api/client'

function renderSidebar(initialPath = '/dashboard') {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <UserProvider>
        <Routes>
          <Route path="login" element={<div>Giriş Sayfası</div>} />
          <Route path="*" element={<Sidebar />} />
        </Routes>
      </UserProvider>
    </MemoryRouter>
  )
}

beforeEach(() => {
  localStorage.clear()
  vi.spyOn(console, 'error').mockImplementation(() => {})
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('Sidebar', () => {
  it('tüm ana menü öğelerini render eder', () => {
    renderSidebar()
    // Varsayılan olarak daraltılmış (hover ile genişler) — etiketler hem nav'da hem
    // tooltip'te aynı metinle göründüğü için genişletip tekil eşleşme sağlıyoruz.
    fireEvent.mouseEnter(screen.getByRole('complementary'))
    for (const label of ['Genel Bakış', 'Portföyüm', 'Piyasalar', 'Banka İşlemleri', 'Yapay Zeka Asistan', 'Risk Analizi']) {
      expect(screen.getByText(label)).toBeInTheDocument()
    }
  })

  it('aktif rotaya karşılık gelen link aria-current="page" taşır', () => {
    renderSidebar('/portfolio')
    fireEvent.mouseEnter(screen.getByRole('complementary'))
    const link = screen.getByText('Portföyüm').closest('a')
    expect(link).toHaveAttribute('aria-current', 'page')
  })

  it('hover ile genişler/daralır; etiketler CSS ile gizlenir, tooltip yalnızca daraltılmış modda görünür', () => {
    renderSidebar()
    const aside = screen.getByRole('complementary')

    // Varsayılan: daraltılmış — tooltip DOM'da, nav etiketi opacity-0 ile gizli.
    expect(screen.getAllByRole('tooltip').length).toBeGreaterThan(0)
    const collapsedLabel = screen.getAllByText('Genel Bakış').find((el) => !el.closest('[role="tooltip"]'))
    expect(collapsedLabel?.className).toContain('opacity-0')

    fireEvent.mouseEnter(aside)
    // Genişletilmiş modda tooltip DOM'dan kaldırılır, etiket görünür olur.
    expect(screen.queryAllByRole('tooltip')).toHaveLength(0)
    expect(screen.getByText('Genel Bakış').className).toContain('opacity-100')

    fireEvent.mouseLeave(aside)
    expect(screen.getAllByRole('tooltip').length).toBeGreaterThan(0)
  })

  it('profil yüklenirken iskelet gösterir, yüklenince gerçek profili gösterir', async () => {
    vi.spyOn(api, 'get').mockResolvedValue({ first_name: 'Can', last_name: 'Öz' })
    const futureExp = Math.floor(Date.now() / 1000) + 3600
    const token = `h.${btoa(JSON.stringify({ exp: futureExp })).replace(/=+$/, '')}.s`
    localStorage.setItem('access_token', token)

    renderSidebar()
    expect(document.querySelector('.animate-pulse')).not.toBeNull()

    await waitFor(() => expect(screen.getByText('Can Öz')).toBeInTheDocument())
  })

  it('oturumu kapat butonuna basınca token silinir ve /login\'e yönlendirilir', async () => {
    localStorage.setItem('access_token', 'herhangi-bir-token')
    renderSidebar()
    fireEvent.mouseEnter(screen.getByRole('complementary'))

    fireEvent.click(screen.getByLabelText('Oturumu kapat'))

    await waitFor(() => expect(screen.getByText('Giriş Sayfası')).toBeInTheDocument())
    expect(localStorage.getItem('access_token')).toBeNull()
  })
})
