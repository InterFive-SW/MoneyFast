import { useState } from 'react'
import type { FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import logo from '../assets/logo.png'

export default function Register() {
  const navigate = useNavigate()

  const [name, setName] = useState('')
  const [surname, setSurname] = useState('')
  const [tcNo, setTcNo] = useState('')
  const [phone, setPhone] = useState('')
  const [email, setEmail] = useState('')
  const [error, setError] = useState('')

  function handleTcChange(value: string) {
    setTcNo(value.replace(/\D/g, '').slice(0, 11))
  }

  function handlePhoneChange(value: string) {
    setPhone(value.replace(/\D/g, '').slice(0, 10))
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError('')

    if (!name.trim() || !surname.trim() || !tcNo || !phone || !email.trim()) {
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

    if (phone.length !== 10) {
      setError('Telefon numarası 10 haneli olmalıdır.')
      return
    }

    // İkinci kayıt adımına geçerken verileri state olarak gönder
    navigate('/register/password', { 
      state: { 
        name, 
        surname, 
        tcNo, 
        phone, 
        email 
      } 
    })
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
            <div className="mb-8 text-center">
              <div className="mb-4 inline-flex items-center gap-2 rounded-full bg-emerald-50 px-3 py-1.5 text-xs font-semibold text-emerald-700">
                <span className="h-2 w-2 rounded-full bg-emerald-500" />
                Hesap Oluştur
              </div>

              <h1 className="text-3xl font-bold tracking-tight text-slate-950">
                MoneyFast'e hoş geldin
              </h1>

              <p className="mt-3 text-sm leading-6 text-slate-500">
                Hesabını oluşturmaya başlamak için bilgilerini gir.
              </p>
            </div>

            {/* Adım göstergesi */}
            <div className="mb-7 flex items-center gap-3">
              <div className="h-1.5 flex-1 rounded-full bg-emerald-400" />
              <div className="h-1.5 flex-1 rounded-full bg-slate-200" />
            </div>

            <p className="mb-6 text-center text-xs font-medium text-slate-400">
              Adım 1 / 2
            </p>

            <form onSubmit={handleSubmit} className="space-y-4">
              {/* Ad */}
              <div>
                <label
                  htmlFor="name"
                  className="mb-2 block text-sm font-semibold text-slate-700"
                >
                  Ad
                </label>

                <input
                  id="name"
                  type="text"
                  autoComplete="given-name"
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                  placeholder="Adınızı girin"
                  className="w-full rounded-2xl border border-slate-200 bg-slate-50/60 px-4 py-3.5 text-sm text-slate-950 outline-none transition placeholder:text-slate-400 hover:border-slate-300 focus:border-emerald-400 focus:bg-white focus:ring-4 focus:ring-emerald-100"
                />
              </div>

              {/* Soyad */}
              <div>
                <label
                  htmlFor="surname"
                  className="mb-2 block text-sm font-semibold text-slate-700"
                >
                  Soyad
                </label>

                <input
                  id="surname"
                  type="text"
                  autoComplete="family-name"
                  value={surname}
                  onChange={(event) => setSurname(event.target.value)}
                  placeholder="Soyadınızı girin"
                  className="w-full rounded-2xl border border-slate-200 bg-slate-50/60 px-4 py-3.5 text-sm text-slate-950 outline-none transition placeholder:text-slate-400 hover:border-slate-300 focus:border-emerald-400 focus:bg-white focus:ring-4 focus:ring-emerald-100"
                />
              </div>

              {/* TC */}
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
                  autoComplete="off"
                  value={tcNo}
                  onChange={(event) => handleTcChange(event.target.value)}
                  placeholder="11 haneli T.C. Kimlik No"
                  className="w-full rounded-2xl border border-slate-200 bg-slate-50/60 px-4 py-3.5 text-sm text-slate-950 outline-none transition placeholder:text-slate-400 hover:border-slate-300 focus:border-emerald-400 focus:bg-white focus:ring-4 focus:ring-emerald-100"
                />
              </div>

              {/* E-posta */}
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
                  className="w-full rounded-2xl border border-slate-200 bg-slate-50/60 px-4 py-3.5 text-sm text-slate-950 outline-none transition placeholder:text-slate-400 hover:border-slate-300 focus:border-emerald-400 focus:bg-white focus:ring-4 focus:ring-emerald-100"
                />
              </div>

              {/* Telefon */}
              <div>
                <label
                  htmlFor="phone"
                  className="mb-2 block text-sm font-semibold text-slate-700"
                >
                  Telefon Numarası
                </label>

                <div className="flex">
                  <div className="flex items-center rounded-l-2xl border border-r-0 border-slate-200 bg-slate-100 px-4 text-sm font-medium text-slate-600">
                    +90
                  </div>

                  <input
                    id="phone"
                    type="tel"
                    inputMode="numeric"
                    autoComplete="tel"
                    value={phone}
                    onChange={(event) => handlePhoneChange(event.target.value)}
                    placeholder="5XX XXX XX XX"
                    className="w-full rounded-r-2xl border border-slate-200 bg-slate-50/60 px-4 py-3.5 text-sm text-slate-950 outline-none transition placeholder:text-slate-400 hover:border-slate-300 focus:border-emerald-400 focus:bg-white focus:ring-4 focus:ring-emerald-100"
                  />
                </div>
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
                className="group mt-2 flex w-full items-center justify-center gap-2 rounded-2xl bg-slate-950 px-4 py-3.5 font-semibold text-white shadow-lg shadow-slate-200 transition duration-200 hover:-translate-y-0.5 hover:bg-slate-800"
              >
                Devam
                <span className="transition-transform duration-200 group-hover:translate-x-1">
                  →
                </span>
              </button>
            </form>

            <div className="mt-7 text-center">
              <span className="text-sm text-slate-500">
                Zaten hesabın var mı?{' '}
              </span>

              <Link
                to="/login"
                className="text-sm font-semibold text-slate-700 transition hover:text-emerald-600"
              >
                Giriş yap
              </Link>
            </div>
          </div>
        </section>
      </main>
    </div>
  )
}