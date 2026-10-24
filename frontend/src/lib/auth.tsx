import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import * as api from './api'
import type { AuthUser, LoginType, Role } from './types'

interface AuthState {
  user: AuthUser | null
  signIn: (username: string, password: string, loginType: LoginType) => Promise<void>
  signOut: () => void
  can: (...roles: Role[]) => boolean
  checking: boolean
}
const Ctx = createContext<AuthState | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(() => {
    const saved = api.loadSession()
    if (saved) api.setToken(saved.token)
    return saved?.user ?? null
  })

  const [checking, setChecking] = useState(!!api.loadSession())
  const clearSession = useCallback(() => { api.setToken(null); api.saveSession(null); setUser(null); setChecking(false) }, [])
  const signOut = useCallback(() => {
    void api.write('POST', '/api/auth/logout', {}).catch(() => undefined)
    clearSession()
  }, [clearSession])
  useEffect(() => {
    if (!api.loadSession()) return
    api.get<AuthUser>('/api/auth/me').then(({ data }) => setUser(data), clearSession).finally(() => setChecking(false))
  }, [clearSession])
  useEffect(() => { api.onUnauthorized(clearSession); return () => api.onUnauthorized(null) }, [clearSession])

  const signIn = useCallback(async (username: string, password: string, loginType: LoginType) => {
    const session = await api.login(username.trim(), password, loginType)
    api.setToken(session.token); api.saveSession(session); setUser(session.user)
  }, [])

  const value = useMemo<AuthState>(() => ({
    user, signIn, signOut, checking, can: (...roles) => !!user && roles.includes(user.role),
  }), [user, signIn, signOut, checking])
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

export function useAuth() {
  const ctx = useContext(Ctx)
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider')
  return ctx
}

/** Roles that may read student-level data, per the backend's RBAC. */
export const STAFF: Role[] = ['college_admin']
export const roleLabel: Record<Role, string> = {
  super_admin: 'Super Admin', college_admin: 'College Admin', student: 'Student',
}
