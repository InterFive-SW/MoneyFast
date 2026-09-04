import { useState } from 'react'
import type { FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import logo from '../assets/logo-icon.png'
import { api } from '../api/client'

export default function Login() {
  const navigate = useNavigate()

  const [tcNo, setTcNo] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  function handleTcChange(value: string) {
    // Sadece rakam kabul et ve maksimum 11 karakter tut.
    const onlyNumbers = value.replace(/\D/g, '').slice(0, 11)
    setTcNo(onlyNumbers)
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError('')

    if (!tcNo.trim() || !password.trim()) {
      setError('Lütfen T.C. Kimlik No ve şifre alanlarını doldurun.')
      return
    }

    if (tcNo.length !== 11) {
      setError('T.C. Kimlik No 11 haneli olmalıdır.')
      return
    }

    setLoading(true)
    try {
      const response = await api.post<{ access_token: string; refresh_token?: string }>(
        '/api/auth/login',
        { tc_no: tcNo, password: password },
      )

      localStorage.setItem('access_token', response.access_token)
      // Access token 30 dakikada dolar. Bu olmadan oturum sessizce anonime
      // düşüyor ve sohbet onaylanamayacak işlem önerileri hazırlıyordu.
      if (response.refresh_token) {
        localStorage.setItem('refresh_token', response.refresh_token)
      }
      navigate('/dashboard')
    } catch (err: any) {
      setError(err.message || 'Giriş yapılamadı. Bilgilerinizi kontrol edin.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="relative min-h-screen antialiased bg-hologram-global text-slate-300 overflow-hidden">
      {/* Logo */}
      <header className="absolute left-6 top-6 z-10 sm:left-10 sm:top-8">
        <Link to="/" className="flex items-center gap-3">
          <img src={logo} alt="MoneyFast Logo" className="h-10 sm:h-12 w-auto object-contain transition-transform duration-300 hover:scale-105" />
        </Link>
      </header>

      {/* Ana alan */}
      <main className="flex min-h-screen items-center justify-center px-5 pb-10 pt-28 sm:px-8">
        <section className="relative z-10 w-full max-w-xl rounded-[2.5rem] bg-slate-900/50 backdrop-blur-xl border border-white/10 px-7 py-10 shadow-2xl sm:px-12 sm:py-12">
          <div className="mx-auto max-w-md">
            {/* Başlık */}
            <div className="mb-9 text-center">
              <h2 className="text-3xl font-bold tracking-tight text-gradient-hero inline-block">
                MoneyFast'e Hoş Geldin
              </h2>
              <p className="mt-3 text-sm leading-6 text-slate-400">
                Kişiselleştirilmiş finansal görünümünüze güvenli şekilde erişin
              </p>
            </div>

            <form onSubmit={handleSubmit} className="space-y-5">
              {/* TC Kimlik No */}
              <div>
                <label
                  htmlFor="tcNo"
                  className="mb-2 block text-sm font-semibold text-slate-300"
                >
                  T.C. Kimlik No
                </label>

                <div className="relative">
                  <div className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-slate-500">
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                      <circle cx="12" cy="8" r="4" />
                      <path d="M4 21c0-4 3.6-7 8-7s8 3 8 7" />
                    </svg>
                  </div>

                  <input
                    id="tcNo"
                    name="tcNo"
                    type="text"
                    inputMode="numeric"
                    autoComplete="username"
                    maxLength={11}
                    value={tcNo}
                    onChange={(event) => handleTcChange(event.target.value)}
                    placeholder="11 haneli T.C. Kimlik No"
                    className="w-full rounded-2xl border border-white/10 bg-white/5 py-3.5 pl-12 pr-4 text-sm text-white outline-none transition duration-200 placeholder:text-slate-500 hover:border-white/20 focus:border-brandBlue focus:bg-white/10 focus:ring-4 focus:ring-brandBlue/20"
                  />
                </div>
              </div>

              {/* Şifre */}
              <div>
                <label
                  htmlFor="password"
                  className="mb-2 block text-sm font-semibold text-slate-300"
                >
                  Şifre
                </label>

                <div className="relative">
                  <div className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-slate-500">
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                      <rect x="5" y="10" width="14" height="10" rx="2" />
                      <path d="M8 10V7a4 4 0 0 1 8 0v3" />
                    </svg>
                  </div>

                  <input
                    id="password"
                    name="password"
                    type={showPassword ? 'text' : 'password'}
                    autoComplete="current-password"
                    value={password}
                    onChange={(event) => setPassword(event.target.value)}
                    placeholder="Şifrenizi girin"
                    className="w-full rounded-2xl border border-white/10 bg-white/5 py-3.5 pl-12 pr-12 text-sm text-white outline-none transition duration-200 placeholder:text-slate-500 hover:border-white/20 focus:border-brandBlue focus:bg-white/10 focus:ring-4 focus:ring-brandBlue/20"
                  />

                  <button
                    type="button"
                    onClick={() => setShowPassword((current) => !current)}
                    className="absolute right-4 top-1/2 -translate-y-1/2 text-slate-400 transition hover:text-white"
                  >
                    {showPassword ? (
                      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"></path>
                        <line x1="1" y1="1" x2="23" y2="23"></line>
                      </svg>
                    ) : (
                      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path>
                        <circle cx="12" cy="12" r="3"></circle>
                      </svg>
                    )}
                  </button>
                </div>
              </div>

              {/* Hesap / şifre linkleri */}
              <div className="flex items-center justify-between pt-1 text-sm">
                <Link
                  to="/register"
                  className="font-semibold text-slate-400 transition hover:text-brandBlue"
                >
                  Hesap oluştur
                </Link>

                <Link
                    to="/forgot-password"
                    className="font-semibold text-slate-400 transition hover:text-brandBlue"
                >
                    Şifremi unuttum
                </Link>
              </div>

              {/* Hata mesajı */}
              {error && (
                <div
                  role="alert"
                  className="rounded-2xl border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-400"
                >
                  {error}
                </div>
              )}

              {/* Giriş butonu */}
              <button
                type="submit"
                disabled={loading}
                className="group flex w-full items-center justify-center gap-2 rounded-2xl bg-brandBlue px-4 py-3.5 font-semibold text-white shadow-lg shadow-brandBlue/25 transition duration-200 hover:-translate-y-0.5 hover:bg-blue-600 hover:shadow-xl focus:outline-none focus:ring-4 focus:ring-brandBlue/30 disabled:opacity-70 disabled:hover:translate-y-0"
              >
                {loading ? 'Giriş Yapılıyor...' : 'Giriş Yap'}

                {!loading && (
                  <span className="transition-transform duration-200 group-hover:translate-x-1">
                    →
                  </span>
                )}
              </button>
            </form>

            {/* Güven bilgisi */}
            <div className="mt-7 flex items-center justify-center gap-2 text-xs text-slate-500">
              <svg
                width="14"
                height="14"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden="true"
              >
                <rect x="5" y="10" width="14" height="10" rx="2" />
                <path d="M8 10V7a4 4 0 0 1 8 0v3" />
              </svg>

              <span>Güvenli ve korumalı giriş</span>
            </div>
          </div>
        </section>
      </main>
    </div>
  )
}
