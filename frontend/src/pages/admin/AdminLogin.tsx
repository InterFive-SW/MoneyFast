import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { adminApi, setAdminToken } from '../../api/adminClient'

export default function AdminLogin() {
  const navigate = useNavigate()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const submit = async (event: React.FormEvent) => {
    event.preventDefault()
    setError(null); setBusy(true)
    try {
      const { access_token } = await adminApi.login(username, password)
      setAdminToken(access_token)
      navigate('/admin/users', { replace: true })
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Giriş yapılamadı.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-950 p-4">
      <form onSubmit={submit} className="w-full max-w-sm rounded-2xl border border-slate-800 bg-slate-900 p-6">
        <h1 className="text-lg font-bold text-white">Yönetici Girişi</h1>
        <p className="mt-1 text-xs text-slate-500">
          Bu alan müşteri hesaplarından ayrıdır.
        </p>
        <label className="mt-5 block">
          <span className="text-xs font-medium text-slate-400">Kullanıcı Adı</span>
          <input
            value={username} onChange={(e) => setUsername(e.target.value)}
            className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-800 p-2.5 text-sm text-white"
          />
        </label>
        <label className="mt-3 block">
          <span className="text-xs font-medium text-slate-400">Parola</span>
          <input
            type="password" value={password} onChange={(e) => setPassword(e.target.value)}
            className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-800 p-2.5 text-sm text-white"
          />
        </label>
        {error && <p className="mt-3 text-sm text-rose-400">{error}</p>}
        <button
          type="submit" disabled={busy}
          className="mt-5 w-full rounded-lg bg-brandBlue p-2.5 text-sm font-semibold text-white disabled:opacity-50"
        >
          {busy ? 'Giriş yapılıyor…' : 'Giriş Yap'}
        </button>
      </form>
    </div>
  )
}
