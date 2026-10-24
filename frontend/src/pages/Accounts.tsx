import { useState, type FormEvent } from 'react'
import { get, write, setupPassword } from '../lib/api'
import { useAuth } from '../lib/auth'
import { useLoad, errorMessage } from '../lib/hooks'
import { Notice, PageHeading, Panel } from '../components/Primitives'
import { useToast } from '../components/Toast'
import Modal from '../components/Modal'

export function Loading() { return <div className="saas-loading" role="status" aria-label="Loading"><div /><div /><div /></div> }
export function Fields({ fields }: { fields: Record<string, unknown> }) {
  return <dl className="saas-fields">{Object.entries(fields).filter(([, v]) => typeof v !== 'object' || v === null).map(([k, v]) => <div key={k}><dt>{k.replaceAll('_', ' ')}</dt><dd>{v === null || v === '' ? 'Unavailable' : String(v)}</dd></div>)}</dl>
}

export function AccountSettings({ setupToken }: { setupToken?: string }) {
  const { user, signOut } = useAuth()
  const [current, setCurrent] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState('')
  const [done, setDone] = useState(false)
  const [busy, setBusy] = useState(false)
  const submit = async (e: FormEvent) => {
    e.preventDefault(); setError('')
    if (password !== confirm) { setError('Passwords do not match.'); return }
    setBusy(true)
    try {
      if (setupToken) await setupPassword(setupToken, password)
      else await write('POST', '/api/auth/password', { current_password: current, new_password: password })
      setDone(true); setPassword(''); setCurrent(''); setConfirm('')
      if (!setupToken) signOut()
    } catch (err) { setError(errorMessage(err)) } finally { setBusy(false) }
  }
  return <div className={setupToken || user?.must_change_password ? 'login-page' : ''}><div className="saas-account">
    <PageHeading title={setupToken ? 'Set your password' : 'Account settings'} description={user?.must_change_password ? 'Choose a new password to activate your access.' : 'Use a unique password of at least 12 characters.'} />
    {done ? <Notice tone="success">Password saved. <a href="/">Continue to sign in</a>.</Notice> : <Panel title="Password">
      {error && <Notice tone="error">{error}</Notice>}
      <form onSubmit={submit} className="stack">
        {!setupToken && <label className="form-field">Current password<input type="password" autoComplete="current-password" value={current} onChange={e => setCurrent(e.target.value)} required maxLength={256} /></label>}
        <label className="form-field">New password<input type="password" autoComplete="new-password" value={password} onChange={e => setPassword(e.target.value)} required minLength={12} maxLength={256} /></label>
        <label className="form-field">Confirm password<input type="password" autoComplete="new-password" value={confirm} onChange={e => setConfirm(e.target.value)} required /></label>
        <button className="button button-primary" disabled={busy}>{busy ? 'Saving...' : 'Save password'}</button>
      </form>
    </Panel>}
  </div></div>
}

export function SetupLink({ value, close }: { value: { setup_token: string; username: string }; close: () => void }) {
  const toast = useToast()
  const link = `${window.location.origin}/#setup=${encodeURIComponent(value.setup_token)}`
  return <Modal title="Deliver account setup link" onClose={close}>
    <p>Send this single-use link privately to {value.username}. It expires in one hour. It will not be displayed again after closing.</p>
    <button className="button button-primary" onClick={async () => { try { await navigator.clipboard.writeText(link); toast.push('success', 'Setup link copied. Deliver it privately.'); } catch { toast.push('error', 'Clipboard unavailable. Use a secure browser context.'); } }}>Copy setup link</button>
  </Modal>
}

