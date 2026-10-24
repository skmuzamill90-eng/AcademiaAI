import { useState, type FormEvent } from 'react'
import { LockKeyhole } from 'lucide-react'
import { useAuth } from '../lib/auth'
import { errorMessage } from '../lib/hooks'
import { Notice } from '../components/Primitives'

type LoginMode = 'admin' | 'campus' | 'student'

export default function Login() {
  const { signIn } = useAuth()
  const [mode, setMode] = useState<LoginMode>('campus')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await signIn(username, password, mode)
    } catch (err) {
      setError(errorMessage(err))
      setBusy(false)
    }
  }

  return (
    <div className="login-page login-page-signin">
      <main className="login-panel">
        <form className="login-card" onSubmit={submit} aria-label="AcademiaAI sign in">
          <div className="login-brand">
            <img src="/academia-mark.png" alt="" width={38} height={38} />
            <div>
              <strong>Academia</strong>
              <span>Campus Intelligence</span>
            </div>
          </div>

          <div className="login-tabs" role="group" aria-label="Choose account type">
            <button type="button" aria-pressed={mode === 'admin'} onClick={() => setMode('admin')}>Admin</button>
            <button type="button" aria-pressed={mode === 'campus'} onClick={() => setMode('campus')}>Campus Login</button>
            <button type="button" aria-pressed={mode === 'student'} onClick={() => setMode('student')}>Student Login</button>
          </div>

          <div className="login-intro">
            <h1>Sign in</h1>
            <p>{mode === 'admin'
              ? 'Use your administrator account to manage campus access.'
              : mode === 'campus'
                ? 'Use your campus administrator account to access your institution workspace.'
                : 'Use your student account to access your student dashboard.'}</p>
          </div>

          <div className="login-fields">
            <label className="login-field">
              <span>Username</span>
              <div>
                <input
                  aria-label={mode === 'admin' ? 'Admin username' : mode === 'student' ? 'Student username' : 'Campus username'}
                  value={username}
                  onChange={e => setUsername(e.target.value)}
                  autoComplete="username"
                  autoFocus
                  required
                  placeholder="Username"
                />
              </div>
            </label>
            <label className="login-field">
              <span>Password</span>
              <div>
                <input
                  aria-label="Password"
                  type="password"
                  value={password}
                  onChange={e => setPassword(e.target.value)}
                  autoComplete="current-password"
                  required
                  placeholder="Password"
                />
              </div>
            </label>
          </div>

          {error && <Notice tone="error">{error}</Notice>}

          <button className="login-submit" type="submit" disabled={busy || !username || !password}>
            {busy ? 'Signing in...' : <><LockKeyhole size={16} />Sign in</>}
          </button>
        </form>
      </main>
    </div>
  )
}
