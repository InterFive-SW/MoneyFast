import { useState } from 'react'
import type { FormEvent } from 'react'
import { Link } from 'react-router-dom'
import logo from '../assets/logo-icon.png'
import { api } from '../api/client'

export default function ForgotPassword() {
  const [tcNo, setTcNo] = useState('')
  const [email, setEmail] = useState('')
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [loading, setLoading] = useState(false)

  function handleTcChange(value: string) {
    setTcNo(value.replace(/\D/g, '').slice(0, 11))
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError('')
    setSuccess('')

    if (!tcNo || !email.trim()) {
      setError('Lütfen tüm alanları doldurun')
      return
    }

    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      setError('Lütfen geçerli bir e-posta adresi girin')
      return
    }

    if (tcNo.length !== 11) {
      setError('T.C. Kimlik No 11 haneli olmalıdır')
      return
    }

    setLoading(true)
    try {
      await api.post('/api/auth/forgot-password', {
        tc_no: tcNo,
        email: email
      })
      
      setSuccess('Şifre yenileme bağlantısı e-posta adresinize gönderildi')
    } catch (err: any) {
      setError(err.message || 'Bir hata oluştu. Lütfen bilgilerinizi kontrol edin')
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
          <div className="mx-auto max-w-md">
            <div className="mb-9 text-center flex flex-col items-center">
              <h1 className="text-3xl font-bold tracking-tight text-gradient-hero inline-block">
                Şifrenizi Sıfırlayın
              </h1>
            </div>
            {success && (
              <div className="mt-4 rounded-xl border border-emerald-500/10 bg-emerald-500/10 p-4 text-sm text-emerald-600">
                {success}
              </div>
            )}

            {error && (
              <div className="mt-4 rounded-xl border border-red-500/10 bg-red-500/10 p-4 text-sm text-red-600">
                {error}
              </div>
            )}

            <form onSubmit={handleSubmit} className="mt-8 space-y-6">
              {/* TC Kimlik No Input */}
              <div className="space-y-1.5 text-left">
                <label
                  htmlFor="tcNo"
                  className="block text-sm font-medium text-slate-300"
                >
                  T.C. Kimlik No
                </label>
                <input
                  type="text"
                  id="tcNo"
                  maxLength={11}
                  value={tcNo}
                  onChange={(e) => handleTcChange(e.target.value)}
                  className="block w-full rounded-xl border border-white/10 bg-white/5 px-4 py-3 text-white transition-colors placeholder:text-slate-500 focus:border-brandBlue focus:outline-none focus:ring-4 focus:ring-brandBlue/20"
                  placeholder="11 haneli T.C. Kimlik No"
                />
              </div>

              {/* Email Input */}
              <div className="space-y-1.5 text-left">
                <label
                  htmlFor="email"
                  className="block text-sm font-medium text-slate-300"
                >
                  E-posta Adresi
                </label>
                <input
                  type="email"
                  id="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="block w-full rounded-xl border border-white/10 bg-white/5 px-4 py-3 text-white transition-colors placeholder:text-slate-500 focus:border-brandBlue focus:outline-none focus:ring-4 focus:ring-brandBlue/20"
                  placeholder="ornek@eposta.com"
                />
              </div>

              {/* Şifre Sıfırla Butonu */}
              <button
                type="submit"
                disabled={loading}
                className="group flex w-full items-center justify-center gap-2 rounded-2xl bg-brandBlue px-4 py-3.5 font-semibold text-white shadow-lg shadow-brandBlue/20 transition duration-200 hover:-translate-y-0.5 hover:bg-brandBlue/90 focus:outline-none focus:ring-4 focus:ring-brandBlue/20 disabled:opacity-70 disabled:hover:translate-y-0"
              >
                {loading ? 'Gönderiliyor...' : 'Şifremi Sıfırla'}

                {!loading && (
                  <span className="transition-transform duration-200 group-hover:translate-x-1">
                    →
                  </span>
                )}
              </button>
            </form>

            <div className="mt-7 text-center">
              <Link
                to="/login"
                className="text-sm font-semibold text-slate-400 transition hover:text-white"
              >
                ← Giriş ekranına dön
              </Link>
            </div>
          </div>
        </section>
      </main>
    </div>
  )
}
