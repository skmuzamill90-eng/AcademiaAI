/** Pure helpers for the bulk student import flow (unit-tested; no React, no network). */

export type ImportMode = 'insert_only' | 'update_existing' | 'insert_or_update'
export interface FieldInfo {
  key: string; label: string; kind: 'text' | 'int' | 'float' | 'category'; group: string
  required_for_insert: boolean; minimum: number | null; maximum: number | null; options: string[]; example: string
}
export interface Suggestion { column: number; confidence: number; reason: string }
export type Mapping = Record<string, number | null>

export const STEPS = ['Upload', 'Preview & mapping', 'Validate', 'Import'] as const

export const MODE_COPY: Record<ImportMode, { title: string; body: string }> = {
  insert_only: { title: 'Insert only', body: 'Add new students. Rows whose Student ID already exists are skipped and never overwritten.' },
  update_existing: { title: 'Update existing', body: 'Change students that already exist, matched by Student ID. Blank cells keep the current value; unknown IDs are skipped.' },
  insert_or_update: { title: 'Insert or update', body: 'Match by Student ID: update the student if it exists, otherwise add a new one.' },
}

/** 0 -> A, 25 -> Z, 26 -> AA (matches spreadsheet column letters). */
export function columnLetter(index: number): string {
  let n = index, out = ''
  do { out = String.fromCharCode(65 + (n % 26)) + out; n = Math.floor(n / 26) - 1 } while (n >= 0)
  return out
}

export const columnLabel = (headers: string[], index: number) => `${columnLetter(index)} · ${headers[index] ?? ''}`

export const formatBytes = (bytes: number) =>
  bytes < 1024 ? `${bytes} B` : bytes < 1024 * 1024 ? `${(bytes / 1024).toFixed(1)} KB` : `${(bytes / 1024 / 1024).toFixed(1)} MB`

/** Quick client-side checks before upload. The server repeats and enforces all of them. */
export function precheckFile(file: { name: string; size: number }, maxMb: number, extensions: string[]): string | null {
  const lower = file.name.toLowerCase()
  if (!extensions.some(ext => lower.endsWith(ext))) return `“${file.name}” is not supported. Upload an Excel (.xlsx, .xls) or CSV (.csv) file.`
  if (file.size === 0) return `“${file.name}” is empty.`
  if (file.size > maxMb * 1024 * 1024) return `“${file.name}” is ${formatBytes(file.size)}. The limit is ${maxMb} MB.`
  return null
}

export function suggestionsToMapping(s: Record<string, Suggestion>): Mapping {
  return Object.fromEntries(Object.entries(s).map(([k, v]) => [k, v.column]))
}

/** Assign a column to a field. A column can feed only one field, so any previous owner is cleared. */
export function assignColumn(mapping: Mapping, field: string, column: number | null): { mapping: Mapping; displaced: string | null } {
  const next: Mapping = { ...mapping, [field]: column }
  let displaced: string | null = null
  if (column !== null) {
    for (const [k, v] of Object.entries(next)) if (k !== field && v === column) { next[k] = null; displaced = k }
  }
  return { mapping: next, displaced }
}

/** Fields that must be mapped before the chosen mode can run. Mirrors the server's rules. */
export function missingRequired(mapping: Mapping, mode: ImportMode, fields: FieldInfo[]): string[] {
  const mapped = (k: string) => mapping[k] !== null && mapping[k] !== undefined
  const out: string[] = []
  if (mode !== 'insert_only' && !mapped('student_id')) out.push('student_id')
  if (mode !== 'update_existing') for (const f of fields) if (f.required_for_insert && !mapped(f.key)) out.push(f.key)
  if (mode === 'update_existing' && !fields.some(f => f.key !== 'student_id' && mapped(f.key))) out.push('__any_field__')
  return out
}

export const toRequestMapping = (mapping: Mapping): Record<string, number> =>
  Object.fromEntries(Object.entries(mapping).filter((e): e is [string, number] => e[1] !== null && e[1] !== undefined))

export interface Issue {
  row: number; field: string | null; field_label: string | null; column: number | null
  source_column: string | null; value: string; code: string; message: string
}

/** Index issues by "row:column" so the preview table can highlight cells in O(1). */
export function indexIssues(issues: Issue[]): Map<string, Issue[]> {
  const map = new Map<string, Issue[]>()
  for (const i of issues) {
    if (i.column === null) continue
    const key = `${i.row}:${i.column}`
    map.set(key, [...(map.get(key) ?? []), i])
  }
  return map
}

export const rowsWithIssues = (issues: Issue[]) => new Set(issues.map(i => i.row))

export const CODE_LABEL: Record<string, string> = {
  invalid_value: 'Invalid value', required_missing: 'Required value missing', invalid_id: 'Invalid Student ID',
  missing_id: 'Student ID missing', duplicate_in_file: 'Duplicate in file', already_exists: 'Already exists', not_found: 'Not found',
}
