import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import Landing from './Landing'

describe('Landing', () => {
  it('kahraman başlığını ve giriş/kayıt bağlantılarını render eder', () => {
    render(
      <MemoryRouter>
        <Landing />
      </MemoryRouter>
    )
    expect(screen.getByText('Paranızı Hızla Yönetin,')).toBeInTheDocument()
    expect(screen.getByText('Giriş Yap')).toBeInTheDocument()
    expect(screen.getByText('Ücretsiz Kayıt Ol')).toBeInTheDocument()
  })
})
