import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import ImportStudents from './ImportStudents'
import type { ImportConfig, Job, UploadInfo } from '../lib/importApi'

const mocks = vi.hoisted(() => ({
  config: vi.fn(), upload: vi.fn(), discard: vi.fn(), validate: vi.fn(), start: vi.fn(), job: vi.fn(), cancel: vi.fn(),
  issues: vi.fn(), rowIssues: vi.fn(), downloadErrors: vi.fn(), downloadTemplate: vi.fn(),
}))
vi.mock('../lib/importApi', () => ({ importApi: mocks }))

const FIELD = (key: string, label: string, required = false) => ({ key, label, kind: 'text' as const, group: 'g', required_for_insert: required, minimum: null, maximum: null, options: [], example: '' })
const CONFIG: ImportConfig = {
  fields: [FIELD('student_id', 'Student ID'), FIELD('student_name', 'Student name', true), FIELD('department', 'Department', true), FIELD('cgpa', 'CGPA')],
  modes: [], limits: { max_upload_mb: 10, max_rows: 20000, batch_size: 500, extensions: ['.xlsx', '.xls', '.csv'] }, identifier: 'student_id',
}
const UPLOAD: UploadInfo = {
  upload_id: 'up1', filename: 'roster.csv', format: 'csv', size: 2048, headers: ['Roll No', 'Name', 'Dept', 'CGPA'], total_rows: 3, blank_rows_skipped: 0,
  preview: [{ row: 2, cells: ['STU20269001', 'Asha', 'CSE', '8.1'] }, { row: 3, cells: ['STU20269002', 'Ravi', 'CSE', '11'] }, { row: 4, cells: ['STU20269003', 'Mina', 'ECE', '7.2'] }],
  preview_limit: 100, existing_student_count: 10,
  suggested_mapping: { student_id: { column: 0, confidence: 0.92, reason: 'Known alias' }, student_name: { column: 1, confidence: 0.92, reason: 'Known alias' },
    department: { column: 2, confidence: 0.92, reason: 'Known alias' }, cgpa: { column: 3, confidence: 1, reason: 'Exact column name' } },
}
const baseJob = (over: Partial<Job>): Job => ({ job_id: 'job1', upload_id: 'up1', kind: 'validate', mode: 'insert_only', status: 'completed', phase: 'Done', processed: 3, total: 3, percent: 100,
  can_cancel: false, cancel_requested: false, error: null, summary: null, result: null, filename: 'roster.csv', ...over })
const SUMMARY = { total_rows: 3, valid_rows: 2, duplicate_rows: 0, invalid_rows: 1, will_insert: 2, will_update: 0, skipped_existing: 0, skipped_not_found: 0,
  unchanged_rows: 0, generated_ids: 0, issue_count: 1, issues_truncated: false }
const ISSUE = { row: 3, field: 'cgpa', field_label: 'CGPA', column: 3, source_column: 'CGPA', value: '11', code: 'invalid_value', message: '11 is outside the allowed range 0–10.' }

const csvFile = (name = 'roster.csv') => new File(['Roll No,Name\n1,A'], name, { type: 'text/csv' })
const setup = () => { const user = userEvent.setup(); render(<MemoryRouter><ImportStudents /></MemoryRouter>); return user }
const uploadFile = async (user: ReturnType<typeof userEvent.setup>, file = csvFile()) => {
  await screen.findByText('Upload a file')
  await user.upload(screen.getByTestId('file-input'), file)
}

beforeEach(() => {
  Object.values(mocks).forEach(m => m.mockReset())
  mocks.config.mockResolvedValue(CONFIG); mocks.upload.mockResolvedValue(UPLOAD); mocks.discard.mockResolvedValue(undefined)
  mocks.issues.mockResolvedValue({ items: [ISSUE], total: 1 }); mocks.rowIssues.mockResolvedValue([ISSUE])
  mocks.downloadErrors.mockResolvedValue(undefined); mocks.downloadTemplate.mockResolvedValue(undefined)
})

describe('upload step', () => {
  it('shows a loading skeleton, then the upload area with a four-step indicator', async () => {
    setup()
    expect(screen.getByRole('status', { name: 'Loading import settings' })).toBeInTheDocument()
    expect(await screen.findByText('Drag and drop a spreadsheet here')).toBeInTheDocument()
    expect(screen.queryByText('Required fields')).not.toBeInTheDocument()
    expect(screen.queryByRole('region', { name: /all \d+ import fields/i })).not.toBeInTheDocument()
    const steps = within(screen.getByRole('list', { name: 'Import progress' })).getAllByRole('listitem')
    expect(steps.map(s => s.textContent?.replace(/\(.*\)/, '').trim())).toEqual(['1Upload', '2Preview & mapping', '3Validate', '4Import'])
    expect(steps[0]).toHaveAttribute('aria-current', 'step')
  })

  it('rejects unsupported files before any upload request', async () => {
    const user = userEvent.setup({ applyAccept: false })
    render(<MemoryRouter><ImportStudents /></MemoryRouter>)
    await screen.findByText('Upload a file')
    await user.upload(screen.getByTestId('file-input'), new File(['x'], 'notes.pdf', { type: 'application/pdf' }))
    expect((await screen.findAllByText(/not supported/))[0]).toBeInTheDocument()
    expect(mocks.upload).not.toHaveBeenCalled()
  })

  it('shows server upload errors and stays on the upload step', async () => {
    mocks.upload.mockRejectedValue(new Error('The workbook is corrupt.'))
    const user = setup(); await uploadFile(user)
    expect((await screen.findAllByText('The workbook is corrupt.'))[0]).toBeInTheDocument()
    expect(screen.getByText('Upload a file')).toBeInTheDocument()
  })

  it('offers the CSV template download through the API', async () => {
    const user = setup(); await screen.findByText('Upload a file')
    await user.click(screen.getByRole('button', { name: /download csv template/i }))
    expect(mocks.downloadTemplate).toHaveBeenCalled()
  })
})

