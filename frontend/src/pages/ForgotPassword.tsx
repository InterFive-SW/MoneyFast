import { useState } from 'react'
import type { FormEvent } from 'react'
import { Link } from 'react-router-dom'

export default function ForgotPassword() {
  const [tcNo, setTcNo] = useState('')
  const [email, setEmail] = useState('')
  const [error, setError] = useState('')

  function handleTcChange(value: string) {
    setTcNo(value.replace(/\D/g, '').slice(0, 11))
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError('')

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

    // Backend OTP / şifre yenileme entegrasyonu daha sonra eklenecek.
    console.log('Password reset code requested')
  }

  return (
    <div className="relative min-h-screen overflow-hidden bg-gradient-to-br from-slate-50 via-white to-emerald-50/50">
      {/* Arka plan */}
      <div className="pointer-events-none absolute -left-40 -top-40 h-96 w-96 rounded-full bg-emerald-200/30 blur-3xl" />
      <div className="pointer-events-none absolute -bottom-40 -right-40 h-96 w-96 rounded-full bg-teal-200/20 blur-3xl" />

      {/* Logo */}
      <header className="absolute left-6 top-6 z-10 sm:left-10 sm:top-8">
        <Link to="/login" className="flex items-center gap-3">
          <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-gradient-to-br from-emerald-400 to-teal-500 shadow-lg shadow-emerald-200/60">
            <svg
              viewBox="0 0 40 40"
              className="h-8 w-8"
              fill="none"
              aria-hidden="true"
            >
              <path
                d="M7 29V12L14.5 22L20 14.5L25.5 22L33 12V29"
                stroke="#020617"
                strokeWidth="3.2"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
              <path
                d="M9 27L16 23L22 25L31 17"
                stroke="white"
                strokeWidth="2.4"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
              <path
                d="M26.5 17H31V21.5"
                stroke="white"
                strokeWidth="2.4"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </div>

          <div>
            <div>
              <span className="text-2xl font-extrabold tracking-tight text-slate-950">
                Money
              </span>
              <span className="text-2xl font-extrabold tracking-tight text-emerald-500">
                Fast
              </span>
            </div>

            <p className="hidden text-xs font-medium tracking-wide text-slate-500 sm:block">
              Akıllı Finans Danışmanı
            </p>
          </div>
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

              <p className="mt-3 text-sm leading-6 text-slate-500">
                Bilgilerini doğrulayalım ve sana şifre yenileme kodu gönderelim.
              </p>
            </div>

            <form onSubmit={handleSubmit} className="space-y-5">
              <div>
                <label
                  htmlFor="tcNo"
                  className="mb-2 block text-sm font-semibold text-slate-700"
                >
                  T.C. Kimlik No
                </label>

                <input
                  id="tcNo"
                  type="text"
                  inputMode="numeric"
                  value={tcNo}
                  onChange={(event) => handleTcChange(event.target.value)}
                  placeholder="11 haneli T.C. Kimlik No"
                  className="w-full rounded-2xl border border-slate-200 bg-slate-50/60 px-4 py-3.5 text-sm outline-none transition placeholder:text-slate-400 hover:border-slate-300 focus:border-emerald-400 focus:bg-white focus:ring-4 focus:ring-emerald-100"
                />
              </div>

              <div>
                <label
                  htmlFor="email"
                  className="mb-2 block text-sm font-semibold text-slate-700"
                >
                  E-posta Adresi
                </label>

                <input
                  id="email"
                  type="email"
                  autoComplete="email"
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  placeholder="ornek@posta.com"
                  className="w-full rounded-2xl border border-slate-200 bg-slate-50/60 px-4 py-3.5 text-sm outline-none transition placeholder:text-slate-400 hover:border-slate-300 focus:border-emerald-400 focus:bg-white focus:ring-4 focus:ring-emerald-100"
                />
              </div>

              {error && (
                <div
                  role="alert"
                  className="rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700"
                >
                  {error}
                </div>
              )}

              <button
                type="submit"
                className="group flex w-full items-center justify-center gap-2 rounded-2xl bg-slate-950 px-4 py-3.5 font-semibold text-white shadow-lg shadow-slate-200 transition duration-200 hover:-translate-y-0.5 hover:bg-slate-800"
              >
                Kod Gönder
                <span className="transition-transform duration-200 group-hover:translate-x-1">
                  →
                </span>
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