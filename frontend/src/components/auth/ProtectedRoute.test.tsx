import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it } from 'vitest'
import ProtectedRoute from './ProtectedRoute'

function base64Url(obj: object): string {
  return btoa(JSON.stringify(obj)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
}

function makeJwt(payload: object): string {
  return `${base64Url({ alg: 'HS256' })}.${base64Url(payload)}.signature`
}

function renderProtected() {
  return render(
    <MemoryRouter initialEntries={['/dashboard']}>
      <Routes>
        <Route path="login" element={<div>Giriş Sayfası</div>} />
        <Route element={<ProtectedRoute />}>
          <Route path="dashboard" element={<div>Korumalı İçerik</div>} />
        </Route>
      </Routes>
    </MemoryRouter>
  )
}

beforeEach(() => {
  localStorage.clear()
})

describe('ProtectedRoute', () => {
  it('access_token yoksa /login\'e yönlendirir', () => {
    renderProtected()
    expect(screen.getByText('Giriş Sayfası')).toBeInTheDocument()
  })

  it('geçerli, süresi dolmamış token varsa korumalı içeriği render eder', () => {
    const futureExp = Math.floor(Date.now() / 1000) + 3600
    localStorage.setItem('access_token', makeJwt({ exp: futureExp }))
    renderProtected()
    expect(screen.getByText('Korumalı İçerik')).toBeInTheDocument()
  })

  it('süresi dolmuş token varsa /login\'e yönlendirir', () => {
    const pastExp = Math.floor(Date.now() / 1000) - 3600
    localStorage.setItem('access_token', makeJwt({ exp: pastExp }))
    renderProtected()
    expect(screen.getByText('Giriş Sayfası')).toBeInTheDocument()
  })

  it('3 segmentli olmayan (bozuk) token varsa /login\'e yönlendirir', () => {
    localStorage.setItem('access_token', 'sadece-bir-parca')
    renderProtected()
    expect(screen.getByText('Giriş Sayfası')).toBeInTheDocument()
  })

  it('payload segmenti geçerli JSON değilse /login\'e yönlendirir', () => {
    localStorage.setItem('access_token', `header.${btoa('json-degil')}.signature`)
    renderProtected()
    expect(screen.getByText('Giriş Sayfası')).toBeInTheDocument()
  })

  it('exp claim\'i eksikse /login\'e yönlendirir', () => {
    localStorage.setItem('access_token', makeJwt({ sub: '123' }))
    renderProtected()
    expect(screen.getByText('Giriş Sayfası')).toBeInTheDocument()
  })

  it('exp claim\'i sayı değilse /login\'e yönlendirir', () => {
    localStorage.setItem('access_token', makeJwt({ exp: 'sayi-degil' }))
    renderProtected()
    expect(screen.getByText('Giriş Sayfası')).toBeInTheDocument()
  })
})
