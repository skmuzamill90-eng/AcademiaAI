import { describe, expect, it } from 'vitest'
import {
  assignColumn, columnLetter, formatBytes, indexIssues, missingRequired, precheckFile, suggestionsToMapping,
  toRequestMapping, type FieldInfo, type Issue,
} from './importLogic'

const f = (key: string, required = false): FieldInfo => ({ key, label: key, kind: 'text', group: 'g', required_for_insert: required, minimum: null, maximum: null, options: [], example: '' })
const FIELDS = [f('student_id'), f('student_name', true), f('department', true), f('cgpa')]

describe('file pre-checks', () => {
  const ext = ['.xlsx', '.xls', '.csv']
  it('accepts supported files', () => {
    for (const name of ['a.xlsx', 'B.XLS', 'roster.csv']) expect(precheckFile({ name, size: 100 }, 10, ext)).toBeNull()
  })
  it('rejects unsupported, empty and oversized files with a clear message', () => {
    expect(precheckFile({ name: 'a.pdf', size: 100 }, 10, ext)).toMatch(/not supported/)
    expect(precheckFile({ name: 'a.csv', size: 0 }, 10, ext)).toMatch(/empty/)
    expect(precheckFile({ name: 'a.csv', size: 11 * 1024 * 1024 }, 10, ext)).toMatch(/limit is 10 MB/)
  })
  it('formats sizes', () => { expect(formatBytes(512)).toBe('512 B'); expect(formatBytes(2048)).toBe('2.0 KB'); expect(formatBytes(3 * 1024 * 1024)).toBe('3.0 MB') })
})

describe('column mapping', () => {
  it('names columns like a spreadsheet', () => {
    expect([0, 25, 26, 27, 701, 702].map(columnLetter)).toEqual(['A', 'Z', 'AA', 'AB', 'ZZ', 'AAA'])
  })
  it('converts server suggestions into an editable mapping', () => {
    expect(suggestionsToMapping({ cgpa: { column: 3, confidence: 1, reason: 'x' } })).toEqual({ cgpa: 3 })
  })
  it('lets one column feed only one field and reports the displaced field', () => {
    const { mapping, displaced } = assignColumn({ student_name: 1, department: 2 }, 'department', 1)
    expect(mapping).toEqual({ student_name: null, department: 1 })
    expect(displaced).toBe('student_name')
  })
  it('unmapping a field displaces nothing', () => {
    expect(assignColumn({ cgpa: 3 }, 'cgpa', null)).toEqual({ mapping: { cgpa: null }, displaced: null })
  })
  it('requires the identifier and a field for update-existing', () => {
    expect(missingRequired({}, 'update_existing', FIELDS)).toEqual(['student_id', '__any_field__'])
    expect(missingRequired({ student_id: 0, cgpa: 1 }, 'update_existing', FIELDS)).toEqual([])
  })
  it('requires core fields for modes that add students', () => {
    expect(missingRequired({}, 'insert_only', FIELDS)).toEqual(['student_name', 'department'])
    expect(missingRequired({ student_name: 1, department: 2 }, 'insert_only', FIELDS)).toEqual([])
    expect(missingRequired({ student_name: 1, department: 2 }, 'insert_or_update', FIELDS)).toEqual(['student_id'])
  })
  it('sends only mapped columns to the API', () => {
    expect(toRequestMapping({ a: 0, b: null, c: 2 })).toEqual({ a: 0, c: 2 })
  })
})

describe('validation issues', () => {
  const issue = (row: number, column: number | null, message: string): Issue =>
    ({ row, field: 'cgpa', field_label: 'CGPA', column, source_column: 'CGPA', value: '11', code: 'invalid_value', message })
  it('indexes issues by row and column for cell highlighting', () => {
    const map = indexIssues([issue(3, 7, 'too high'), issue(3, 7, 'not numeric'), issue(4, null, 'row level')])
    expect(map.get('3:7')?.map(i => i.message)).toEqual(['too high', 'not numeric'])
    expect(map.has('4:null')).toBe(false)
  })
})
