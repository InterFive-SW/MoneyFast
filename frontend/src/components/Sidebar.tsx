import { NavLink } from 'react-router-dom'

const links = [
  { to: '/dashboard', label: 'Dashboard' },
  { to: '/chat', label: 'Chat' },
  { to: '/portfolio', label: 'Portfolio' },
  { to: '/banking', label: 'Banking' },
  { to: '/investment', label: 'Investment' },
  { to: '/risk', label: 'Risk' },
]

export default function Sidebar() {
  return (
    <aside className="w-56 shrink-0 h-screen bg-gray-900 text-white flex flex-col">
      <div className="px-6 py-5 text-xl font-bold tracking-tight border-b border-gray-700">
        MoneyFast
      </div>
      <nav className="flex-1 px-3 py-4 space-y-1">
        {links.map(({ to, label }) => (
          <NavLink
            key={to}
            to={to}
            end={to === '/dashboard'}
            className={({ isActive }) =>
              `block px-3 py-2 rounded-md text-sm font-medium transition-colors ${
                isActive
                  ? 'bg-gray-700 text-white'
                  : 'text-gray-300 hover:bg-gray-800 hover:text-white'
              }`
            }
          >
            {label}
          </NavLink>
        ))}
      </nav>
    </aside>
  )
}
