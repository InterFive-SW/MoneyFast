import { useState } from 'react'
import type { FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import logo from '../assets/logo-inline.png'

export default function Register() {
  const navigate = useNavigate()

  const [name, setName] = useState('')
  const [surname, setSurname] = useState('')
  const [tcNo, setTcNo] = useState('')
  const [phone, setPhone] = useState('')
  const [email, setEmail] = useState('')
  const [acceptTerms, setAcceptTerms] = useState(false)
  const [acceptKVKK, setAcceptKVKK] = useState(false)
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

    if (!acceptTerms || !acceptKVKK) {
      setError('Lütfen Kullanıcı Sözleşmesi ve KVKK metinlerini onaylayın.')
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
    <div className="relative min-h-screen overflow-hidden bg-slate-950 text-slate-300">
      {/* Animated Background Blobs */}
      <div className="absolute top-[-10%] left-[-10%] w-[40%] h-[40%] rounded-full bg-brandBlue/20 blur-[120px] mix-blend-screen animate-blob" />
      <div className="absolute bottom-[-10%] right-[-10%] w-[40%] h-[40%] rounded-full bg-purple-600/20 blur-[120px] mix-blend-screen animate-blob animation-delay-2000" />

      {/* Logo */}
      <header className="absolute left-6 top-6 z-10 sm:left-10 sm:top-8">
        <Link to="/" className="flex items-center gap-3">
          <img src={logo} alt="MoneyFast Logo" className="h-20 sm:h-28 w-auto object-contain transition-transform duration-300 hover:scale-105" />
        </Link>
      </header>

      {/* İçerik */}
      <main className="flex min-h-screen items-center justify-center px-5 pb-10 pt-28 sm:px-8">
        <section className="relative z-10 w-full max-w-xl rounded-[2.5rem] bg-slate-900/50 backdrop-blur-xl border border-white/10 px-7 py-10 shadow-2xl sm:px-12 sm:py-12">
          <div className="mx-auto max-w-md">
            <div className="mb-8 text-center">
              <div className="mb-4 inline-flex items-center gap-2 rounded-full bg-brandBlue/10 border border-brandBlue/20 px-3 py-1.5 text-xs font-semibold text-brandBlue">
                <span className="h-2 w-2 rounded-full bg-brandBlue" />
                Hesap Oluştur
              </div>

              <h1 className="text-3xl font-bold tracking-tight text-white">
                MoneyFast'e hoş geldin
              </h1>

              <p className="mt-3 text-sm leading-6 text-slate-400">
                Hesabını oluşturmaya başlamak için bilgilerini gir.
              </p>
            </div>

            {/* Adım göstergesi */}
            <div className="mb-7 flex items-center gap-3">
              <div className="h-1.5 flex-1 rounded-full bg-brandBlue" />
              <div className="h-1.5 flex-1 rounded-full bg-slate-800" />
            </div>

            <p className="mb-6 text-center text-xs font-medium text-slate-500">
              Adım 1 / 2
            </p>

            <form onSubmit={handleSubmit} className="space-y-4">
              {/* Ad */}
              <div>
                <label
                  htmlFor="name"
                  className="mb-2 block text-sm font-semibold text-slate-300"
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
                  className="w-full rounded-2xl border border-white/10 bg-white/5 px-4 py-3.5 text-sm text-white outline-none transition placeholder:text-slate-500 hover:border-white/20 focus:border-brandBlue focus:bg-white/10 focus:ring-4 focus:ring-brandBlue/20"
                />
              </div>

              {/* Soyad */}
              <div>
                <label
                  htmlFor="surname"
                  className="mb-2 block text-sm font-semibold text-slate-300"
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
                  className="w-full rounded-2xl border border-white/10 bg-white/5 px-4 py-3.5 text-sm text-white outline-none transition placeholder:text-slate-500 hover:border-white/20 focus:border-brandBlue focus:bg-white/10 focus:ring-4 focus:ring-brandBlue/20"
                />
              </div>

              {/* TC */}
              <div>
                <label
                  htmlFor="tcNo"
                  className="mb-2 block text-sm font-semibold text-slate-300"
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
                  className="w-full rounded-2xl border border-white/10 bg-white/5 px-4 py-3.5 text-sm text-white outline-none transition placeholder:text-slate-500 hover:border-white/20 focus:border-brandBlue focus:bg-white/10 focus:ring-4 focus:ring-brandBlue/20"
                />
              </div>

              {/* E-posta */}
              <div>
                <label
                  htmlFor="email"
                  className="mb-2 block text-sm font-semibold text-slate-300"
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
                  className="w-full rounded-2xl border border-white/10 bg-white/5 px-4 py-3.5 text-sm text-white outline-none transition placeholder:text-slate-500 hover:border-white/20 focus:border-brandBlue focus:bg-white/10 focus:ring-4 focus:ring-brandBlue/20"
                />
              </div>

              {/* Telefon */}
              <div>
                <label
                  htmlFor="phone"
                  className="mb-2 block text-sm font-semibold text-slate-300"
                >
                  Telefon Numarası
                </label>

                <div className="flex">
                  <div className="flex items-center rounded-l-2xl border border-r-0 border-white/10 bg-slate-800 px-4 text-sm font-medium text-slate-400">
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
                    className="w-full rounded-r-2xl border border-white/10 bg-white/5 px-4 py-3.5 text-sm text-white outline-none transition placeholder:text-slate-500 hover:border-white/20 focus:border-brandBlue focus:bg-white/10 focus:ring-4 focus:ring-brandBlue/20"
                  />
                </div>
              </div>

              {/* Sözleşmeler */}
              <div className="space-y-3 pt-2">
                <label className="flex items-start gap-3 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={acceptTerms}
                    onChange={(e) => setAcceptTerms(e.target.checked)}
                    className="mt-1 h-4 w-4 rounded border-white/10 bg-white/5 text-brandBlue focus:ring-brandBlue/30 focus:ring-offset-slate-900 cursor-pointer"
                  />
                  <span className="text-xs text-slate-400">
                    <Link to="#" className="text-brandBlue hover:underline">Kullanıcı Sözleşmesini</Link> ve <Link to="#" className="text-brandBlue hover:underline">Aydınlatma Metnini</Link> okudum, kabul ediyorum.
                  </span>
                </label>

                <label className="flex items-start gap-3 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={acceptKVKK}
                    onChange={(e) => setAcceptKVKK(e.target.checked)}
                    className="mt-1 h-4 w-4 rounded border-white/10 bg-white/5 text-brandBlue focus:ring-brandBlue/30 focus:ring-offset-slate-900 cursor-pointer"
                  />
                  <span className="text-xs text-slate-400">
                    Kişisel verilerimin işlenmesine ilişkin <Link to="#" className="text-brandBlue hover:underline">Açık Rıza Metnini</Link> okudum, kabul ediyorum.
                  </span>
                </label>
              </div>

              {error && (
                <div
                  role="alert"
                  className="rounded-2xl border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-400"
                >
                  {error}
                </div>
              )}

              <button
                type="submit"
                className="group mt-2 flex w-full items-center justify-center gap-2 rounded-2xl bg-brandBlue px-4 py-3.5 font-semibold text-white shadow-lg shadow-brandBlue/25 transition duration-200 hover:-translate-y-0.5 hover:bg-blue-600 focus:outline-none focus:ring-4 focus:ring-brandBlue/30"
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
                className="text-sm font-semibold text-slate-400 transition hover:text-brandBlue"
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