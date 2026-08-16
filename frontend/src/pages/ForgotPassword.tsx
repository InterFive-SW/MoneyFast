import { useState } from 'react'
import type { FormEvent } from 'react'
import { Link } from 'react-router-dom'
import logo from '../assets/logo.png'
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
      setError('Lütfen tüm alanları doldurun.')
      return
    }

    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      setError('Lütfen geçerli bir e-posta adresi girin.')
      return
    }

    if (tcNo.length !== 11) {
      setError('T.C. Kimlik No 11 haneli olmalıdır.')
      return
    }

    setLoading(true)
    try {
      await api.post('/api/auth/forgot-password', {
        email
      })
      
      setSuccess('Şifre yenileme bağlantısı e-posta adresinize gönderildi.')
    } catch (err: any) {
      setError(err.message || 'Bir hata oluştu. Lütfen bilgilerinizi kontrol edin.')
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
            <div className="mb-9 text-center">
              <div className="mb-4 inline-flex items-center gap-2 rounded-full bg-emerald-50 px-3 py-1.5 text-xs font-semibold text-emerald-700">
                <span className="h-2 w-2 rounded-full bg-emerald-500" />
                Şifre Yenileme
              </div>

              <h1 className="text-3xl font-bold tracking-tight text-slate-950">
                Şifreni mi unuttun?
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
                  className="block text-sm font-medium text-slate-700"
                >
                  T.C. Kimlik No
                </label>
                <input
                  type="text"
                  id="tcNo"
                  maxLength={11}
                  value={tcNo}
                  onChange={(e) => handleTcChange(e.target.value)}
                  className="block w-full rounded-xl border border-slate-200 bg-white px-4 py-3 text-slate-900 transition-colors placeholder:text-slate-400 focus:border-slate-400 focus:outline-none focus:ring-4 focus:ring-slate-100"
                  placeholder="11 haneli T.C. kimlik numaranız"
                />
              </div>

              {/* Email Input */}
              <div className="space-y-1.5 text-left">
                <label
                  htmlFor="email"
                  className="block text-sm font-medium text-slate-700"
                >
                  E-posta Adresi
                </label>
                <input
                  type="email"
                  id="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="block w-full rounded-xl border border-slate-200 bg-white px-4 py-3 text-slate-900 transition-colors placeholder:text-slate-400 focus:border-slate-400 focus:outline-none focus:ring-4 focus:ring-slate-100"
                  placeholder="ornek@email.com"
                />
              </div>

              {/* Şifre Sıfırla Butonu */}
              <button
                type="submit"
                disabled={loading}
                className="group flex w-full items-center justify-center gap-2 rounded-2xl bg-slate-950 px-4 py-3.5 font-semibold text-white shadow-lg shadow-slate-200 transition duration-200 hover:-translate-y-0.5 hover:bg-slate-800 focus:outline-none focus:ring-4 focus:ring-slate-200 disabled:opacity-70 disabled:hover:translate-y-0"
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
                className="text-sm font-semibold text-slate-600 transition hover:text-emerald-600"
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