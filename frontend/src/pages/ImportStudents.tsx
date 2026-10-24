import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  ArrowLeft, Check, CircleAlert, Download, FileSpreadsheet, Files, ListChecks, PlayCircle,
  RefreshCcw, ShieldCheck, Trash2, TriangleAlert, UserPlus, Users,
} from 'lucide-react'
import { ApiError } from '../lib/api'
import { errorMessage } from '../lib/hooks'
import { importApi, type ImportConfig, type Job, type UploadInfo } from '../lib/importApi'
import {
  CODE_LABEL, MODE_COPY, STEPS, assignColumn, columnLabel, columnLetter, formatBytes, indexIssues, missingRequired,
  precheckFile, rowsWithIssues, suggestionsToMapping, toRequestMapping, type ImportMode, type Issue, type Mapping,
} from '../lib/importLogic'
import { EmptyState, Notice, PageHeading, Panel } from '../components/Primitives'
import Modal from '../components/Modal'
import { ToastProvider, useToast } from '../components/Toast'
import Dropzone from '../components/import/Dropzone'
import PreviewTable from '../components/import/PreviewTable'
import { PanelSkeleton, Skeleton } from '../components/import/Skeleton'

type Stage = 0 | 1 | 2 | 3
const ISSUE_PAGE = 25
const isFinished = (job: Job | null) => !!job && ['completed', 'failed', 'cancelled'].includes(job.status)

export default function ImportStudents() {
  return <ToastProvider><ImportWorkflow /></ToastProvider>
}

