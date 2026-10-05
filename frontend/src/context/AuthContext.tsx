import {
  createContext, useContext, useState, useCallback,
  type ReactNode,
} from 'react'
import type { GoogleUser } from '@/types'
import { decodeGoogleJwt } from '@/lib/utils'

interface AuthContextValue {
  user:            GoogleUser | null
  token:           string | null
  isAuthenticated: boolean
  loginWithGoogle: (credential: string) => Promise<void>
  logout:          () => void
}

const AuthContext = createContext<AuthContextValue | null>(null)

const USER_KEY = 'bx_user'
const TOKEN_KEY = 'bx_token'

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<GoogleUser | null>(() => {
    try {
      const raw = sessionStorage.getItem(USER_KEY)
      return raw ? (JSON.parse(raw) as GoogleUser) : null
    } catch {
      return null
    }
  })

  const [token, setToken] = useState<string | null>(() => {
    return sessionStorage.getItem(TOKEN_KEY)
  })

  const loginWithGoogle = useCallback(async (credential: string) => {
    const base = import.meta.env.VITE_API_URL ?? ''
    const endpoint = base ? `${base}/api/v1/auth/google` : '/api/v1/auth/google'

    const res = await fetch(endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ credential }),
    })

    if (!res.ok) {
      const errData = (await res.json().catch(() => ({}))) as { error?: string; message?: string }
      const errMessage = errData.message ?? errData.error ?? `Authentication failed with status ${res.status}`
      throw new Error(errMessage)
    }

    const data = await res.json()
    const issuedToken = data.token
    if (!issuedToken) {
      throw new Error('No session token returned by gateway')
    }

    const userObj: GoogleUser = {
      sub: data.user?.user_id ?? 'usr_google',
      email: data.user?.email ?? '',
      name: data.user?.name ?? 'Authenticated User',
      picture: data.user?.picture ?? '',
    }

    sessionStorage.setItem(TOKEN_KEY, issuedToken)
    sessionStorage.setItem(USER_KEY, JSON.stringify(userObj))
    setToken(issuedToken)
    setUser(userObj)
  }, [])

  const logout = useCallback(() => {
    sessionStorage.removeItem(TOKEN_KEY)
    sessionStorage.removeItem(USER_KEY)
    setToken(null)
    setUser(null)
  }, [])

  return (
    <AuthContext.Provider value={{ user, token, isAuthenticated: !!user, loginWithGoogle, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
