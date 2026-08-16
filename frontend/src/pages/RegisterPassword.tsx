import { useState, useEffect } from 'react'
import type { FormEvent } from 'react'
import { Link, useNavigate, useLocation } from 'react-router-dom'
import logo from '../assets/logo.png'
import { api } from '../api/client'

export default function RegisterPassword() {
  const navigate = useNavigate()
  const location = useLocation()
  
  // State eksikse, 1. adıma geri dön
  useEffect(() => {
    if (!location.state) {
      navigate('/register')
    }
  }, [location, navigate])

  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [acceptedTerms, setAcceptedTerms] = useState(false)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError('')

    if (!password || !confirmPassword) {
      setError('Lütfen şifre alanlarını doldurun.')
      return
    }

    if (password.length < 8) {
      setError('Şifreniz en az 8 karakter olmalıdır.')
      return
    }

    if (password !== confirmPassword) {
      setError('Şifreler birbiriyle eşleşmiyor.')
      return
    }

    if (!acceptedTerms) {
      setError('Devam etmek için kullanıcı sözleşmesini onaylamalısınız.')
      return
    }

    const { name, surname, tcNo, phone, email } = location.state || {}

    setLoading(true)
    try {
      await api.post('/api/auth/register', {
        first_name: name,
        last_name: surname,
        tc_no: tcNo,
        phone_number: phone?.startsWith('+') ? phone : '+90' + phone,
        email: email,
        password: password
      })
      
      // Şimdilik başarılı kayıt sonrası login ekranına dön.
      navigate('/login')
    } catch (err: any) {
      setError(err.message || 'Kayıt olurken bir hata oluştu. Lütfen bilgilerinizi kontrol edin.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="relative min-h-screen overflow-hidden bg-gradient-to-br from-slate-50 via-white to-emerald-50/50">
      {/* Arka plan */}
      <div className="pointer-events-none absolute -left-40 -top-40 h-96 w-96 rounded-full bg-emerald-200/30 blur-3xl" />
      <div className="pointer-events-none absolute -bottom-40 -right-40 h-96 w-96 rounded-full bg-teal-200/20 blur-3xl" />

      {/* Logo */}
      <header className="absolute left-6 top-6 z-10 sm:left-10 sm:top-8">
        <Link to="/" className="flex items-center gap-3">
          <img src={logo} alt="MoneyFast Logo" className="h-16 w-auto object-contain transition-transform duration-300 hover:scale-105" />
        </Link>
      </header>

      {/* İçerik */}
      <main className="flex min-h-screen items-center justify-center px-5 pb-10 pt-28 sm:px-8">
        <section className="w-full max-w-xl rounded-[2.5rem] border border-slate-200/80 bg-white px-7 py-10 shadow-[0_24px_70px_-30px_rgba(15,23,42,0.3)] sm:px-12 sm:py-12">
          <div className="mx-auto max-w-md">
            {/* Başlık */}
            <div className="mb-8 text-center">
              <div className="mb-4 inline-flex items-center gap-2 rounded-full bg-emerald-50 px-3 py-1.5 text-xs font-semibold text-emerald-700">
                <span className="h-2 w-2 rounded-full bg-emerald-500" />
                Hesap Oluştur
              </div>

              <h1 className="text-3xl font-bold tracking-tight text-slate-950">
                Şifreni oluştur
              </h1>

              <p className="mt-3 text-sm leading-6 text-slate-500">
                MoneyFast hesabın için güvenli bir şifre belirle.
              </p>
            </div>

            {/* Adım göstergesi */}
            <div className="mb-3 flex items-center gap-3">
              <div className="h-1.5 flex-1 rounded-full bg-emerald-400" />
              <div className="h-1.5 flex-1 rounded-full bg-emerald-400" />
            </div>

            <p className="mb-7 text-center text-xs font-medium text-slate-400">
              Adım 2 / 2
            </p>

            <form onSubmit={handleSubmit} className="space-y-5">
              {/* Şifre */}
              <div>
                <label
                  htmlFor="password"
                  className="mb-2 block text-sm font-semibold text-slate-700"
                >
                  Şifre
                </label>

                <div className="relative">
                  <input
                    id="password"
                    type={showPassword ? 'text' : 'password'}
                    autoComplete="new-password"
                    value={password}
                    onChange={(event) => setPassword(event.target.value)}
                    placeholder="Şifrenizi oluşturun"
                    className="w-full rounded-2xl border border-slate-200 bg-slate-50/60 px-4 py-3.5 pr-20 text-sm text-slate-950 outline-none transition placeholder:text-slate-400 hover:border-slate-300 focus:border-emerald-400 focus:bg-white focus:ring-4 focus:ring-emerald-100"
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

                <p className="mt-2 text-xs text-slate-400">
                  En az 8 karakter kullan.
                </p>
              </div>

              {/* Şifre tekrar */}
              <div>
                <label
                  htmlFor="confirmPassword"
                  className="mb-2 block text-sm font-semibold text-slate-700"
                >
                  Şifre Tekrar
                </label>

                <input
                  id="confirmPassword"
                  type={showPassword ? 'text' : 'password'}
                  autoComplete="new-password"
                  value={confirmPassword}
                  onChange={(event) =>
                    setConfirmPassword(event.target.value)
                  }
                  placeholder="Şifrenizi tekrar girin"
                  className="w-full rounded-2xl border border-slate-200 bg-slate-50/60 px-4 py-3.5 text-sm text-slate-950 outline-none transition placeholder:text-slate-400 hover:border-slate-300 focus:border-emerald-400 focus:bg-white focus:ring-4 focus:ring-emerald-100"
                />
              </div>

              {/* Sözleşme */}
              <label className="flex cursor-pointer items-start gap-3 rounded-2xl border border-slate-100 bg-slate-50/60 p-4">
                <input
                  type="checkbox"
                  checked={acceptedTerms}
                  onChange={(event) =>
                    setAcceptedTerms(event.target.checked)
                  }
                  className="mt-0.5 h-4 w-4 accent-emerald-500"
                />

                <span className="text-sm leading-5 text-slate-500">
                  <button
                    type="button"
                    className="font-semibold text-slate-700 transition hover:text-emerald-600"
                  >
                    Kullanıcı sözleşmesini
                  </button>{' '}
                  okudum ve kabul ediyorum.
                </span>
              </label>

              {/* Hata */}
              {error && (
                <div
                  role="alert"
                  className="rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700"
                >
                  {error}
                </div>
              )}

              {/* Hesap oluştur */}
              <button
                type="submit"
                disabled={loading}
                className="group flex w-full items-center justify-center gap-2 rounded-2xl bg-slate-950 px-4 py-3.5 font-semibold text-white shadow-lg shadow-slate-200 transition duration-200 hover:-translate-y-0.5 hover:bg-slate-800 disabled:opacity-70 disabled:hover:translate-y-0"
              >
                {loading ? 'Hesap Oluşturuluyor...' : 'Hesap Oluştur'}

                {!loading && (
                  <span className="transition-transform duration-200 group-hover:translate-x-1">
                    →
                  </span>
                )}
              </button>
            </form>

            <div className="mt-7 text-center">
              <Link
                to="/register"
                className="text-sm font-semibold text-slate-600 transition hover:text-emerald-600"
              >
                ← Önceki adıma dön
              </Link>
            </div>
          </div>
        </section>
      </main>
    </div>
  )
}