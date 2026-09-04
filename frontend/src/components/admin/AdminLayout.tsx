import { NavLink, Outlet, useNavigate } from 'react-router-dom'

import { clearAdminToken } from '../../api/adminClient'

/**
 * The operator shell.
 *
 * Not `DashboardLayout`: that sidebar is the customer application — portfolio,
 * chat, markets — and an administrator holds none of those. Showing them would
 * offer navigation the backend refuses anyway.
 */
export default function AdminLayout() {
  const navigate = useNavigate()
  const link = ({ isActive }: { isActive: boolean }) =>
    `block rounded-lg px-4 py-2.5 text-sm font-medium transition ${
      isActive ? 'bg-brandBlue text-white' : 'text-slate-300 hover:bg-slate-800'
    }`

  return (
    <div className="flex min-h-screen bg-slate-950">
      <aside className="w-60 shrink-0 border-r border-slate-800 bg-slate-900 p-4">
        <div className="mb-6 px-2">
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
            MoneyFast
          </p>
          <p className="text-lg font-bold text-white">Yönetim</p>
        </div>
        <nav className="space-y-1">
          <NavLink to="/admin/users" className={link}>Müşteriler</NavLink>
          <NavLink to="/admin/bills" className={link}>Faturalar</NavLink>
        </nav>
        <button
          onClick={() => { clearAdminToken(); navigate('/admin/login', { replace: true }) }}
          className="mt-6 w-full rounded-lg border border-slate-700 px-4 py-2.5 text-sm text-slate-300 hover:bg-slate-800"
        >
          Çıkış
        </button>
      </aside>
      <main className="flex-1 overflow-auto p-6"><Outlet /></main>
    </div>
  )
}