describe('preview and column mapping', () => {
  it('previews rows with spreadsheet row numbers and applies suggested mappings', async () => {
    const user = setup(); await uploadFile(user)
    expect(await screen.findByText('roster.csv')).toBeInTheDocument()
    expect(screen.getByRole('region', { name: /spreadsheet preview/i })).toBeInTheDocument()
    expect(screen.getByRole('rowheader', { name: '2' })).toBeInTheDocument()
    expect(screen.getByRole('rowheader', { name: '4' })).toBeInTheDocument()
    expect(screen.getByLabelText(/^Student name/)).toHaveValue('1')
    expect(screen.getByLabelText(/^CGPA/)).toHaveValue('3')
    expect(screen.getAllByText(/Auto · 92%/).length).toBeGreaterThan(0)
    expect(screen.getByRole('button', { name: /validate file/i })).toBeEnabled()
  })

  it('blocks validation until required fields are mapped and explains what is missing', async () => {
    const user = setup(); await uploadFile(user)
    await user.selectOptions(await screen.findByLabelText(/^Department/), '')
    expect(screen.getByRole('button', { name: /validate file/i })).toBeDisabled()
    expect(screen.getByText(/Still required for this mode/)).toHaveTextContent('Department')
  })

  it('moves a column to a new field and unmaps the previous owner', async () => {
    const user = setup(); await uploadFile(user)
    await user.selectOptions(await screen.findByLabelText(/^Department/), '1')   // column B was "Student name"
    expect(screen.getByLabelText(/^Student name/)).toHaveValue('')
    expect(await screen.findByText(/“Student name” is now unmapped/)).toBeInTheDocument()
  })

  it('offers three explicit import modes and sends the chosen one', async () => {
    mocks.validate.mockResolvedValue(baseJob({ status: 'running', processed: 0, percent: 0 }))
    mocks.job.mockResolvedValue(baseJob({ summary: SUMMARY }))
    const user = setup(); await uploadFile(user)
    const modes = await screen.findAllByRole('radio')
    expect(modes.map(m => (m as HTMLInputElement).value)).toEqual(['insert_only', 'update_existing', 'insert_or_update'])
    await user.click(screen.getByRole('radio', { name: /insert or update/i }))
    await user.click(screen.getByRole('button', { name: /validate file/i }))
    expect(mocks.validate).toHaveBeenCalledWith('up1', { student_id: 0, student_name: 1, department: 2, cgpa: 3 }, 'insert_or_update')
  })
})

describe('validation results', () => {
  const toValidation = async (user: ReturnType<typeof userEvent.setup>) => {
    mocks.validate.mockResolvedValue(baseJob({ status: 'running', processed: 0, percent: 0 }))
    mocks.job.mockResolvedValue(baseJob({ summary: SUMMARY }))
    await uploadFile(user)
    await user.click(await screen.findByRole('button', { name: /validate file/i }))
  }

  it('shows the four summary cards from the server response', async () => {
    const user = setup(); await toValidation(user)
    const card = async (label: string) => (await screen.findByText(label)).closest('article') as HTMLElement
    expect(await card('Total rows')).toHaveTextContent('3')
    expect(await card('Valid records')).toHaveTextContent('2')
    expect(await card('Valid records')).toHaveTextContent('2 to add · 0 to update')
    expect(await card('Duplicates')).toHaveTextContent('0')
    expect(await card('Invalid records')).toHaveTextContent('1')
  })

  it('lists errors with row numbers and highlights the invalid cell in the preview', async () => {
    const user = setup(); await toValidation(user)
    expect(await screen.findByText('11 is outside the allowed range 0–10.')).toBeInTheDocument()
    const row = screen.getByText('11 is outside the allowed range 0–10.').closest('tr') as HTMLElement
    expect(within(row).getByText('3')).toBeInTheDocument()                    // spreadsheet row number
    expect(within(row).getByText('Invalid value')).toBeInTheDocument()
    expect(within(row).getByText('D · CGPA')).toBeInTheDocument()
    await waitFor(() => expect(document.querySelectorAll('td.cell-invalid[aria-invalid="true"]')).toHaveLength(1))
    expect(document.querySelector('td.cell-invalid')).toHaveTextContent('11')
    expect(mocks.rowIssues).toHaveBeenCalledWith('job1', 1, 4)
  })

  it('downloads the error report', async () => {
    const user = setup(); await toValidation(user)
    await user.click(await screen.findByRole('button', { name: /error report/i }))
    expect(mocks.downloadErrors).toHaveBeenCalledWith('job1')
  })

  it('shows an empty state when every row is valid', async () => {
    mocks.issues.mockResolvedValue({ items: [], total: 0 })
    mocks.validate.mockResolvedValue(baseJob({ status: 'running' }))
    mocks.job.mockResolvedValue(baseJob({ summary: { ...SUMMARY, invalid_rows: 0, valid_rows: 3, issue_count: 0 } }))
    const user = setup(); await uploadFile(user)
    await user.click(await screen.findByRole('button', { name: /validate file/i }))
    expect(await screen.findByText('No problems found')).toBeInTheDocument()
  })
})

