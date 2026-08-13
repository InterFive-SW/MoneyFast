import { useState } from 'react'
import type { FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import logo from '../assets/logo.png'
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
      const response = await api.post<{ access_token: string }>('/api/v1/auth/login', {
        tc_no: tcNo,
        password: password,
      })
      
      localStorage.setItem('access_token', response.access_token)
      navigate('/dashboard')
    } catch (err: any) {
      setError(err.message || 'Giriş yapılamadı. Bilgilerinizi kontrol edin.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="relative min-h-screen overflow-hidden bg-gradient-to-br from-slate-50 via-white to-emerald-50/50">
      {/* Hafif arka plan efektleri */}
      <div className="pointer-events-none absolute -left-40 -top-40 h-96 w-96 rounded-full bg-emerald-200/30 blur-3xl" />

      <div className="pointer-events-none absolute -bottom-40 -right-40 h-96 w-96 rounded-full bg-teal-200/20 blur-3xl" />

      {/* Logo */}
      <header className="absolute left-6 top-6 z-10 sm:left-10 sm:top-8">
  <Link to="/" className="flex items-center gap-3">
          <img src={logo} alt="MoneyFast Logo" className="h-16 w-auto object-contain transition-transform duration-300 hover:scale-105" />
        </Link>
</header>

      {/* Ana alan */}
      <main className="flex min-h-screen items-center justify-center px-5 pb-10 pt-28 sm:px-8">
        <section className="w-full max-w-xl rounded-[2.5rem] border border-slate-200/80 bg-white px-7 py-10 shadow-[0_24px_70px_-30px_rgba(15,23,42,0.3)] sm:px-12 sm:py-12">
          <div className="mx-auto max-w-md">
            {/* Başlık */}
            <div className="mb-9 text-center">
              <div className="mb-4 inline-flex items-center gap-2 rounded-full bg-emerald-50 px-3 py-1.5 text-xs font-semibold text-emerald-700">
                <span className="h-2 w-2 rounded-full bg-emerald-500" />
                Güvenli Giriş
              </div>

              <h2 className="text-3xl font-bold tracking-tight text-slate-950">
                Hoş geldin 👋
              </h2>

              <p className="mt-3 text-sm leading-6 text-slate-500">
                MoneyFast hesabına giriş yaparak finansal görünümüne eriş.
              </p>
            </div>

            <form onSubmit={handleSubmit} className="space-y-5">
              {/* TC Kimlik No */}
              <div>
                <label
                  htmlFor="tcNo"
                  className="mb-2 block text-sm font-semibold text-slate-700"
                >
                  T.C. Kimlik No
                </label>

                <div className="relative">
                  <div className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-slate-400">
                    <svg
                      width="20"
                      height="20"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="1.8"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      aria-hidden="true"
                    >
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
                    onChange={(event) =>
                      handleTcChange(event.target.value)
                    }
                    placeholder="11 haneli T.C. Kimlik No"
                    className="w-full rounded-2xl border border-slate-200 bg-slate-50/60 py-3.5 pl-12 pr-4 text-sm text-slate-950 outline-none transition duration-200 placeholder:text-slate-400 hover:border-slate-300 focus:border-emerald-400 focus:bg-white focus:ring-4 focus:ring-emerald-100"
                  />
                </div>
              </div>

              {/* Şifre */}
              <div>
                <label
                  htmlFor="password"
                  className="mb-2 block text-sm font-semibold text-slate-700"
                >
                  Şifre
                </label>

                <div className="relative">
                  <div className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-slate-400">
                    <svg
                      width="20"
                      height="20"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="1.8"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      aria-hidden="true"
                    >
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
                    onChange={(event) =>
                      setPassword(event.target.value)
                    }
                    placeholder="Şifrenizi girin"
                    className="w-full rounded-2xl border border-slate-200 bg-slate-50/60 py-3.5 pl-12 pr-20 text-sm text-slate-950 outline-none transition duration-200 placeholder:text-slate-400 hover:border-slate-300 focus:border-emerald-400 focus:bg-white focus:ring-4 focus:ring-emerald-100"
                  />

                  <button
                    type="button"
                    onClick={() =>
                      setShowPassword((current) => !current)
                    }
                    className="absolute right-4 top-1/2 -translate-y-1/2 text-xs font-semibold text-slate-500 transition hover:text-emerald-600"
                  >
                    {showPassword ? 'Gizle' : 'Göster'}
                  </button>
                </div>
              </div>

              {/* Hesap / şifre linkleri */}
              <div className="flex items-center justify-between pt-1 text-sm">
                <Link
                  to="/register"
                  className="font-semibold text-slate-600 transition hover:text-emerald-600"
                >
                  Hesap oluştur
                </Link>

                <Link
                    to="/forgot-password"
                    className="font-semibold text-slate-600 transition hover:text-emerald-600"
                >
                    Şifremi unuttum
                </Link>
              </div>

              {/* Hata mesajı */}
              {error && (
                <div
                  role="alert"
                  className="rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700"
                >
                  {error}
                </div>
              )}

              {/* Giriş butonu */}
              <button
                type="submit"
                disabled={loading}
                className="group flex w-full items-center justify-center gap-2 rounded-2xl bg-slate-950 px-4 py-3.5 font-semibold text-white shadow-lg shadow-slate-200 transition duration-200 hover:-translate-y-0.5 hover:bg-slate-800 hover:shadow-xl focus:outline-none focus:ring-4 focus:ring-slate-200 disabled:opacity-70 disabled:hover:translate-y-0"
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
            <div className="mt-7 flex items-center justify-center gap-2 text-xs text-slate-400">
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