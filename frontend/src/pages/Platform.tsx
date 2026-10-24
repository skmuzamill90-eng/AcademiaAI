import { useState, type FormEvent } from 'react'
import { useLocation } from 'react-router-dom'
import { get, write } from '../lib/api'
import { useLoad, errorMessage } from '../lib/hooks'
import { Notice, PageHeading, Panel } from '../components/Primitives'
import { useToast } from '../components/Toast'
import Modal from '../components/Modal'
import { Loading, Fields, SetupLink } from './Accounts'

type Institution = { id: string; name: string; status: string; contact_email: string; student_count: number | null; student_accounts: number; intervention_count: number; created_at: string; administrators: Array<{ username: string; active: boolean; must_change_password: boolean; last_login_at: string | null }> }
export default function Platform() {
  const auditPage = useLocation().pathname === '/audit'
  const toast = useToast()
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState('')
  const [sort, setSort] = useState('name')
  const [order, setOrder] = useState('asc')
  const [offset, setOffset] = useState(0)
  const [creating, setCreating] = useState(false)
  const [selected, setSelected] = useState<Institution | null>(null)
  const [busy, setBusy] = useState(false)
  const [link, setLink] = useState<{ setup_token: string; username: string } | null>(null)
  const overview = useLoad<{ institutions: number; student_accounts: number; statuses: Record<string, number> }>(() => get('/api/platform/overview'), 'overview')
  const institutions = useLoad<Institution[]>(() => get('/api/platform/institutions', { search, status, sort, order, limit: 20, offset }), `${search}:${status}:${sort}:${order}:${offset}`)
  const logs = useLoad<Array<{ at: string; actor: string; action: string; target: string }>>(() => auditPage ? get('/api/platform/audit', { offset, limit: 20 }) : Promise.resolve({ data: [] }), `${auditPage}:${offset}`)
  const run = async (fn: () => Promise<unknown>) => { setBusy(true); try { await fn(); institutions.reload(); overview.reload(); logs.reload(); toast.push('success', 'Changes saved.'); } catch (e) { toast.push('error', errorMessage(e)); } finally { setBusy(false) } }
  const submit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault(); const f = new FormData(e.currentTarget)
    const body = Object.fromEntries(f.entries())
    void run(async () => { await write(creating ? 'POST' : 'PATCH', creating ? '/api/platform/institutions' : `/api/platform/institutions/${selected?.id}`, body); setCreating(false); setSelected(null) })
  }
  const list = auditPage ? logs : institutions
  return <>
    <PageHeading title={auditPage ? 'Administrative audit logs' : 'Platform overview'} description="Authorize institutions and manage administrator access." actions={!auditPage && <button className="button button-primary" onClick={() => setCreating(true)}>Create institution</button>} />
    {!auditPage && <>
      {overview.error && <Notice tone="error">{overview.error}</Notice>}
      {overview.loading ? <Loading /> : overview.data && <div className="saas-summary">{Object.entries({ Institutions: overview.data.institutions, 'Student accounts': overview.data.student_accounts, ...overview.data.statuses }).map(([k, v]) => <Panel key={k} title={k}><strong className="saas-number">{v}</strong></Panel>)}</div>}
      <div className="saas-toolbar"><label className="form-field">Search institutions<input value={search} onChange={e => { setSearch(e.target.value); setOffset(0) }} /></label><label className="form-field">Status<select value={status} onChange={e => { setStatus(e.target.value); setOffset(0) }}><option value="">All statuses</option>{['pending', 'active', 'suspended', 'deactivated'].map(s => <option key={s}>{s}</option>)}</select></label><label className="form-field">Sort<select value={sort} onChange={e => { setSort(e.target.value); setOffset(0) }}><option value="name">Name</option><option value="created_at">Created</option><option value="status">Status</option></select></label><label className="form-field">Order<select value={order} onChange={e => setOrder(e.target.value)}><option value="asc">Ascending</option><option value="desc">Descending</option></select></label></div>
    </>}
    {list.error && <Notice tone="error">{list.error} <button className="button" onClick={list.reload}>Retry</button></Notice>}
    {list.loading ? <Loading /> : auditPage ? <Panel title="Recent events"><div className="saas-table"><table><thead><tr><th>Time</th><th>Actor</th><th>Action</th><th>Target</th></tr></thead><tbody>{logs.data?.map((r, i) => <tr key={i}><td>{r.at}</td><td>{r.actor}</td><td>{r.action}</td><td>{r.target}</td></tr>)}</tbody></table>{!logs.data?.length && <p>No audit events.</p>}</div></Panel> : <Panel title="Institutions"><div className="saas-table"><table><thead><tr><th>Institution</th><th>Status</th><th>Students</th><th>Accounts</th><th>Manage</th></tr></thead><tbody>{institutions.data?.map(r => <tr key={r.id}><td><strong>{r.name}</strong><small>{r.contact_email}</small></td><td><span className={`saas-status status-${r.status}`}>{r.status}</span></td><td>{r.student_count ?? 'Unavailable'}</td><td>{r.student_accounts}</td><td><button className="button button-secondary" onClick={() => setSelected(r)}>Details & access</button></td></tr>)}</tbody></table>{!institutions.data?.length && <p>No institutions found. Create an institution to begin onboarding.</p>}</div></Panel>}
    <div className="saas-toolbar"><button className="button" disabled={!offset || list.loading} onClick={() => setOffset(Math.max(0, offset - 20))}>Previous</button><span>{list.meta.total ?? 0} records</span><button className="button" disabled={!list.meta.has_more || list.loading} onClick={() => setOffset(offset + 20)}>Next</button></div>
    {(creating || selected) && <Modal title={creating ? 'Create institution' : selected!.name} onClose={() => { setCreating(false); setSelected(null) }}>
      <form className="stack" onSubmit={submit}>
        <label className="form-field">Institution name<input name="name" required minLength={2} maxLength={160} defaultValue={selected?.name} /></label>
        <label className="form-field">Administrator contact email<input name="contact_email" type="email" required defaultValue={selected?.contact_email} /></label>
        {creating && <label className="form-field">Administrator username<input name="admin_username" required minLength={3} maxLength={64} pattern="[A-Za-z0-9_-]+" /></label>}
        <label className="form-field">Status<select name="status" defaultValue={selected?.status ?? 'pending'}>{(creating ? ['pending', 'active'] : ['pending', 'active', 'suspended', 'deactivated']).map(s => <option key={s}>{s}</option>)}</select></label>
        <p>Changing status revokes existing sessions. Suspended and deactivated institutions cannot access protected data.</p>
        <button className="button button-primary" disabled={busy} onClick={e => { if (!creating && !window.confirm('Save institution profile and access status?')) e.preventDefault() }}>{busy ? 'Saving...' : 'Save institution'}</button>
      </form>
      {selected && <><Fields fields={{ institution_id: selected.id, created: selected.created_at, students: selected.student_count, student_accounts: selected.student_accounts, interventions: selected.intervention_count }} />{selected.administrators.map(a => <div className="stack" key={a.username}><Fields fields={{ administrator: a.username, active: a.active, onboarding: a.must_change_password ? 'Setup required' : 'Completed', last_login: a.last_login_at }} /><button className="button button-secondary" disabled={busy || selected.status !== 'active' || !a.active} onClick={() => { if (window.confirm('Issue a setup link and revoke existing sessions?')) void run(async () => { setLink(await write('POST', `/api/platform/institutions/${selected.id}/administrator/setup`, {})); setSelected(null) }) }}>Issue administrator setup / reset</button><button className="button button-secondary" disabled={busy} onClick={() => { if (window.confirm('Change administrator access and revoke sessions?')) void run(async () => { await write('PATCH', `/api/platform/institutions/${selected.id}/administrator`, { active: !a.active }); setSelected(null) }) }}>{a.active ? 'Revoke administrator access' : 'Activate administrator access'}</button></div>)}</>}
    </Modal>}
    {link && <SetupLink value={link} close={() => setLink(null)} />}
  </>
}