function ImportWorkflow() {
  const toast = useToast()
  const [config, setConfig] = useState<ImportConfig | null>(null)
  const [configError, setConfigError] = useState<string | null>(null)
  const [stage, setStage] = useState<Stage>(0)
  const [upload, setUpload] = useState<UploadInfo | null>(null)
  const [uploading, setUploading] = useState(false)
  const [uploadError, setUploadError] = useState<string | null>(null)
  const [mapping, setMapping] = useState<Mapping>({})
  const [mode, setMode] = useState<ImportMode>('insert_only')
  const [mapFilter, setMapFilter] = useState<'all' | 'mapped' | 'unmapped'>('all')
  const [validateJob, setValidateJob] = useState<Job | null>(null)
  const [importJob, setImportJob] = useState<Job | null>(null)
  const [activeJobId, setActiveJobId] = useState<string | null>(null)
  const [starting, setStarting] = useState(false)
  const [stageError, setStageError] = useState<string | null>(null)
  const [issues, setIssues] = useState<Issue[]>([])
  const [issueTotal, setIssueTotal] = useState(0)
  const [issueOffset, setIssueOffset] = useState(0)
  const [issueCode, setIssueCode] = useState('')
  const [issuesLoading, setIssuesLoading] = useState(false)
  const [previewIssues, setPreviewIssues] = useState<Issue[]>([])
  const [confirmImport, setConfirmImport] = useState(false)
  const [confirmDiscard, setConfirmDiscard] = useState(false)
  const headingRef = useRef<HTMLHeadingElement>(null)

  const loadConfig = useCallback(() => {
    setConfigError(null)
    importApi.config().then(setConfig).catch(e => setConfigError(errorMessage(e)))
  }, [])
  useEffect(loadConfig, [loadConfig])
  useEffect(() => { headingRef.current?.focus() }, [stage])

  const running = !!activeJobId
  useEffect(() => {
    if (!running) return
    const warn = (e: BeforeUnloadEvent) => { e.preventDefault() }
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [running])

  const fields = config?.fields ?? []
  const fieldByKey = useMemo(() => new Map(fields.map(f => [f.key, f])), [fields])
  const missing = useMemo(() => missingRequired(mapping, mode, fields), [mapping, mode, fields])

  /* ---------- issues -------------------------------------------------------------------- */
  const loadIssues = useCallback(async (jobId: string, offset: number, code: string) => {
    setIssuesLoading(true)
    try {
      const page = await importApi.issues(jobId, offset, ISSUE_PAGE, code || undefined)
      setIssues(page.items); setIssueTotal(page.total); setIssueOffset(offset)
    } catch (e) { toast.push('error', errorMessage(e)) } finally { setIssuesLoading(false) }
  }, [toast])

  /* ---------- job polling --------------------------------------------------------------- */
  const onUpdate = useRef<(job: Job) => void>(() => undefined)
  onUpdate.current = (job: Job) => {
    if (job.kind === 'validate') setValidateJob(job); else setImportJob(job)
    if (!isFinished(job)) return
    setActiveJobId(null)
    if (job.status === 'failed') { toast.push('error', job.error ?? 'The job failed.'); return }
    if (job.status === 'cancelled') { toast.push('info', 'Import cancelled. No changes were saved.'); return }
    if (job.kind === 'validate') {
      toast.push('success', 'Validation finished.')
      void loadIssues(job.job_id, 0, '')
      const last = upload?.preview.at(-1)?.row
      if (last) importApi.rowIssues(job.job_id, 1, last).then(setPreviewIssues).catch(() => undefined)
    } else {
      const r = job.result
      toast.push(r?.roster_saved === false ? 'error' : 'success',
        r?.roster_saved === false
          ? 'Students were imported, but the uploaded spreadsheet could not be saved for future updates.'
          : `Import complete: ${r?.inserted ?? 0} added, ${r?.updated ?? 0} updated.`)
    }
  }
  useEffect(() => {
    if (!activeJobId) return
    let stopped = false
    let timer: ReturnType<typeof setTimeout>
    const tick = async () => {
      try {
        const job = await importApi.job(activeJobId)
        if (stopped) return
        onUpdate.current(job)
        if (isFinished(job)) return
      } catch (e) {
        if (stopped) return
        if (!(e instanceof ApiError) || e.status === 404 || e.status === 401) { setActiveJobId(null); setStageError(errorMessage(e)); return }
      }
      timer = setTimeout(tick, 600)
    }
    void tick()
    return () => { stopped = true; clearTimeout(timer) }
  }, [activeJobId])

  /* ---------- actions ------------------------------------------------------------------- */
  const resetAll = useCallback(() => {
    setStage(0); setUpload(null); setMapping({}); setMode('insert_only'); setValidateJob(null); setImportJob(null)
    setActiveJobId(null); setIssues([]); setPreviewIssues([]); setIssueTotal(0); setIssueOffset(0); setIssueCode('')
    setStageError(null); setUploadError(null)
  }, [])

  const handleFile = async (file: File) => {
    if (!config) return
    setUploadError(null)
    const problem = precheckFile(file, config.limits.max_upload_mb, config.limits.extensions)
    if (problem) { setUploadError(problem); toast.push('error', problem); return }
    setUploading(true)
    try {
      const info = await importApi.upload(file)
      if (upload) void importApi.discard(upload.upload_id).catch(() => undefined)
      setUpload(info); setMapping(suggestionsToMapping(info.suggested_mapping)); setValidateJob(null); setStage(1)
      toast.push('success', `Loaded ${info.total_rows.toLocaleString()} rows from ${info.filename}.`)
    } catch (e) { setUploadError(errorMessage(e)); toast.push('error', errorMessage(e)) } finally { setUploading(false) }
  }

  const discardAndReset = async () => {
    setConfirmDiscard(false)
    if (upload) await importApi.discard(upload.upload_id).catch(() => undefined)
    resetAll(); toast.push('info', 'Upload discarded.')
  }

  const changeColumn = (field: string, value: string) => {
    const { mapping: next, displaced } = assignColumn(mapping, field, value === '' ? null : Number(value))
    setMapping(next)
    if (displaced) toast.push('info', `“${fieldByKey.get(displaced)?.label}” is now unmapped because its column was reassigned.`)
  }

  const startValidation = async () => {
    if (!upload) return
    setStarting(true); setStageError(null)
    try {
      const job = await importApi.validate(upload.upload_id, toRequestMapping(mapping), mode)
      setValidateJob(job); setIssues([]); setPreviewIssues([]); setIssueCode(''); setStage(2); setActiveJobId(job.job_id)
    } catch (e) { setStageError(errorMessage(e)); toast.push('error', errorMessage(e)) } finally { setStarting(false) }
  }

  const startImport = async () => {
    if (!upload) return
    setConfirmImport(false); setStarting(true); setStageError(null)
    try {
      const job = await importApi.start(upload.upload_id, toRequestMapping(mapping), mode)
      setImportJob(job); setStage(3); setActiveJobId(job.job_id)
    } catch (e) { setStageError(errorMessage(e)); toast.push('error', errorMessage(e)) } finally { setStarting(false) }
  }

  const cancelJob = async (job: Job) => {
    try { onUpdate.current(await importApi.cancel(job.job_id)); toast.push('info', 'Cancellation requested…') }
    catch (e) { toast.push('error', errorMessage(e)) }
  }

  const downloadErrors = (job: Job) => importApi.downloadErrors(job.job_id).catch(e => toast.push('error', errorMessage(e)))

  /* ---------- derived ------------------------------------------------------------------- */
  const fieldLabels = useMemo(() => {
    const labels: (string | undefined)[] = Array(upload?.headers.length ?? 0).fill(undefined)
    for (const [key, col] of Object.entries(mapping)) if (col !== null && col !== undefined) labels[col] = fieldByKey.get(key)?.label
    return labels
  }, [mapping, upload, fieldByKey])
  const issueIndex = useMemo(() => indexIssues(previewIssues), [previewIssues])
  const flaggedRows = useMemo(() => rowsWithIssues(previewIssues), [previewIssues])
  const summary = validateJob?.summary ?? null
  const validated = validateJob?.status === 'completed' && !!summary
  const importable = validated ? summary.valid_rows : 0

  return (
    <>
      <PageHeading title="Import student data"
        description="Download the CSV template with all 33 import fields, open it in Excel or another spreadsheet app, then upload your completed file."
        actions={<button className="button button-secondary" onClick={() => importApi.downloadTemplate().catch(e => toast.push('error', errorMessage(e)))}>
          <Download size={16} /> Download CSV template</button>} />
      <Stepper stage={stage} />

      {configError && <Notice tone="error">{configError} <button className="text-button" onClick={loadConfig}>Try again</button></Notice>}
      {!config && !configError && <Panel title="Preparing import"><PanelSkeleton label="Loading import settings" rows={3} /></Panel>}

      {config && stage === 0 && (
        <Panel title="Upload a file" subtitle="One sheet per file. The first visible sheet of a workbook is used.">
          {uploadError && <Notice tone="error" onDismiss={() => setUploadError(null)}>{uploadError}</Notice>}
          {uploading
            ? <PanelSkeleton label="Reading your file" rows={3} />
            : <Dropzone onFile={handleFile} maxMb={config.limits.max_upload_mb} accept={config.limits.extensions} />}
          <h2 ref={headingRef} tabIndex={-1} className="sr-only">Step 1 of 4: Upload</h2>
        </Panel>
      )}

      {config && stage >= 1 && upload && (
        <>
          <FileCard upload={upload} locked={running} onReplace={() => setConfirmDiscard(true)} />
          {stageError && <Notice tone="error" onDismiss={() => setStageError(null)}>{stageError}</Notice>}
        </>
      )}

      {config && stage === 1 && upload && (
        <>
          <h2 ref={headingRef} tabIndex={-1} className="stage-title">Step 2 of 4: Preview &amp; mapping</h2>
          <Panel flush title="Spreadsheet preview"
            subtitle={`First ${Math.min(upload.preview.length, upload.preview_limit)} of ${upload.total_rows.toLocaleString()} rows. Row numbers match your spreadsheet.`}>
            <PreviewTable headers={upload.headers} rows={upload.preview} fieldLabels={fieldLabels} />
          </Panel>
          <Panel title="Import mode" subtitle="Choose how rows are matched against existing students.">
            <fieldset className="mode-group">
              <legend className="sr-only">Import mode</legend>
              {(Object.keys(MODE_COPY) as ImportMode[]).map(m => (
                <label key={m} className={`mode-option ${mode === m ? 'is-selected' : ''}`}>
                  <input type="radio" name="import-mode" value={m} checked={mode === m} onChange={() => setMode(m)} />
                  <span><strong>{MODE_COPY[m].title}</strong><small>{MODE_COPY[m].body}</small></span>
                </label>
              ))}
            </fieldset>
          </Panel>
          <Panel flush title="Column mapping" subtitle="We matched columns by name. Review and correct anything that looks wrong."
            action={<div className="segmented" role="group" aria-label="Filter fields">
              {(['all', 'mapped', 'unmapped'] as const).map(f => <button key={f} aria-pressed={mapFilter === f} onClick={() => setMapFilter(f)}>{f[0].toUpperCase() + f.slice(1)}</button>)}
            </div>}>
            {missing.length > 0 && (
              <div className="panel-body" style={{ paddingBottom: 0 }}>
                <Notice tone="error" icon={<TriangleAlert size={16} />}>
                  {missing.includes('__any_field__') ? 'Map at least one field to update. ' : ''}
                  {missing.filter(k => k !== '__any_field__').length > 0 && <>Still required for this mode: <strong>{missing.filter(k => k !== '__any_field__').map(k => fieldByKey.get(k)?.label).join(', ')}</strong>.</>}
                </Notice>
              </div>
            )}
            <div className="table-wrap">
              <table className="data-table map-table">
                <thead><tr><th scope="col">Student field</th><th scope="col">Spreadsheet column</th><th scope="col">Match</th><th scope="col">Sample value</th></tr></thead>
                <tbody>
                  {fields.filter(f => mapFilter === 'all' || (mapFilter === 'mapped') === (mapping[f.key] !== null && mapping[f.key] !== undefined)).map(f => {
                    const col = mapping[f.key] ?? null
                    const s = upload.suggested_mapping[f.key]
                    const required = (f.required_for_insert || f.key === 'student_id') && mode !== 'update_existing'
                    const isMissing = missing.includes(f.key)
                    return (
                      <tr key={f.key} className={isMissing ? 'map-missing' : undefined}>
                        <td><label htmlFor={`map-${f.key}`}><strong>{f.label}</strong>{required && <>{' '}<span className="req-tag">Required</span></>}</label><small className="map-key">{f.key}</small></td>
                        <td>
                          <select id={`map-${f.key}`} className="input" value={col ?? ''} onChange={e => changeColumn(f.key, e.target.value)}>
                            <option value="">— Not imported —</option>
                            {upload.headers.map((_, i) => <option key={i} value={i}>{columnLabel(upload.headers, i)}</option>)}
                          </select>
                        </td>
                        <td>{col === null ? <span className="muted-cell">—</span>
                          : s && s.column === col ? <span className={`pill ${s.confidence >= 0.9 ? 'risk-low' : 'risk-moderate'}`} title={s.reason}><i />{s.confidence >= 0.9 ? 'Auto' : 'Likely'} · {Math.round(s.confidence * 100)}%</span>
                          : <span className="pill risk-neutral"><i />Manual</span>}</td>
                        <td className="sample-cell">{col !== null ? (upload.preview.find(r => r.cells[col])?.cells[col] ?? '—') : '—'}</td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </Panel>
          <div className="stage-actions">
            <button className="button button-secondary" onClick={() => setConfirmDiscard(true)}><ArrowLeft size={16} /> Choose a different file</button>
            <span className="stage-hint">{missing.length ? 'Complete the required mappings to continue.' : `${Object.values(mapping).filter(v => v !== null).length} fields mapped.`}</span>
            <button className="button button-primary" disabled={missing.length > 0 || starting} onClick={startValidation}>
              <ListChecks size={16} /> {starting ? 'Starting…' : 'Validate file'}
            </button>
          </div>
        </>
      )}

      {config && stage === 2 && upload && (
        <>
          <h2 ref={headingRef} tabIndex={-1} className="stage-title">Step 3 of 4: Validate</h2>
          {validateJob && !isFinished(validateJob) && <JobProgress job={validateJob} onCancel={() => cancelJob(validateJob)} />}
          {validateJob?.status === 'failed' && <Notice tone="error">{validateJob.error}</Notice>}
          {validateJob?.status === 'cancelled' && <Notice>Validation was cancelled.</Notice>}
          {!validateJob || (!isFinished(validateJob) && !summary) ? <div className="summary-grid" aria-busy="true">{[0, 1, 2, 3].map(i => <div className="metric-card" key={i}><Skeleton height={14} width="50%" /><Skeleton height={32} width="40%" /></div>)}</div> : null}
          {validated && summary && (
            <>
              <div className="summary-grid">
                <SummaryCard label="Total rows" value={summary.total_rows} sub={`${upload.headers.length} columns in file`} />
                <SummaryCard tone="good" label="Valid records" value={summary.valid_rows} sub={`${summary.will_insert} to add · ${summary.will_update} to update`} />
                <SummaryCard tone={summary.duplicate_rows ? 'warn' : undefined} label="Duplicates" value={summary.duplicate_rows} sub="Repeated in file or already in database" />
                <SummaryCard tone={summary.invalid_rows ? 'bad' : undefined} label="Invalid records" value={summary.invalid_rows} sub="Rows with errors will be skipped" />
              </div>
              {summary.issues_truncated && <Notice>Only the first issues are listed; the downloadable error report contains the same capped list.</Notice>}
              {summary.generated_ids > 0 && <Notice tone="info">{summary.generated_ids} new student(s) have no Student ID and will receive generated IDs.</Notice>}
              <Panel flush title="Rows to review" subtitle="Every problem with its spreadsheet row number and what to fix."
                action={<div className="heading-actions">
                  <select className="input" aria-label="Filter problems by type" value={issueCode} onChange={e => { setIssueCode(e.target.value); void loadIssues(validateJob.job_id, 0, e.target.value) }}>
                    <option value="">All problems</option>
                    {Object.entries(CODE_LABEL).map(([c, l]) => <option key={c} value={c}>{l}</option>)}
                  </select>
                  <button className="button button-secondary" disabled={!summary.issue_count} onClick={() => downloadErrors(validateJob)}><Download size={16} /> Error report</button>
                </div>}>
                {issuesLoading ? <div className="panel-body"><PanelSkeleton label="Loading problems" rows={4} /></div>
                  : issues.length === 0 ? <EmptyState icon={<ShieldCheck size={24} />} title={issueCode ? 'No problems of this type' : 'No problems found'}
                      body={issueCode ? 'Try another filter.' : 'Every row passed validation.'} />
                  : <IssueTable issues={issues} />}
                {issueTotal > ISSUE_PAGE && (
                  <div className="table-footer">
                    <span>{issueOffset + 1}–{Math.min(issueOffset + ISSUE_PAGE, issueTotal)} of {issueTotal.toLocaleString()} problems</span>
                    <div className="heading-actions">
                      <button className="button button-secondary" disabled={issueOffset === 0} onClick={() => loadIssues(validateJob.job_id, Math.max(0, issueOffset - ISSUE_PAGE), issueCode)}>Previous</button>
                      <button className="button button-secondary" disabled={issueOffset + ISSUE_PAGE >= issueTotal} onClick={() => loadIssues(validateJob.job_id, issueOffset + ISSUE_PAGE, issueCode)}>Next</button>
                    </div>
                  </div>
                )}
              </Panel>
              <Panel flush title="Preview with highlighted cells" subtitle="Cells with errors are outlined. Hover or focus a cell to read the problem.">
                <PreviewTable headers={upload.headers} rows={upload.preview} fieldLabels={fieldLabels} issueIndex={issueIndex} flaggedRows={flaggedRows} />
              </Panel>
            </>
          )}
          <div className="stage-actions">
            <button className="button button-secondary" disabled={running} onClick={() => { setStage(1); setValidateJob(null) }}><ArrowLeft size={16} /> Back to mapping</button>
            <span className="stage-hint">{validated ? (importable ? `${importable.toLocaleString()} valid row(s) will be imported. Invalid and duplicate rows are skipped.` : 'There are no valid rows to import.') : ''}</span>
            <button className="button button-primary" disabled={!validated || importable === 0 || starting} onClick={() => setConfirmImport(true)}>
              <PlayCircle size={16} /> Import {importable ? importable.toLocaleString() : ''} records
            </button>
          </div>
        </>
      )}

      {config && stage === 3 && (
        <>
          <h2 ref={headingRef} tabIndex={-1} className="stage-title">Step 4 of 4: Import</h2>
          {importJob && !isFinished(importJob) && <JobProgress job={importJob} onCancel={() => cancelJob(importJob)} />}
          {importJob?.status === 'failed' && <Notice tone="error" icon={<CircleAlert size={16} />}>{importJob.error}</Notice>}
          {importJob?.status === 'cancelled' && <Notice icon={<CircleAlert size={16} />}>Import cancelled. No changes were saved to the student database.</Notice>}
          {importJob?.status === 'completed' && importJob.result && <Results job={importJob} onDownload={() => downloadErrors(importJob)} />}
          {importJob && !isFinished(importJob) && <div className="summary-grid" aria-busy="true">{[0, 1, 2, 3].map(i => <div className="metric-card" key={i}><Skeleton height={14} width="50%" /><Skeleton height={32} width="40%" /></div>)}</div>}
          <div className="stage-actions">
            <button className="button button-secondary" disabled={running} onClick={() => { setStage(2); setImportJob(null) }}><ArrowLeft size={16} /> Back to validation</button>
            <span className="stage-hint" />
            <div className="heading-actions">
              {importJob?.status === 'completed' && <Link className="button button-secondary" to="/students"><Users size={16} /> View students</Link>}
              <button className="button button-primary" disabled={running} onClick={resetAll}><RefreshCcw size={16} /> Import another file</button>
            </div>
          </div>
        </>
      )}

      {confirmImport && summary && (
        <Modal title="Import these records?" onClose={() => setConfirmImport(false)} footer={<>
          <button className="button button-secondary" onClick={() => setConfirmImport(false)}>Cancel</button>
          <button className="button button-primary" onClick={startImport}><Check size={16} /> Confirm import</button></>}>
          <p>This changes the live student data and refreshes dashboards, risk indicators and scores.</p>
          <ul className="import-tips" style={{ marginTop: 12 }}>
            <li>Mode: <strong>{MODE_COPY[mode].title}</strong></li>
            {summary.will_insert > 0 && <li><strong>{summary.will_insert.toLocaleString()}</strong> new student(s) will be added.</li>}
            {summary.will_update > 0 && <li><strong>{summary.will_update.toLocaleString()}</strong> existing student(s) will be updated.</li>}
            <li><strong>{(summary.total_rows - summary.valid_rows).toLocaleString()}</strong> row(s) will be skipped.</li>
          </ul>
          <p style={{ marginTop: 12, color: 'var(--muted)' }}>The server validates the file again before saving. Changes are saved together, so a failure leaves your data untouched.</p>
        </Modal>
      )}
      {confirmDiscard && (
        <Modal title="Discard this upload?" onClose={() => setConfirmDiscard(false)} footer={<>
          <button className="button button-secondary" onClick={() => setConfirmDiscard(false)}>Keep working</button>
          <button className="button button-primary" onClick={discardAndReset}><Trash2 size={16} /> Discard upload</button></>}>
          <p>Your column mapping and validation results for <strong>{upload?.filename}</strong> will be lost. No student data has been changed.</p>
        </Modal>
      )}
    </>
  )
}

/* ---------- presentational pieces ------------------------------------------------------- */
function Stepper({ stage }: { stage: Stage }) {
  return (
    <ol className="stepper" aria-label="Import progress">
      {STEPS.map((label, i) => (
        <li key={label} className={i < stage ? 'is-done' : i === stage ? 'is-current' : ''} aria-current={i === stage ? 'step' : undefined}>
          <span className="step-dot" aria-hidden="true">{i < stage ? <Check size={13} /> : i + 1}</span>
          <span className="step-label">{label}</span>
          <span className="sr-only">{i < stage ? ' (completed)' : i === stage ? ' (current step)' : ''}</span>
        </li>
      ))}
    </ol>
  )
}

function FileCard({ upload, locked, onReplace }: { upload: UploadInfo; locked: boolean; onReplace: () => void }) {
  return (
    <section className="file-card" aria-label="Selected file">
      <FileSpreadsheet size={22} aria-hidden="true" />
      <div className="file-meta">
        <strong>{upload.filename}</strong>
        <span>{upload.format.toUpperCase()} · {formatBytes(upload.size)} · {upload.total_rows.toLocaleString()} data rows · {upload.headers.length} columns
          {upload.blank_rows_skipped > 0 && ` · ${upload.blank_rows_skipped} blank rows ignored`}</span>
      </div>
      <button className="button button-secondary" disabled={locked} onClick={onReplace}><Files size={16} /> Replace file</button>
    </section>
  )
}

function SummaryCard({ label, value, sub, tone }: { label: string; value: number; sub: string; tone?: 'good' | 'warn' | 'bad' }) {
  return (
    <article className={`metric-card summary-card ${tone ? `tone-${tone}` : ''}`}>
      <div className="metric-top"><span className="metric-label">{label}</span></div>
      <div className="metric-value">{value.toLocaleString()}</div>
      <div className="metric-bottom"><span>{sub}</span></div>
    </article>
  )
}

function JobProgress({ job, onCancel }: { job: Job; onCancel: () => void }) {
  return (
    <Panel title={job.kind === 'import' ? 'Importing students' : 'Validating file'} subtitle={job.phase}
      action={job.can_cancel ? <button className="button button-secondary" disabled={job.cancel_requested} onClick={onCancel}>{job.cancel_requested ? 'Cancelling…' : 'Cancel'}</button> : undefined}>
      <div className="progress" role="progressbar" aria-label={`${job.kind === 'import' ? 'Import' : 'Validation'} progress`} aria-valuemin={0} aria-valuemax={100} aria-valuenow={job.percent}>
        <i style={{ width: `${job.percent}%` }} />
      </div>
      <p className="progress-caption" role="status">{job.processed.toLocaleString()} of {job.total.toLocaleString()} rows · {job.percent}%
        {job.kind === 'import' && !job.can_cancel && ' · saving changes, cancellation is no longer possible'}</p>
    </Panel>
  )
}

function IssueTable({ issues }: { issues: Issue[] }) {
  return (
    <div className="table-wrap">
      <table className="data-table issue-table">
        <thead><tr><th scope="col">Row</th><th scope="col">Field</th><th scope="col">Column</th><th scope="col">Value</th><th scope="col">What to fix</th></tr></thead>
        <tbody>
          {issues.map((i, n) => (
            <tr key={`${i.row}-${i.field}-${n}`}>
              <td className="num"><strong>{i.row}</strong></td>
              <td>{i.field_label ?? '—'}</td>
              <td>{i.column !== null ? `${columnLetter(i.column)} · ${i.source_column}` : '—'}</td>
              <td className="issue-value">{i.value === '' ? <em>blank</em> : i.value}</td>
              <td><span className="pill risk-high"><i />{CODE_LABEL[i.code] ?? i.code}</span><span className="issue-msg">{i.message}</span></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function Results({ job, onDownload }: { job: Job; onDownload: () => void }) {
  const r = job.result!
  const skipped = r.skipped ?? 0
  return (
    <>
      <Notice tone={r.roster_saved === false ? 'error' : 'success'} icon={<Check size={16} />}>
        {r.message ?? 'Import finished. Student lists, dashboards, scores and risk indicators now include these changes.'}
      </Notice>
      <div className="summary-grid">
        <SummaryCard tone="good" label="Added" value={r.inserted} sub="New student records" />
        <SummaryCard tone="good" label="Updated" value={r.updated} sub="Existing records changed" />
        <SummaryCard tone={skipped ? 'warn' : undefined} label="Skipped" value={skipped} sub="Invalid, duplicate or not matched" />
        <SummaryCard label="Rows in file" value={r.total_rows ?? 0} sub={r.generated_ids ? `${r.generated_ids} IDs generated` : 'Processed server-side'} />
      </div>
      {(r.issue_count ?? 0) > 0 && (
        <Panel title="Skipped rows" subtitle={`${r.issue_count} problem(s) were found. Fix them in your spreadsheet and import again.`}
          action={<button className="button button-secondary" onClick={onDownload}><Download size={16} /> Download error report</button>}>
          <p className="stage-hint"><UserPlus size={14} style={{ verticalAlign: '-2px' }} /> The report lists each spreadsheet row, the field, the value and how to correct it.</p>
        </Panel>
      )}
    </>
  )
}
