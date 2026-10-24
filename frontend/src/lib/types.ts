export type RiskLevel = 'Low' | 'Medium' | 'High' | 'Not applicable' | 'Insufficient data'
export type Role = 'super_admin' | 'college_admin' | 'student'
export type LoginType = 'admin' | 'campus' | 'student'

export interface AuthUser { username: string; role: Role; institution_id?: string; student_id?: string; active?: boolean; must_change_password?: boolean }
export interface Meta { total?: number; count?: number; limit?: number; offset?: number; has_more?: boolean; status_counts?: Record<string, number> }
export interface Envelope<T> { status: 'success'; data: T; meta: Meta }

export interface StudentListItem {
  student_id: string; student_name: string; department: string; year_of_study: number | null; section: string | null
  cgpa: number | null; overall_attendance_pct: number | null; placement_status: string | null
  success_score: number | null; academic_risk_level: RiskLevel; placement_risk_level: RiskLevel; segment: string | null
}

export interface RiskView {
  level: RiskLevel; points: number; max_points: number; reasons: string[]; suggested_actions: string[]
  missing_inputs: string[]; note: string | null; is_probability: boolean
}
export interface RiskItem {
  student_id: string; student_name: string; department: string; year_of_study: number | null; section: string | null
  success_score: number | null; segment: string | null; academic_risk: RiskView; placement_risk: RiskView
}

export interface DashboardSummary {
  total_students: number; average_success_score: number | null; average_attendance_pct: number | null
  students_flagged_academic_support: number; students_flagged_placement_support: number
  students_high_priority_support: number; students_strong_placement_readiness: number
  high_risk_academic: number; high_risk_placement: number; students_with_incomplete_data: number
  segments: Record<string, number>; placement_status_counts: Record<string, number>
  open_interventions: number; total_interventions: number; disclaimer?: string
}
export interface DepartmentMetric {
  department: string; students: number; average_success_score: number | null; average_cgpa: number | null
  average_attendance_pct: number | null; average_lms_score: number | null; average_placement_readiness: number | null
  flagged_academic_support: number; flagged_placement_support: number; priority_support: number
  strong_placement_readiness: number; placed_students: number; segments: Record<string, number>
}
export interface SegmentSummary {
  segment: string; description: string; students: number; percentage: number; average_success_score: number | null
  average_attendance_pct: number | null; average_placement_readiness: number | null; by_department: Record<string, number>
}

type Fields = Record<string, string | number | null>
export interface Recommendation {
  id: string; category: string; priority: string; title: string; description: string; suggested_steps: string[]
  related_intervention_type: string | null
  existing_open_intervention: { intervention_id: string; status: string } | null
  based_on: { indicator: string; label: string; value: string | number }[]
}
export interface Intervention {
  intervention_id: string; student_id: string; student_name?: string; intervention_type: string
  assigned_date: string; status: string; follow_up_notes: string
}
export interface Profile {
  student_id: string
  personal: Fields; academics: Fields; attendance: Fields; lms: Fields; engagement: Fields
  feedback: Fields; skills: Fields; placement: Fields
  success_score: { score: number | null; coverage: number; components: Record<string, { score: number | null; weight: number }>; note: string }
  segment: { name: string; description: string | null }
  risk: { academic: RiskView; placement: RiskView; disclaimer: string }
  recommendations: Recommendation[]
  interventions: Intervention[]
  data_quality: { completeness_pct: number; missing_fields: string[] }
}

export interface Metadata {
  departments: string[]; years_of_study: number[]; admission_years: number[]; sections: string[]
  placement_statuses: string[]; risk_levels: string[]; segments: string[]
  intervention_types: string[]; intervention_statuses: string[]
  score_weights: Record<string, number>; segment_rules: Record<string, number>
  datasets: Record<string, { file: string; rows: number; columns: string[]; role?: string }>
  data_notes: string[]; warnings: string[]
}

export interface PredictionFactor {
  factor: string; label: string; value: number | string | null; direction?: string; contribution?: number
}

export interface PredictionRecord {
  student_id: string
  prediction_type: string
  prediction_timestamp: string
  forecast_horizon: string
  prediction_horizon: string
  observed_value: Record<string, number | string | null>
  current_assessment: {
    status: string
    label: string
    summary: string
    observed_values: Record<string, number | string | null>
    score: number | null
    score_label: string | null
    risk_level: string | null
    risk_is_probability: false
    triggered_indicators: Array<{ label: string; value: number | string; threshold: number | string; reason: string }>
    suggested_actions: string[]
    assessment_disclaimer: string
    benchmarks?: {
      indicators: Array<{
        label: string; direction: string
        thresholds: Array<{ threshold: number | string | null; points: number | null }>
      }>
      risk_point_cutoffs: { medium_at: number; high_at: number }
      readiness_score_weights: Record<string, number>
      configured_in: string
    } | null
  }
  predicted_outcome: string | null
  probability: number | null
  predicted_probability: number | null
  predicted_value: number | null
  risk_category: string
  risk_level: string | null
  top_contributing_factors: PredictionFactor[]
  model_version: string
  model_status: string
  model_evaluation_status: string
  data_sufficiency_status: string
  evaluation_summary: string
  explanation: string
  limitations: string[]
  caveats: string[]
  recommended_action: string
  prediction_validation_status?: string
  recorded_placement_status?: string | null
}

export interface PredictionBundle {
  student_id: string
  predictions: Record<string, PredictionRecord>
  model_version: string
  model_evaluation_status: string
  data_sufficiency_status: string
}

export interface PredictionEvaluation {
  model_version: string
  model_evaluation_status: string
  data_sufficiency_status: string
  summary: string
  available_models: string[]
  model_statuses: Record<string, {
    status: string; label: string; horizon: string; reason: string; required_data: string
  }>
  baseline: Record<string, string | Record<string, unknown> | null> | null
  students_checked: number | null
  limitations: string[]
  metrics?: {
    accuracy: number; precision: number; recall: number; f1: number; roc_auc: number
    confusion_matrix: { labels: string[]; rows_actual_columns_predicted: number[][] }
  } | null
  class_counts?: { not_placed: number; placed: number; total: number } | null
  evaluation?: { method: string; random_state: number; positive_examples_per_fold_approx: number }
  caveats?: string[]
}

export interface Health { service: string; student_count: number; intervention_count: number; warning_count: number; warnings: string[]; loaded_at?: string }
