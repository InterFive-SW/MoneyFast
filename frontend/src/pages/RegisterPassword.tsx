import { useState, useEffect } from 'react'
import type { FormEvent } from 'react'
import { Link, useNavigate, useLocation } from 'react-router-dom'
import logo from '../assets/logo-icon.png'
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
  const [showConfirmPassword, setShowConfirmPassword] = useState(false)
  const [acceptedTerms, setAcceptedTerms] = useState(false)

  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [isSuccess, setIsSuccess] = useState(false)

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

    if (!/[A-Z]/.test(password)) {
      setError('Şifreniz en az bir büyük harf içermelidir.')
      return
    }

    if (!/[a-z]/.test(password)) {
      setError('Şifreniz en az bir küçük harf içermelidir.')
      return
    }

    if (!/[0-9]/.test(password)) {
      setError('Şifreniz en az bir rakam içermelidir.')
      return
    }

    if (password !== confirmPassword) {
      setError('Şifreler birbiriyle eşleşmiyor.')
      return
    }


    // Sözleşme onayı bir SUNUM ayrıntısı değil, bir kapı. Kutu ve bu
    // kontrol bir dönem silinmişti ve kullanıcı sözleşmeyi onaylamadan
    // kayıt olabiliyordu.
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
      
      // GÜVENLİK: Kullanıcı kaydedildi fakat is_verified=False durumunda.
      // E-posta adresine doğrulama bağlantısı gönderildi. Kullanıcıyı uyarı ekranına geçiriyoruz.
      setIsSuccess(true)
    } catch (err: any) {
      setError(err.message || 'Kayıt olurken bir hata oluştu. Lütfen bilgilerinizi kontrol edin.')
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

      {/* İçerik */}
      <main className="flex min-h-screen items-center justify-center px-5 pb-10 pt-28 sm:px-8">
        <section className="relative z-10 w-full max-w-xl rounded-[2.5rem] bg-slate-900/50 backdrop-blur-xl border border-white/10 px-7 py-10 shadow-2xl sm:px-12 sm:py-12">
          {isSuccess ? (
            <div className="mx-auto max-w-md text-center">
              <div className="mx-auto mb-6 flex h-16 w-16 items-center justify-center rounded-full bg-emerald-500/20 text-emerald-400">
                <svg className="h-8 w-8" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                </svg>
              </div>
              
              <h2 className="mb-4 text-2xl font-bold text-white">
                Hesabınız Oluşturuldu!
              </h2>
              
              <p className="mb-8 text-slate-400">
                Güvenliğiniz için kayıt olduğunuz e-posta adresine bir doğrulama bağlantısı gönderildi 
                <br />
                Giriş yapabilmek için lütfen e-postanızı kontrol edin ve hesabınızı doğrulayın
              </p>

              <Link
                to="/login"
                className="inline-flex w-full items-center justify-center rounded-2xl bg-brandBlue px-4 py-3.5 font-semibold text-white transition hover:bg-blue-600"
              >
                Giriş Yap
              </Link>
            </div>
          ) : (
            <div className="mx-auto max-w-md">
              {/* Başlık */}
              <div className="mb-8 text-center flex flex-col items-center">
                <h1 className="text-3xl font-bold tracking-tight text-gradient-hero inline-block">
                  Şifre Belirleme
                </h1>
                <p className="mt-3 text-sm leading-6 text-slate-400">
                  Hesabınızın güvenliği için güçlü bir şifre oluşturun
                </p>
              </div>

            {/* Adım göstergesi */}
            <div className="mb-3 flex items-center gap-3">
              <div className="h-1.5 flex-1 rounded-full bg-brandBlue" />
              <div className="h-1.5 flex-1 rounded-full bg-brandBlue" />
            </div>

            <p className="mb-7 text-center text-xs font-medium text-slate-500">
              Adım 2 / 2
            </p>

            <form onSubmit={handleSubmit} className="space-y-5">
              {/* Şifre */}
              <div>
                <label
                  htmlFor="password"
                  className="mb-2 block text-sm font-semibold text-slate-300"
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
                    className="w-full rounded-2xl border border-white/10 bg-white/5 px-4 py-3.5 pr-20 text-sm text-white outline-none transition placeholder:text-slate-500 hover:border-white/20 focus:border-brandBlue focus:bg-white/10 focus:ring-4 focus:ring-brandBlue/20"
                  />

                  <button
                    type="button"
                    onClick={() =>
                      setShowPassword((current) => !current)
                    }
                    aria-label={showPassword ? 'Şifreyi gizle' : 'Şifreyi göster'}
                    className="absolute right-4 top-1/2 -translate-y-1/2 text-slate-400 transition hover:text-white"
                  >
                    {showPassword ? (
                      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                        <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"></path>
                        <line x1="1" y1="1" x2="23" y2="23"></line>
                      </svg>
                    ) : (
                      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                        <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path>
                        <circle cx="12" cy="12" r="3"></circle>
                      </svg>
                    )}
                  </button>
                </div>

                <p className="mt-2 text-xs text-slate-500">
                  En az 8 karakter, 1 büyük harf, 1 küçük harf ve 1 rakam kullanın.
                </p>
              </div>

              {/* Şifre tekrar */}
              <div>
                <label
                  htmlFor="confirmPassword"
                  className="mb-2 block text-sm font-semibold text-slate-300"
                >
                  Şifre Tekrar
                </label>

                <div className="relative">
                  <input
                    id="confirmPassword"
                    type={showConfirmPassword ? 'text' : 'password'}
                    autoComplete="new-password"
                    value={confirmPassword}
                    onChange={(event) =>
                      setConfirmPassword(event.target.value)
                    }
                    placeholder="Şifrenizi tekrar girin"
                    className="w-full rounded-2xl border border-white/10 bg-white/5 px-4 py-3.5 pr-20 text-sm text-white outline-none transition placeholder:text-slate-500 hover:border-white/20 focus:border-brandBlue focus:bg-white/10 focus:ring-4 focus:ring-brandBlue/20"
                  />
                  <button
                    type="button"
                    onClick={() => setShowConfirmPassword((curr) => !curr)}
                    aria-label={showConfirmPassword ? 'Şifreyi gizle' : 'Şifreyi göster'}
                    className="absolute right-4 top-1/2 -translate-y-1/2 text-slate-400 transition hover:text-white"
                  >
                    {showConfirmPassword ? (
                      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                        <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"></path>
                        <line x1="1" y1="1" x2="23" y2="23"></line>
                      </svg>
                    ) : (
                      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                        <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path>
                        <circle cx="12" cy="12" r="3"></circle>
                      </svg>
                    )}
                  </button>
                </div>
              </div>

              {/* Sözleşme */}
              <label className="flex cursor-pointer items-start gap-3 rounded-2xl border border-white/10 bg-white/5 p-4">
                <input
                  type="checkbox"
                  checked={acceptedTerms}
                  onChange={(event) => setAcceptedTerms(event.target.checked)}
                  className="mt-0.5 h-4 w-4 accent-brandBlue"
                />
                <span className="text-sm leading-5 text-slate-400">
                  <button
                    type="button"
                    className="font-semibold text-slate-300 transition hover:text-brandBlue"
                  >
                    Kullanıcı sözleşmesini
                  </button>{' '}
                  okudum ve kabul ediyorum
                </span>
              </label>

              {/* Hata */}
              {error && (
                <div
                  role="alert"
                  className="rounded-2xl border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-400"
                >
                  {error}
                </div>
              )}

              {/* Hesap oluştur */}
              <button
                type="submit"
                disabled={loading}
                className="group flex w-full items-center justify-center gap-2 rounded-2xl bg-brandBlue px-4 py-3.5 font-semibold text-white shadow-lg shadow-brandBlue/25 transition duration-200 hover:-translate-y-0.5 hover:bg-blue-600 focus:outline-none focus:ring-4 focus:ring-brandBlue/30 disabled:opacity-70 disabled:hover:translate-y-0"
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
                className="text-sm font-semibold text-slate-400 transition hover:text-brandBlue"
              >
                ← Önceki adıma dön
              </Link>
            </div>
            </div>
          )}
        </section>
      </main>
    </div>
  )
}
