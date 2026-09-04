import { useState, useEffect } from 'react'
import type { FormEvent } from 'react'
import { Link, useSearchParams, useNavigate } from 'react-router-dom'
import logo from '../assets/logo-icon.png'
import { api } from '../api/client'

export default function ResetPassword() {
  const [searchParams] = useSearchParams()
  const token = searchParams.get('token')
  const navigate = useNavigate()

  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [showConfirmPassword, setShowConfirmPassword] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!token) {
      setError('Geçersiz veya eksik şifre sıfırlama bağlantısı')
    }
  }, [token])

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError('')
    setSuccess('')

    if (!token) {
      setError('Geçersiz bağlantı')
      return
    }

    if (!password || !confirmPassword) {
      setError('Lütfen şifre alanlarını doldurun')
      return
    }

    if (password.length < 8) {
      setError('Şifreniz en az 8 karakter olmalıdır')
      return
    }

    if (!/[A-Z]/.test(password)) {
      setError('Şifreniz en az bir büyük harf içermelidir')
      return
    }

    if (!/[a-z]/.test(password)) {
      setError('Şifreniz en az bir küçük harf içermelidir')
      return
    }

    if (!/[0-9]/.test(password)) {
      setError('Şifreniz en az bir rakam içermelidir')
      return
    }

    if (password !== confirmPassword) {
      setError('Şifreler birbiriyle eşleşmiyor')
      return
    }

    setLoading(true)
    try {
      await api.post('/api/auth/reset-password', {
        token,
        new_password: password
      })
      
      setSuccess('Şifreniz başarıyla güncellendi')
      setTimeout(() => {
        navigate('/login')
      }, 3000)
    } catch (err: any) {
      setError(err.message || 'Şifre sıfırlanırken bir hata oluştu, bağlantının süresi dolmuş olabilir')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="relative min-h-screen antialiased bg-hologram-global text-slate-300 overflow-hidden">
      <header className="absolute left-6 top-6 z-10 sm:left-10 sm:top-8">
        <Link to="/" className="flex items-center gap-3">
          <img src={logo} alt="MoneyFast Logo" className="h-10 sm:h-12 w-auto object-contain transition-transform duration-300 hover:scale-105" />
        </Link>
      </header>

      <main className="flex min-h-screen items-center justify-center px-5 pb-10 pt-28 sm:px-8">
        <section className="relative z-10 w-full max-w-xl rounded-[2.5rem] bg-slate-900/50 backdrop-blur-xl border border-white/10 px-7 py-10 shadow-2xl sm:px-12 sm:py-12">
          <div className="mx-auto max-w-md">
            <div className="mb-9 text-center flex flex-col items-center">
              <h1 className="text-3xl font-bold tracking-tight text-gradient-hero inline-block">
                Yeni Şifre
              </h1>
            </div>

            {success && (
              <div className="mt-4 rounded-xl border border-emerald-500/10 bg-emerald-500/10 p-4 text-sm text-emerald-600 text-center">
                <p>{success}</p>
                <p className="mt-1 text-xs">Giriş sayfasına yönlendiriliyorsunuz...</p>
              </div>
            )}

            {error && (
              <div className="mt-4 rounded-xl border border-red-500/10 bg-red-500/10 p-4 text-sm text-red-600">
                {error}
              </div>
            )}

            {!success && (
              <form onSubmit={handleSubmit} className="mt-8 space-y-6">
                <div>
                  <label htmlFor="password" className="mb-2 block text-sm font-semibold text-slate-300">
                    Yeni Şifre
                  </label>
                  <div className="relative">
                    <input
                      id="password"
                      type={showPassword ? 'text' : 'password'}
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      placeholder="Yeni şifrenizi girin"
                      className="w-full rounded-2xl border border-white/10 bg-white/5 px-4 py-3.5 pr-20 text-sm text-white outline-none transition placeholder:text-slate-500 hover:border-white/20 focus:border-brandBlue focus:bg-white/10 focus:ring-4 focus:ring-brandBlue/20"
                    />
                    <button
                      type="button"
                      onClick={() => setShowPassword((curr) => !curr)}
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
                  <p className="mt-2 text-xs text-slate-500">
                    En az 8 karakter, 1 büyük harf, 1 küçük harf ve 1 rakam kullanın
                  </p>
                </div>

                <div>
                  <label htmlFor="confirmPassword" className="mb-2 block text-sm font-semibold text-slate-300">
                    Şifre Tekrar
                  </label>
                  <div className="relative">
                    <input
                      id="confirmPassword"
                      type={showConfirmPassword ? 'text' : 'password'}
                      value={confirmPassword}
                      onChange={(e) => setConfirmPassword(e.target.value)}
                      placeholder="Şifrenizi tekrar girin"
                      className="w-full rounded-2xl border border-white/10 bg-white/5 px-4 py-3.5 pr-20 text-sm text-white outline-none transition placeholder:text-slate-500 hover:border-white/20 focus:border-brandBlue focus:bg-white/10 focus:ring-4 focus:ring-brandBlue/20"
                    />
                    <button
                      type="button"
                      onClick={() => setShowConfirmPassword((curr) => !curr)}
                      className="absolute right-4 top-1/2 -translate-y-1/2 text-slate-400 transition hover:text-white"
                    >
                      {showConfirmPassword ? (
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

                <button
                  type="submit"
                  disabled={loading || !token}
                  className="group flex w-full items-center justify-center gap-2 rounded-2xl bg-brandBlue px-4 py-3.5 font-semibold text-white shadow-lg shadow-brandBlue/20 transition duration-200 hover:-translate-y-0.5 hover:bg-brandBlue/90 focus:outline-none focus:ring-4 focus:ring-brandBlue/20 disabled:opacity-70 disabled:hover:translate-y-0"
                >
                  {loading ? 'Kaydediliyor...' : 'Şifreyi Güncelle'}
                  {!loading && (
                    <span className="transition-transform duration-200 group-hover:translate-x-1">→</span>
                  )}
                </button>
              </form>
            )}

            <div className="mt-7 text-center">
              <Link to="/login" className="text-sm font-semibold text-slate-400 transition hover:text-white">
                ← Giriş ekranına dön
              </Link>
            </div>
          </div>
        </section>
      </main>
    </div>
  )
}
