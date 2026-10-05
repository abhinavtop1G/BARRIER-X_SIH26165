import { useState, useEffect } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { cn } from '@/lib/utils'
import { useAuth } from '@/context/AuthContext'

const NAV_LINKS = [
  { href: '#core-features', label: 'Core Features' },
  { href: '#problem',       label: 'Problem'       },
  { href: '#solution',      label: 'Solution'      },
  { href: '#about',         label: 'About'         },
]

function scrollTo(id: string) {
  document.getElementById(id)?.scrollIntoView({ behavior: 'smooth' })
}

export default function Navbar() {
  const [scrolled, setScrolled] = useState(false)
  const [open, setOpen]         = useState(false)
  const navigate                = useNavigate()
  const { isAuthenticated }     = useAuth()

  useEffect(() => {
    const fn = () => setScrolled(window.scrollY > 24)
    window.addEventListener('scroll', fn, { passive: true })
    return () => window.removeEventListener('scroll', fn)
  }, [])

  return (
    <header
      className={cn(
        'fixed inset-x-0 top-0 z-50 transition-all duration-300',
        scrolled
          ? 'bg-bx-bg/85 backdrop-blur-xl border-b border-bx-border'
          : 'bg-transparent',
      )}
    >
      <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between gap-8">
        <Link to="/" className="font-display text-xl font-bold tracking-widest uppercase shrink-0">
          BARRIER <span className="text-bx-gold">X</span>
        </Link>

        <nav className="hidden md:flex items-center gap-1">
          {NAV_LINKS.map(({ href, label }) => (
            <button
              key={href}
              onClick={() => scrollTo(href.slice(1))}
              className="px-3.5 py-2 text-sm font-medium text-bx-secondary rounded-lg
                         hover:text-bx-text hover:bg-white/5 transition-colors duration-150"
            >
              {label}
            </button>
          ))}
        </nav>

        <button
          onClick={() => navigate(isAuthenticated ? '/dashboard' : '/login')}
          className="hidden md:flex btn-gold text-sm px-5 py-2.5"
        >
          {isAuthenticated ? 'Dashboard' : 'Sign In'}
        </button>

        <button
          className="md:hidden flex flex-col gap-1.5 p-1.5 text-bx-secondary"
          onClick={() => setOpen(o => !o)}
          aria-label="Toggle menu"
        >
          <span className={cn('block w-5 h-0.5 bg-current transition-all duration-200', open && 'translate-y-2 rotate-45')} />
          <span className={cn('block w-5 h-0.5 bg-current transition-all duration-200', open && 'opacity-0')} />
          <span className={cn('block w-5 h-0.5 bg-current transition-all duration-200', open && '-translate-y-2 -rotate-45')} />
        </button>
      </div>

      {open && (
        <div className="md:hidden bg-bx-bg/95 backdrop-blur-xl border-t border-bx-border px-6 py-4 flex flex-col gap-1">
          {NAV_LINKS.map(({ href, label }) => (
            <button
              key={href}
              onClick={() => { scrollTo(href.slice(1)); setOpen(false) }}
              className="px-3 py-2.5 text-sm text-left text-bx-secondary hover:text-bx-text
                         hover:bg-white/5 rounded-lg transition-colors"
            >
              {label}
            </button>
          ))}
          <button
            onClick={() => { setOpen(false); navigate('/login') }}
            className="btn-gold mt-2 justify-center"
          >
            Sign In
          </button>
        </div>
      )}
    </header>
  )
}
