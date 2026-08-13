import { FormEvent, useState } from 'react'

export default function Login() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [error, setError] = useState('')

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError('')

    if (!email.trim() || !password.trim()) {
      setError('Lütfen e-posta ve şifre alanlarını doldurun.')
      return
    }

    // Backend entegrasyonu daha sonra burada yapılacak.
    console.log('Login form submitted:', { email })
  }

  return (
    <div className="min-h-screen bg-slate-50 lg:grid lg:grid-cols-2">
      {/* Sol alan */}
      <section className="relative hidden overflow-hidden bg-slate-950 p-12 text-white lg:flex lg:flex-col lg:justify-between">
        <div>
          <div className="mb-16 flex items-center gap-3">
            <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-emerald-400 font-bold text-slate-950">
              M
            </div>

            <span className="text-2xl font-semibold tracking-tight">
              MoneyFast
            </span>
          </div>

          <div className="max-w-lg">
            <p className="mb-4 text-sm font-medium uppercase tracking-[0.22em] text-emerald-400">
              Akıllı Finans Danışmanın
            </p>

            <h1 className="text-5xl font-semibold leading-tight">
              Finansal kararlarını daha bilinçli ver.
            </h1>

            <p className="mt-6 max-w-md text-lg leading-8 text-slate-300">
              Finansal durumunu takip et, portföyünü değerlendir ve yapay
              zekâ destekli analizlerle seçeneklerini daha iyi anla.
            </p>
          </div>
        </div>

        <p className="text-sm text-slate-500">
          © 2026 MoneyFast · InterFive
        </p>

        <div className="absolute -bottom-40 -right-32 h-96 w-96 rounded-full bg-emerald-400/10 blur-3xl" />
      </section>

      {/* Login alanı */}
      <main className="flex min-h-screen items-center justify-center px-6 py-12 sm:px-10">
        <div className="w-full max-w-md">
          {/* Mobil logo */}
          <div className="mb-10 flex items-center gap-3 lg:hidden">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-slate-950 font-bold text-white">
              M
            </div>

            <span className="text-xl font-semibold text-slate-950">
              MoneyFast
            </span>
          </div>

          <div className="mb-8">
            <h2 className="text-3xl font-semibold tracking-tight text-slate-950">
              Tekrar hoş geldiniz
            </h2>

            <p className="mt-2 text-sm leading-6 text-slate-500">
              MoneyFast hesabınıza giriş yaparak finansal görünümünüze
              erişebilirsiniz.
            </p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-5">
            <div>
              <label
                htmlFor="email"
                className="mb-2 block text-sm font-medium text-slate-700"
              >
                E-posta
              </label>

              <input
                id="email"
                type="email"
                autoComplete="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                placeholder="ornek@email.com"
                className="w-full rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-950 outline-none transition placeholder:text-slate-400 focus:border-slate-400 focus:ring-4 focus:ring-slate-100"
              />
            </div>

            <div>
              <div className="mb-2 flex items-center justify-between">
                <label
                  htmlFor="password"
                  className="text-sm font-medium text-slate-700"
                >
                  Şifre
                </label>

                <button
                  type="button"
                  className="text-sm font-medium text-slate-600 transition hover:text-slate-950"
                >
                  Şifremi unuttum
                </button>
              </div>

              <div className="relative">
                <input
                  id="password"
                  type={showPassword ? 'text' : 'password'}
                  autoComplete="current-password"
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  placeholder="Şifrenizi girin"
                  className="w-full rounded-xl border border-slate-200 bg-white px-4 py-3 pr-20 text-sm text-slate-950 outline-none transition placeholder:text-slate-400 focus:border-slate-400 focus:ring-4 focus:ring-slate-100"
                />

                <button
                  type="button"
                  onClick={() => setShowPassword((current) => !current)}
                  className="absolute right-4 top-1/2 -translate-y-1/2 text-sm font-medium text-slate-500 hover:text-slate-950"
                >
                  {showPassword ? 'Gizle' : 'Göster'}
                </button>
              </div>
            </div>

            <label className="flex cursor-pointer items-center gap-3 text-sm text-slate-600">
              <input
                type="checkbox"
                className="h-4 w-4 rounded border-slate-300 accent-slate-950"
              />
              Beni hatırla
            </label>

            {error && (
              <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
                {error}
              </div>
            )}

            <button
              type="submit"
              className="w-full rounded-xl bg-slate-950 px-4 py-3 font-medium text-white transition hover:bg-slate-800 focus:outline-none focus:ring-4 focus:ring-slate-200"
            >
              Giriş Yap
            </button>
          </form>

          <p className="mt-8 text-center text-sm text-slate-500">
            Hesabınız yok mu?{' '}
            <button
              type="button"
              className="font-semibold text-slate-900 hover:underline"
            >
              Hesap oluştur
            </button>
          </p>
        </div>
      </main>
    </div>
  )
}