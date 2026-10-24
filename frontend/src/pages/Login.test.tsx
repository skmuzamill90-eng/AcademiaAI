import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import Login from './Login'

const mocks = vi.hoisted(() => ({ signIn: vi.fn() }))

vi.mock('../lib/auth', () => ({
  useAuth: () => ({ signIn: mocks.signIn }),
}))

describe('login account type selection', () => {
  beforeEach(() => mocks.signIn.mockReset())

  it('offers separate admin, campus, and student sign-in modes', async () => {
    render(<Login />)

    expect(screen.getByRole('button', { name: 'Admin' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Campus Login' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Student Login' }))

    fireEvent.change(screen.getByLabelText('Student username'), { target: { value: 'learner' } })
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'secure-password' } })
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))

    expect(mocks.signIn).toHaveBeenCalledWith('learner', 'secure-password', 'student')
  })
})
