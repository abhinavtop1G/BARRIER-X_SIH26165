import { useState } from 'react'
import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { useAuth } from '@/context/AuthContext'
import { cn } from '@/lib/utils'

interface NavItem {
  to:    string
  label: string
  icon:  string
  end?:  boolean
  soon?: boolean
}

const NAV: NavItem[] = [
  { to: '/dashboard',              label: 'Overview',            icon: '⬡', end: true   },
  { to: '/dashboard/reports',      label: 'Reports',             icon: '≡'              },
  { to: '/dashboard/sif-analysis', label: 'SIF Analysis',        icon: '⚑'              },
  { to: '/dashboard/precursors',   label: 'Precursor Patterns',  icon: '◌', soon: true  },
  { to: '/dashboard/life-saving',  label: 'Life-Saving Rules',   icon: '✦', soon: true  },
  { to: '/dashboard/3d-view',      label: '3D Safety View',      icon: '◈', soon: true  },
  { to: '/dashboard/agent',        label: 'AI HSE Agent',        icon: '◎'              },
]

export default function DashboardLayout() {
  const { user, logout } = useAuth()
  const navigate         = useNavigate()
  const [open, setOpen]  = useState(false)

  function handleLogout() { logout(); navigate('/', { replace: true }) }

  const Sidebar = () => (
    <aside className="w-56 shrink-0 bg-[#080808] border-r border-bx-border flex flex-col h-dvh sticky top-0">
      <div className="px-5 h-14 flex items-center border-b border-bx-border">
        <NavLink to="/" className="font-display text-lg font-bold tracking-widest uppercase">
          BARRIER <span className="text-bx-gold">X</span>
        </NavLink>
      </div>

      <nav className="flex-1 overflow-y-auto p-3 flex flex-col gap-px">
        {NAV.map(item => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.end}
            onClick={() => setOpen(false)}
            className={({ isActive }) => cn(
              'flex items-center gap-2.5 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors duration-150',
              isActive
                ? 'bg-bx-gold/10 text-bx-gold border border-bx-gold/15'
                : 'text-bx-secondary hover:text-bx-text hover:bg-white/5',
            )}
          >
            <span className="w-4 text-center opacity-70 text-[0.8rem]">{item.icon}</span>
            <span className="flex-1">{item.label}</span>
            {item.soon && (
              <span className="font-mono text-[0.5rem] uppercase tracking-wider text-bx-muted bg-white/[0.04] border border-bx-border rounded px-1.5 py-0.5">
                Soon
              </span>
            )}
          </NavLink>
        ))}
      </nav>

      <div className="p-3 border-t border-bx-border flex flex-col gap-1">
        <NavLink
          to="/dashboard/settings"
          className={({ isActive }) => cn(
            'flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm font-medium transition-colors duration-150',
            isActive ? 'bg-bx-gold/10 text-bx-gold border border-bx-gold/15' : 'text-bx-secondary hover:text-bx-text hover:bg-white/5',
          )}
        >
          <span className="w-4 text-center opacity-70 text-[0.8rem]">⚙</span>
          Settings
        </NavLink>

        <div className="flex items-center gap-2.5 px-3 py-2 mt-1">
          {user?.picture
            ? <img src={user.picture} alt={user.name} className="w-7 h-7 rounded-full border border-bx-border" />
            : (
              <div className="w-7 h-7 rounded-full bg-bx-gold/15 border border-bx-gold/20 text-bx-gold text-xs font-bold flex items-center justify-center">
                {(user?.name ?? 'U')[0].toUpperCase()}
              </div>
            )
          }
          <div className="flex-1 min-w-0">
            <p className="text-xs font-semibold truncate">{user?.name ?? 'User'}</p>
            <p className="text-[0.65rem] text-bx-muted truncate">{user?.email}</p>
          </div>
          <button onClick={handleLogout} title="Sign out"
            className="text-bx-muted hover:text-bx-text transition-colors text-base p-0.5"
          >↪</button>
        </div>
      </div>
    </aside>
  )

  return (
    <div className="flex bg-bx-bg min-h-dvh">
      {open && (
        <div
          className="fixed inset-0 z-40 bg-black/60 backdrop-blur-sm lg:hidden"
          onClick={() => setOpen(false)}
        />
      )}

      <div className="hidden lg:flex">
        <Sidebar />
      </div>

      <div className={cn(
        'fixed inset-y-0 left-0 z-50 flex lg:hidden transition-transform duration-300',
        open ? 'translate-x-0' : '-translate-x-full',
      )}>
        <Sidebar />
      </div>

      <div className="flex-1 flex flex-col min-w-0">
        <header className="lg:hidden h-14 flex items-center gap-4 px-5 bg-[#080808] border-b border-bx-border sticky top-0 z-30">
          <button onClick={() => setOpen(o => !o)} className="flex flex-col gap-1 p-1 text-bx-secondary">
            <span className="block w-5 h-0.5 bg-current rounded" />
            <span className="block w-5 h-0.5 bg-current rounded" />
            <span className="block w-5 h-0.5 bg-current rounded" />
          </button>
          <span className="font-display font-bold text-lg tracking-widest uppercase">
            BARRIER <span className="text-bx-gold">X</span>
          </span>
        </header>

        <main className="flex-1 p-6 lg:p-8 max-w-7xl">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