describe('import and results', () => {
  const toConfirm = async (user: ReturnType<typeof userEvent.setup>) => {
    mocks.validate.mockResolvedValue(baseJob({ status: 'running' }))
    mocks.job.mockResolvedValueOnce(baseJob({ summary: SUMMARY }))
    await uploadFile(user)
    await user.click(await screen.findByRole('button', { name: /validate file/i }))
    await user.click(await screen.findByRole('button', { name: /import 2 records/i }))
  }

  it('asks for confirmation, then starts the server import and shows final results', async () => {
    mocks.start.mockResolvedValue(baseJob({ kind: 'import', job_id: 'job2', status: 'running', processed: 0, percent: 0, can_cancel: true }))
    mocks.job.mockResolvedValue(baseJob({ kind: 'import', job_id: 'job2', summary: SUMMARY, result: { inserted: 2, updated: 0, skipped: 1, total_rows: 3, invalid_rows: 1, issue_count: 1 } }))
    const user = setup(); await toConfirm(user)
    const dialog = await screen.findByRole('dialog', { name: 'Import these records?' })
    expect(dialog).toHaveTextContent('2 new student(s) will be added')
    expect(mocks.start).not.toHaveBeenCalled()
    await user.click(within(dialog).getByRole('button', { name: /confirm import/i }))
    expect(mocks.start).toHaveBeenCalledWith('up1', expect.any(Object), 'insert_only')
    const added = (await screen.findByText('Added')).closest('article') as HTMLElement
    expect(added).toHaveTextContent('2')
    expect((screen.getByText('Skipped').closest('article') as HTMLElement)).toHaveTextContent('1')
    await user.click(screen.getByRole('button', { name: /download error report/i }))
    expect(mocks.downloadErrors).toHaveBeenCalledWith('job2')
    expect(screen.getByRole('link', { name: /view students/i })).toHaveAttribute('href', '/students')
  })

  it('does not start an import when the confirmation is dismissed', async () => {
    const user = setup(); await toConfirm(user)
    await user.click(await screen.findByRole('button', { name: 'Cancel' }))
    expect(mocks.start).not.toHaveBeenCalled()
  })

  it('shows progress and lets the admin cancel while cancellation is still safe', async () => {
    mocks.start.mockResolvedValue(baseJob({ kind: 'import', job_id: 'job2', status: 'running', processed: 1, percent: 33, can_cancel: true, phase: 'Validating rows' }))
    mocks.job.mockResolvedValue(baseJob({ kind: 'import', job_id: 'job2', status: 'running', processed: 1, percent: 33, can_cancel: true, phase: 'Validating rows' }))
    mocks.cancel.mockResolvedValue(baseJob({ kind: 'import', job_id: 'job2', status: 'cancelled', phase: 'Cancelled', result: { inserted: 0, updated: 0 } }))
    const user = setup(); await toConfirm(user)
    await user.click(within(await screen.findByRole('dialog')).getByRole('button', { name: /confirm import/i }))
    expect(await screen.findByRole('progressbar', { name: /import progress/i })).toHaveAttribute('aria-valuenow', '33')
    await user.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(mocks.cancel).toHaveBeenCalledWith('job2')
    expect(await screen.findByText(/No changes were saved to the student database/)).toBeInTheDocument()
  })

  it('reports a failed import honestly', async () => {
    mocks.start.mockResolvedValue(baseJob({ kind: 'import', job_id: 'job2', status: 'running' }))
    mocks.job.mockResolvedValue(baseJob({ kind: 'import', job_id: 'job2', status: 'failed', error: 'The import could not be saved. No changes were applied.' }))
    const user = setup(); await toConfirm(user)
    await user.click(within(await screen.findByRole('dialog')).getByRole('button', { name: /confirm import/i }))
    expect((await screen.findAllByText(/No changes were applied/))[0]).toBeInTheDocument()
    expect(screen.queryByText('Added')).not.toBeInTheDocument()
  })
})
