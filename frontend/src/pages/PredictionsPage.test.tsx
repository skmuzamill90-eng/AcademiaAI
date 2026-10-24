import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import PredictionsPage from './PredictionsPage'
import type { PredictionBundle, PredictionEvaluation, StudentListItem } from '../lib/types'

const mocks = vi.hoisted(() => ({
  get: vi.fn(),
  getAll: vi.fn(),
}))

vi.mock('../lib/api', () => mocks)

const student: StudentListItem = {
  student_id: 'STU00000001',
  student_name: 'Asha Rao',
  department: 'CSE',
  year_of_study: 2,
  section: 'A',
  cgpa: 8,
  overall_attendance_pct: 52.5,
  placement_status: 'Eligible',
  success_score: 62,
  academic_risk_level: 'High',
  placement_risk_level: 'Low',
  segment: 'Needs support',
}

const evaluation: PredictionEvaluation = {
  model_version: 'prediction-contract-v2',
  model_evaluation_status: 'insufficient_data',
  data_sufficiency_status: 'no_temporal_future_outcomes',
  summary: 'No validated future-outcome models are available.',
  available_models: [],
  model_statuses: {
    placement_readiness: {
      status: 'insufficient_data',
      label: 'Future placement readiness',
      horizon: 'placement season',
      reason: 'No future readiness outcome is recorded.',
      required_data: 'Dated pre-deadline data and actual outcomes.',
    },
  },
  baseline: null,
  students_checked: 1,
  limitations: ['The placement score is current, not a future outcome.'],
}

const predictions: PredictionBundle = {
  student_id: student.student_id,
  model_version: 'prediction-contract-v2',
  model_evaluation_status: 'insufficient_data',
  data_sufficiency_status: 'no_temporal_future_outcomes',
  predictions: {
    semester_performance: {
      student_id: student.student_id,
      prediction_type: 'semester_performance',
      prediction_timestamp: '2026-10-24T00:00:00Z',
      forecast_horizon: 'next semester',
      prediction_horizon: 'next semester',
      observed_value: { success_score: 62 },
      current_assessment: {
        status: 'current_assessment_only',
        label: 'Semester performance — current records',
        summary: 'Academic standing from current records.',
        observed_values: { success_score: 62 },
        score: 62,
        score_label: 'Round 1 Student Success Score (current snapshot)',
        risk_level: 'Low',
        risk_is_probability: false,
        triggered_indicators: [],
        suggested_actions: ['Routine monitoring.'],
        assessment_disclaimer: 'Current support indicator.',
      },
      predicted_outcome: null,
      probability: null,
      predicted_probability: null,
      predicted_value: null,
      risk_category: 'Forecast unavailable',
      risk_level: null,
      top_contributing_factors: [{ factor: 'success_score', label: 'Round 1 Student Success Score', value: 62 }],
      model_status: 'insufficient_data',
      model_version: 'prediction-contract-v2',
      model_evaluation_status: 'insufficient_data',
      data_sufficiency_status: 'no_temporal_future_outcomes',
      evaluation_summary: 'Not evaluated.',
      explanation: 'No forecast.',
      limitations: [],
      caveats: [],
      recommended_action: 'Routine monitoring.',
    },
    placement_readiness: {
      student_id: student.student_id,
      prediction_type: 'placement_readiness',
      prediction_timestamp: '2026-10-24T00:00:00Z',
      forecast_horizon: 'placement season',
      prediction_horizon: 'before the placement-season deadline',
      observed_value: { placement_status: 'Eligible', aptitude_score: 70 },
      current_assessment: {
        status: 'current_assessment_only',
        label: 'Placement readiness — current records',
        summary: 'Current placement status: Eligible.',
        observed_values: { placement_status: 'Eligible', aptitude_score: 70 },
        score: 61.5,
        score_label: 'Placement-readiness assessment (current snapshot)',
        risk_level: 'Low',
        risk_is_probability: false,
        triggered_indicators: [],
        suggested_actions: ['Routine monitoring.'],
        assessment_disclaimer: 'Rule-based indicator, not a probability or a prediction.',
        benchmarks: {
          indicators: [{
            label: 'Aptitude',
            direction: 'below',
            thresholds: [{ threshold: 40, points: 2 }, { threshold: 55, points: 1 }],
          }],
          risk_point_cutoffs: { medium_at: 4, high_at: 7 },
          readiness_score_weights: { aptitude: 0.2, coding: 0.2 },
          configured_in: 'app/config.py',
        },
      },
      predicted_outcome: null,
      probability: null,
      predicted_probability: null,
      predicted_value: null,
      risk_category: 'Forecast unavailable',
      risk_level: null,
      top_contributing_factors: [{ factor: 'aptitude_score', label: 'Aptitude score', value: 70 }],
      model_status: 'insufficient_data',
      model_version: 'prediction-contract-v2',
      model_evaluation_status: 'insufficient_data',
      data_sufficiency_status: 'no_temporal_future_outcomes',
      evaluation_summary: 'Not evaluated: future labels are unavailable.',
      explanation: 'No future estimate is produced.',
      limitations: ['Future placement-readiness outcome is not present.'],
      caveats: ['Future placement-readiness outcome is not present.'],
      recommended_action: 'Confirm the current record.',
    },
  },
}

beforeEach(() => {
  mocks.get.mockReset()
  mocks.getAll.mockReset()
  mocks.get.mockImplementation((path: string) => Promise.resolve({
    data: path === '/api/predictions/evaluation' ? evaluation : predictions,
    meta: {},
  }))
  mocks.getAll.mockResolvedValue([student])
})

describe('predictions page', () => {
  it('keeps current indicators and removes repetitive prediction-status text', async () => {
    render(<PredictionsPage />)

    expect(await screen.findByText('Current placement status: Eligible.')).toBeInTheDocument()
    expect(screen.getAllByText('Current data')).toHaveLength(2)
    expect(screen.queryByText('Future predictions are unavailable')).not.toBeInTheDocument()
    expect(screen.getByText('Aptitude score')).toBeInTheDocument()
    expect(screen.getByText('Readiness assessment criteria')).toBeInTheDocument()
    expect(screen.queryByText(/Future placement readiness: insufficient data/)).not.toBeInTheDocument()
    expect(screen.queryByText(/Current placement status is an observed label/)).not.toBeInTheDocument()
    expect(screen.queryByText(/before the placement-season deadline/)).not.toBeInTheDocument()
    expect(screen.queryByText(/Rule-based indicator, not a probability/)).not.toBeInTheDocument()
    expect(screen.queryByText('Round 1 Student Success Score (current snapshot)')).not.toBeInTheDocument()
    expect(screen.queryByText('Round 1 Student Success Score')).not.toBeInTheDocument()
    expect(screen.queryByText(/Estimated recorded/)).not.toBeInTheDocument()
    expect(screen.queryByText('61.5%')).not.toBeInTheDocument()
  })
})
