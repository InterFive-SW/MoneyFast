import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import logo from '../assets/logo.png'
import { api } from '../api/client'

export default function VerifyEmail() {
  const [searchParams] = useSearchParams()
  const token = searchParams.get('token')
  const [status, setStatus] = useState<'loading' | 'success' | 'error'>('loading')
  const [message, setMessage] = useState('')

  useEffect(() => {
    if (!token) {
      setStatus('error')
      setMessage('Geçersiz veya eksik doğrulama bağlantısı.')
      return
    }

    let isMounted = true
    
    // GÜVENLİK: URL'den alınan token ile backend üzerinden doğrulama işlemi gerçekleştiriliyor.
    api.post('/api/auth/verify-email', { token })
      .then((res: any) => {
        if (isMounted) {
          setStatus('success')
          setMessage(res.message || 'Hesabınız başarıyla doğrulandı. Şimdi giriş yapabilirsiniz.')
        }
      })
      .catch((err: any) => {
        if (isMounted) {
          setStatus('error')
          setMessage(err.message || 'Hesap doğrulanırken bir hata oluştu. Bağlantının süresi dolmuş olabilir.')
        }
      })

    return () => {
      isMounted = false
    }
  }, [token])

  return (
    <div className="relative min-h-screen overflow-hidden bg-slate-950">
      {/* Animated background blobs */}
      <div className="pointer-events-none absolute -left-40 top-20 h-96 w-96 rounded-full bg-brandBlue/20 blur-[100px]" />
      <div className="pointer-events-none absolute -bottom-40 -right-40 h-96 w-96 rounded-full bg-emerald-500/10 blur-[100px]" />

      {/* Logo */}
      <header className="absolute left-6 top-6 z-10 sm:left-10 sm:top-8">
        <Link to="/" className="flex items-center gap-3">
          <img src={logo} alt="MoneyFast Logo" className="h-20 sm:h-28 w-auto object-contain transition-transform duration-300 hover:scale-105" />
        </Link>
      </header>

      {/* İçerik */}
      <main className="flex min-h-screen items-center justify-center px-5 pb-10 pt-28 sm:px-8">
        <section className="w-full max-w-xl rounded-[2.5rem] border border-white/10 bg-slate-900/50 px-7 py-10 shadow-[0_24px_70px_-30px_rgba(0,0,0,0.5)] backdrop-blur-xl sm:px-12 sm:py-12">
          <div className="mx-auto max-w-md text-center">
            {status === 'loading' && (
              <>
                <div className="mx-auto mb-6 flex h-16 w-16 animate-pulse items-center justify-center rounded-full bg-slate-800 text-slate-400">
                  <div className="h-6 w-6 rounded-full border-4 border-slate-500 border-t-brandBlue animate-spin" />
                </div>
                <h2 className="mb-4 text-2xl font-bold text-white">Doğrulanıyor...</h2>
                <p className="text-slate-400">Hesabınız onaylanıyor, lütfen bekleyin.</p>
              </>
            )}

            {status === 'success' && (
              <>
                <div className="mx-auto mb-6 flex h-16 w-16 items-center justify-center rounded-full bg-emerald-500/20 text-emerald-400">
                  <svg className="h-8 w-8" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                  </svg>
                </div>
                <h2 className="mb-4 text-2xl font-bold text-white">Doğrulama Başarılı</h2>
                <p className="mb-8 text-slate-400">{message}</p>
                <Link
                  to="/login"
                  className="inline-flex w-full items-center justify-center rounded-2xl bg-brandBlue px-4 py-3.5 font-semibold text-white shadow-lg shadow-brandBlue/20 transition hover:-translate-y-0.5 hover:bg-brandBlue/90"
                >
                  Giriş Yap
                </Link>
              </>
            )}

            {status === 'error' && (
              <>
                <div className="mx-auto mb-6 flex h-16 w-16 items-center justify-center rounded-full bg-red-500/20 text-red-400">
                  <svg className="h-8 w-8" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </div>
                <h2 className="mb-4 text-2xl font-bold text-white">Doğrulama Başarısız</h2>
                <p className="mb-8 text-slate-400">{message}</p>
                <div className="flex flex-col gap-3">
                  <Link
                    to="/login"
                    className="inline-flex w-full items-center justify-center rounded-2xl border border-white/10 bg-white/5 px-4 py-3.5 font-semibold text-white transition hover:bg-white/10"
                  >
                    Giriş Ekranına Dön
                  </Link>
                </div>
              </>
            )}
          </div>
        </section>
      </main>
    </div>
  )
}
