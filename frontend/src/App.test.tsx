import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import type { ReactNode } from 'react'
import App from './App'

const mocks = vi.hoisted(() => ({ role: 'student' as 'student' | 'college_admin' | 'super_admin' }))
vi.mock('./lib/auth', () => ({
  AuthProvider: ({ children }: { children: ReactNode }) => children,
  STAFF: ['college_admin'],
  roleLabel: { super_admin: 'Super Admin', college_admin: 'College Admin', student: 'Student' },
  useAuth: () => ({
    user: { username: 'test-user', role: mocks.role, institution_id: 'institution-1', student_id: 'STU90000001' },
    checking: false,
    can: (...roles: string[]) => roles.includes(mocks.role),
    signOut: vi.fn(),
  }),
}))
vi.mock('./pages/StudentPortal', () => ({ default: () => <div>Student Portal Route</div> }))
vi.mock('./pages/Dashboard', () => ({ default: () => <div>College Dashboard Route</div> }))
vi.mock('./pages/Platform', () => ({ default: () => <div>Platform Dashboard Route</div> }))

beforeEach(() => {
  mocks.role = 'student'
  window.scrollTo = vi.fn()
})

describe('role-specific landing dashboards', () => {
  it('routes student sessions into the student workspace inside the existing shell', async () => {
    render(<App />)
    expect(await screen.findByText('Student Portal Route')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'My support plan' })).toBeInTheDocument()
  })

  it('keeps the college administrator dashboard route', async () => {
    mocks.role = 'college_admin'
    render(<App />)
    expect(await screen.findByText('College Dashboard Route')).toBeInTheDocument()
  })

  it('keeps the super administrator dashboard route', async () => {
    mocks.role = 'super_admin'
    render(<App />)
    expect(await screen.findByText('Platform Dashboard Route')).toBeInTheDocument()
  })
})
