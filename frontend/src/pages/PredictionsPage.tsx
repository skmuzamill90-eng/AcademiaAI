import { useEffect, useMemo, useState } from 'react'
import { get, getAll } from '../lib/api'
import { useLoad } from '../lib/hooks'
import type { PredictionBundle, StudentListItem } from '../lib/types'
import { Async, PageHeading } from '../components/Primitives'

const predictionLabels: Record<string, string> = {
  semester_performance: 'Academic performance',
  backlog_risk: 'Backlogs',
  placement_readiness: 'Placement readiness',
  engagement_drop: 'Engagement',
}

export default function PredictionsPage() {
  const students = useLoad<StudentListItem[]>(
    async () => ({ data: await getAll<StudentListItem>('/api/students') }),
    'predictions-students',
  )
  const [selectedStudentId, setSelectedStudentId] = useState<string | null>(null)

  useEffect(() => {
    if (!selectedStudentId && students.data?.length) setSelectedStudentId(students.data[0].student_id)
  }, [students.data, selectedStudentId])

  const selectedPrediction = useLoad<PredictionBundle>(
    () => selectedStudentId
      ? get<PredictionBundle>(`/api/students/${selectedStudentId}/predictions`)
      : Promise.resolve({ data: { student_id: '', predictions: {} } as PredictionBundle, meta: {} }),
    `prediction:${selectedStudentId ?? 'none'}`,
  )

  const predictions = useMemo(
    () => Object.values(selectedPrediction.data?.predictions ?? {}),
    [selectedPrediction.data],
  )
  const selectedStudent = students.data?.find(student => student.student_id === selectedStudentId)

  return (
    <>
      <PageHeading
        title="Student predictions"
        description="View a student's current academic, attendance, engagement, and placement indicators."
        actions={
          <label className="prediction-student-select">
            <span>Student</span>
            <select
              className="select"
              aria-label="Select student"
              value={selectedStudentId ?? ''}
              onChange={event => setSelectedStudentId(event.target.value)}
              disabled={!students.data?.length}
            >
              {(students.data ?? []).map(student => (
                <option key={student.student_id} value={student.student_id}>
                  {student.student_name} · {student.student_id}
                </option>
              ))}
            </select>
          </label>
        }
      />

      {selectedStudent && (
        <section className="prediction-student-summary" aria-label="Selected student">
          <div className="prediction-student-identity">
            <strong>{selectedStudent.student_name}</strong>
            <span>{selectedStudent.department}</span>
          </div>
          <div className="prediction-student-meta">
            <span><small>Student ID</small>{selectedStudent.student_id}</span>
            {selectedStudent.year_of_study != null && (
              <span><small>Year</small>{selectedStudent.year_of_study}</span>
            )}
            {selectedStudent.section && <span><small>Section</small>{selectedStudent.section}</span>}
          </div>
        </section>
      )}

      <Async
        loading={selectedPrediction.loading && !selectedPrediction.data}
        error={selectedPrediction.error}
        onRetry={selectedPrediction.reload}
      >
        {predictions.length ? (
          <div className="prediction-list">
            {predictions.map(prediction => {
              const label = predictionLabels[prediction.prediction_type] ?? prediction.prediction_type
              const factors = (prediction.top_contributing_factors ?? []).filter(
                factor => !(prediction.prediction_type === 'semester_performance' && factor.factor === 'success_score'),
              )
              const assessment = prediction.current_assessment
              const benchmarks = assessment.benchmarks
              const showScore = prediction.prediction_type !== 'semester_performance'
                && assessment.score !== null && assessment.score_label
              return (
                <article className="prediction-card" key={prediction.prediction_type}>
                  <div className="prediction-card-heading">
                    <div>
                      <h2>{label}</h2>
                    </div>
                    <span className="pill risk-neutral"><i />Current data</span>
                  </div>

                  <p className="prediction-outcome">{assessment.summary}</p>
                  {showScore && (
                    <div className="prediction-current-score">
                      <span>{assessment.score_label}</span><strong>{assessment.score}</strong>
                    </div>
                  )}

                  <div className="prediction-detail">
                    <div>
                      <span className="prediction-label">Current recorded values</span>
                      {factors.length ? (
                        <ul className="prediction-factors">
                          {factors.map(factor => (
                            <li key={factor.factor}>
                              <span className="prediction-factor-label">{factor.label}</span>
                              <strong>{factor.value ?? 'Unavailable'}</strong>
                            </li>
                          ))}
                        </ul>
                      ) : <p className="prediction-muted">No current values are available.</p>}
                    </div>
                    <div className="prediction-support-column">
                      <section className="prediction-assessment">
                        <div className="prediction-assessment-heading">
                          <span className="prediction-label">Current support assessment</span>
                          <strong className={`prediction-assessment-level ${assessment.risk_level?.toLowerCase().replace(/\s+/g, '-') ?? 'not-assessed'}`}>
                            {assessment.risk_level ?? 'Not assessed'}
                          </strong>
                        </div>
                        {assessment.triggered_indicators.length > 0 && (
                          <ul className="prediction-assessment-evidence">
                            {assessment.triggered_indicators.map((indicator, index) => (
                              <li key={`${indicator.label}-${index}`}>{indicator.reason}</li>
                            ))}
                          </ul>
                        )}
                        {benchmarks && (
                          <details className="prediction-assessment-benchmarks">
                            <summary>Readiness assessment criteria</summary>
                            <ul>
                              {benchmarks.indicators.map(indicator => (
                                <li key={indicator.label}>
                                  <strong>{indicator.label}</strong>
                                  <span>{indicator.thresholds.map(rule => (
                                    `${indicator.direction === 'below' ? 'below' : indicator.direction === 'at_least' ? 'at least' : 'equals'} ${rule.threshold} (${rule.points ?? 0} point${rule.points === 1 ? '' : 's'})`
                                  )).join('; ')}</span>
                                </li>
                              ))}
                            </ul>
                            <p>Medium at {benchmarks.risk_point_cutoffs.medium_at}+ points; High at {benchmarks.risk_point_cutoffs.high_at}+ points.</p>
                            <p>Readiness weights: {Object.entries(benchmarks.readiness_score_weights)
                              .map(([name, weight]) => `${name.replace(/_/g, ' ')} ${Math.round(weight * 100)}%`).join(', ')}.</p>
                          </details>
                        )}
                      </section>
                      <section className="prediction-action">
                        <span className="prediction-label">Suggested next step</span>
                        <p>{prediction.recommended_action}</p>
                      </section>
                    </div>
                  </div>

                </article>
              )
            })}
          </div>
        ) : (
          <div className="prediction-empty">
            <p>No prediction indicators are available for this student.</p>
            <span>Check the student’s records or choose another student.</span>
          </div>
        )}
      </Async>
    </>
  )
}
