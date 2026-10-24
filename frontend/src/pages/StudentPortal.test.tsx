import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import StudentPortal from './StudentPortal'
import type { Profile } from '../lib/types'

const mocks = vi.hoisted(() => ({ get: vi.fn() }))
vi.mock('../lib/api', () => ({ get: mocks.get }))

const PROFILE: Profile & { institution: { id: string; name: string } } = {
  student_id: 'STU90000001',
  personal: {
    student_name: 'Asha Rao', department: 'CSE', year_of_study: 2, section: 'A', admission_year: 2025,
  },
  academics: { cgpa: 8.2, backlogs: 1, internal_score_pct: 76, semester_score_pct: 72, cgpa_scale_max: 10 },
  attendance: { overall_attendance_pct: 82, subjects_below_attendance_threshold: 1 },
  lms: { logins_last_30_days: 12, assignment_completion_pct: 84, avg_weekly_learning_hours: 4 },
  engagement: { events_attended: 2, hackathons_participated: 1, club_participation: 'Active', volunteer_hours: null },
  feedback: { student_satisfaction_1_to_5: 4, faculty_feedback_1_to_5: 3, support_requested: 'No', feedback_topic: null },
  skills: { technical_skill_score: 67, soft_skill_score: 73, certifications_count: 1, projects_count: 2 },
  placement: { aptitude_score: 60, coding_score: 58, mock_interview_score: null, resume_readiness_pct: 65, placement_status: 'Eligible' },
  success_score: {
    score: 71, coverage: 0.8,
    components: {
      academic: { score: 70, weight: 0.4 }, attendance: { score: 80, weight: 0.2 },
      lms: { score: 65, weight: 0.15 }, placement_readiness: { score: 72, weight: 0.25 },
    },
    note: 'Prototype score, not an official institutional measurement.',
  },
  segment: { name: 'Developing', description: 'Developing indicators' },
  risk: {
    academic: {
      level: 'Low', points: 1, max_points: 10, reasons: ['Attendance needs attention'],
      suggested_actions: ['Discuss attendance with your mentor'], missing_inputs: [], note: null, is_probability: false,
    },
    placement: {
      level: 'Low', points: 0, max_points: 10, reasons: [],
      suggested_actions: [], missing_inputs: [], note: null, is_probability: false,
    },
    disclaimer: 'Rule-based support indicators, not probabilities.',
  },
  recommendations: [{
    id: 'attendance_support', category: 'Attendance', priority: 'Medium',
    title: 'Attendance improvement support', description: 'Attendance is below the expected level.',
    suggested_steps: ['Agree on an attendance target.'],
    based_on: [{ indicator: 'overall_attendance_pct', label: 'Overall attendance %', value: 82 }],
    related_intervention_type: 'Attendance counselling',
    existing_open_intervention: { intervention_id: 'INT0001', status: 'Assigned' },
  }],
  interventions: [{
    intervention_id: 'INT0001', student_id: 'STU90000001', intervention_type: 'Mentoring',
    assigned_date: '2026-10-24', status: 'Assigned', follow_up_notes: 'PRIVATE STAFF NOTE',
  }],
  data_quality: { completeness_pct: 90, missing_fields: ['mock_interview_score'] },
  institution: { id: 'institution-1', name: 'Academia College' },
}

function setup(path = '/') {
  render(<MemoryRouter initialEntries={[path]}><StudentPortal /></MemoryRouter>)
}

beforeEach(() => {
  mocks.get.mockReset()
  mocks.get.mockResolvedValue({ data: PROFILE, meta: {} })
})

describe('student dashboard', () => {
  it('shows record-backed profile, score, indicators, recommendations and safe support plan', async () => {
    setup()
    expect(await screen.findByRole('heading', { name: 'Welcome, Asha Rao' })).toBeInTheDocument()
    expect(screen.getAllByText('Student success score').length).toBeGreaterThan(0)
    expect(screen.getByText('Historical score trends are not shown because historical snapshots are not available.')).toBeInTheDocument()
    expect(screen.getByText('Attendance improvement support')).toBeInTheDocument()
    expect(screen.getAllByText('My support plan').length).toBeGreaterThan(0)
    expect(screen.getByText('Mentoring')).toBeInTheDocument()
    expect(screen.queryByText('PRIVATE STAFF NOTE')).not.toBeInTheDocument()
    expect(screen.getByText(/missing data is shown as unavailable/i)).toBeInTheDocument()
  })

  it('shows a read-only support plan page with only the student’s intervention', async () => {
    setup('/my/support')
    expect(await screen.findByRole('heading', { name: 'My support plan', level: 1 })).toBeInTheDocument()
    const table = screen.getByRole('table')
    expect(within(table).getByText('Mentoring')).toBeInTheDocument()
    expect(within(table).getByText('Assigned')).toBeInTheDocument()
    expect(screen.queryByText('PRIVATE STAFF NOTE')).not.toBeInTheDocument()
  })
})