export function InstitutionSettings() {
  const info = useLoad<{ name: string; contact_email: string; status: string }>(() => get('/api/institution'), 'institution')
  const [search, setSearch] = useState('')
  const [offset, setOffset] = useState(0)
  const list = useLoad<Array<{ username: string; student_id: string; active: boolean; must_change_password: boolean }>>(() => get('/api/institution/accounts', { search, offset, limit: 25 }), `${search}:${offset}`)
  const [username, setUsername] = useState('')
  const [sid, setSid] = useState('')
  const [link, setLink] = useState<{ setup_token: string; username: string } | null>(null)
  const [busy, setBusy] = useState(false)
  const toast = useToast()
  const run = async (fn: () => Promise<unknown>) => { setBusy(true); try { await fn(); list.reload(); toast.push('success', 'Account updated.'); } catch (e) { toast.push('error', errorMessage(e)); } finally { setBusy(false) } }
  const create = (e: FormEvent) => { e.preventDefault(); void run(async () => { await write('POST', '/api/institution/accounts', { username, student_id: sid }); setUsername(''); setSid('') }) }
  return <>
    <PageHeading title="Institution & accounts" description="Manage your institution profile and access for existing student records." />
    {info.error && <Notice tone="error">{info.error}</Notice>}
    {info.loading ? <Loading /> : info.data && <Panel title={info.data.name}><form className="stack" key={info.data.name + info.data.contact_email} onSubmit={e => { e.preventDefault(); const f = new FormData(e.currentTarget); void run(async () => { await write('PATCH', '/api/institution', { name: f.get('name'), contact_email: f.get('email') }); info.reload() }) }}>
      <label className="form-field">Institution name<input name="name" required minLength={2} maxLength={160} defaultValue={info.data.name} /></label>
      <label className="form-field">Contact email<input name="email" type="email" required defaultValue={info.data.contact_email} /></label>
      <p>Status: {info.data.status}</p><button className="button button-secondary" disabled={busy}>Save profile</button>
    </form></Panel>}
    <Panel title="Create student account" subtitle="Import or create the student record first. Reimporting data does not create duplicate logins.">
      <form className="saas-toolbar" onSubmit={create}>
        <label className="form-field">Student ID<input value={sid} onChange={e => setSid(e.target.value)} required maxLength={32} /></label>
        <label className="form-field">Username<input value={username} onChange={e => setUsername(e.target.value)} required minLength={3} maxLength={64} pattern="[A-Za-z0-9_-]+" /></label>
        <button className="button button-primary" disabled={busy}>Create account</button>
      </form>
    </Panel>
    <Panel title="Student accounts">
      <label className="form-field">Search accounts<input value={search} onChange={e => { setSearch(e.target.value); setOffset(0) }} /></label>
      {list.error && <Notice tone="error">{list.error}</Notice>}
      {list.loading ? <Loading /> : <div className="saas-table"><table><thead><tr><th>Username</th><th>Student ID</th><th>Status</th><th>Access</th></tr></thead><tbody>{list.data?.map(u => <tr key={u.username}><td>{u.username}</td><td>{u.student_id}</td><td>{!u.active ? 'Inactive' : u.must_change_password ? 'Setup required' : 'Active'}</td><td><button className="button button-secondary" disabled={busy || !u.active} onClick={() => { if (window.confirm('Issue a new setup link and revoke all current sessions?')) void run(async () => setLink(await write('POST', `/api/institution/accounts/${u.username}/setup`, {}))) }}>Issue setup / reset</button> <button className="button button-secondary" disabled={busy} onClick={() => { if (window.confirm(`${u.active ? 'Deactivate' : 'Activate'} this account?`)) void run(() => write('PATCH', `/api/institution/accounts/${u.username}`, { active: !u.active })) }}>{u.active ? 'Deactivate' : 'Activate'}</button></td></tr>)}</tbody></table>{!list.data?.length && <p>No student accounts found.</p>}</div>}
      <div className="saas-toolbar"><button className="button" disabled={!offset || list.loading} onClick={() => setOffset(offset - 25)}>Previous</button><span>{list.meta.total ?? 0} accounts</span><button className="button" disabled={!list.meta.has_more || list.loading} onClick={() => setOffset(offset + 25)}>Next</button></div>
    </Panel>
    {link && <SetupLink value={link} close={() => setLink(null)} />}
  </>
}
