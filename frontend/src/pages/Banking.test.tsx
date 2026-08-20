import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import Banking from './Banking'
import BankingDashboard from '../components/banking/BankingDashboard'

function renderBanking() {
  return render(
    <MemoryRouter initialEntries={['/banking']}>
      <Routes>
        <Route path="banking" element={<Banking />}>
          <Route index element={<BankingDashboard />} />
        </Route>
      </Routes>
    </MemoryRouter>
  )
}

describe('Banking', () => {
  it('yüklenirken bekleme durumunu, ardından hesap özetini gösterir', async () => {
    renderBanking()
    expect(screen.getByText('Veriler yükleniyor...')).toBeInTheDocument()

    await waitFor(() => expect(screen.queryByText('Veriler yükleniyor...')).not.toBeInTheDocument())
    expect(screen.getByText('Vadesiz Maaş Hesabı')).toBeInTheDocument()
  })
})
