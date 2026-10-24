import { apiUrl, getToken, get, notifyUnauthorized, write, ApiError } from './api'
import type { FieldInfo, Issue, Suggestion } from './importLogic'

export interface ImportConfig {
  fields: FieldInfo[]; modes: { value: string; label: string }[]
  limits: { max_upload_mb: number; max_rows: number; batch_size: number; extensions: string[] }; identifier: string
}
export interface UploadInfo {
  upload_id: string; filename: string; format: string; size: number; headers: string[]; total_rows: number
  blank_rows_skipped: number; preview: { row: number; cells: string[] }[]; preview_limit: number
  suggested_mapping: Record<string, Suggestion>; existing_student_count: number
}
export interface ValidationSummary {
  total_rows: number; valid_rows: number; duplicate_rows: number; invalid_rows: number; will_insert: number
  will_update: number; skipped_existing: number; skipped_not_found: number; unchanged_rows: number
  generated_ids: number; issue_count: number; issues_truncated: boolean
}
export interface ImportResult {
  inserted: number; updated: number; skipped?: number; total_rows?: number; invalid_rows?: number
  duplicate_rows?: number; generated_ids?: number; issue_count?: number; message?: string; roster_saved?: boolean
}
export type JobStatus = 'queued' | 'running' | 'completed' | 'failed' | 'cancelled'
export interface Job {
  job_id: string; upload_id: string; kind: 'validate' | 'import'; mode: string; status: JobStatus; phase: string
  processed: number; total: number; percent: number; can_cancel: boolean; cancel_requested: boolean
  error: string | null; summary: ValidationSummary | null; result: ImportResult | null; filename: string
}

const messageFrom = async (res: Response) => {
  try {
    const body = await res.json()
    return body?.error?.message ?? (typeof body?.detail === 'string' ? body.detail : null) ?? `Request failed (${res.status}).`
  } catch { return `Request failed (${res.status}).` }
}

async function authed(path: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers)
  const token = getToken()
  if (token) headers.set('Authorization', `Bearer ${token}`)
  let res: Response
  try { res = await fetch(apiUrl(path), { ...init, headers }) }
  catch { throw new ApiError('Cannot reach the Smart Campus API. Check that the backend is running on port 8000.', 0) }
  if (!res.ok) {
    if (res.status === 401) notifyUnauthorized()
    throw new ApiError(await messageFrom(res), res.status)
  }
  return res
}

export const importApi = {
  config: async () => (await get<ImportConfig>('/api/imports/config')).data,
  async upload(file: File): Promise<UploadInfo> {
    const form = new FormData()
    form.append('file', file)
    const body = await (await authed('/api/imports/uploads', { method: 'POST', body: form })).json()
    return body.data
  },
  discard: (uploadId: string) => authed(`/api/imports/uploads/${encodeURIComponent(uploadId)}`, { method: 'DELETE' }).then(() => undefined),
  validate: (uploadId: string, mapping: Record<string, number>, mode: string) =>
    write<Job>('POST', `/api/imports/uploads/${encodeURIComponent(uploadId)}/validate`, { mapping, mode }),
  start: (uploadId: string, mapping: Record<string, number>, mode: string) =>
    write<Job>('POST', `/api/imports/uploads/${encodeURIComponent(uploadId)}/import`, { mapping, mode }),
  job: async (jobId: string) => (await get<Job>(`/api/imports/jobs/${encodeURIComponent(jobId)}`)).data,
  cancel: async (jobId: string) => (await (await authed(`/api/imports/jobs/${encodeURIComponent(jobId)}/cancel`, { method: 'POST' })).json()).data as Job,
  issues: async (jobId: string, offset: number, limit: number, code?: string) => {
    const { data, meta } = await get<Issue[]>(`/api/imports/jobs/${encodeURIComponent(jobId)}/issues`, { offset, limit, code })
    return { items: data, total: meta.total ?? data.length }
  },
  rowIssues: async (jobId: string, firstRow: number, lastRow: number) =>
    (await get<Issue[]>(`/api/imports/jobs/${encodeURIComponent(jobId)}/issues/by-row`, { first_row: firstRow, last_row: lastRow })).data,
  /** Downloads need the bearer token, so fetch a blob and trigger the save from it. */
  async download(path: string, filename?: string) {
    const response = await authed(path)
    const blob = await response.blob()
    const disposition = response.headers.get('Content-Disposition')
    const downloadedName = filename ?? disposition?.match(/filename="?([^";]+)"?/i)?.[1] ?? 'download'
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url; a.download = downloadedName; document.body.appendChild(a); a.click(); a.remove()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
  },
  downloadTemplate: () => importApi.download('/api/imports/template', 'academia-student-import-template.csv'),
  downloadRoster: () => importApi.download('/api/imports/roster'),
  downloadErrors: (jobId: string) => importApi.download(`/api/imports/jobs/${encodeURIComponent(jobId)}/errors.csv`, `import-errors-${jobId.slice(0, 8)}.csv`),
}
