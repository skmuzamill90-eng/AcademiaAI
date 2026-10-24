import { useLocation } from 'react-router-dom'
import {
  Activity, BookOpenCheck, BriefcaseBusiness, CalendarDays, GraduationCap, Lightbulb,
  ListChecks, Sparkles, Users,
} from 'lucide-react'
import { get } from '../lib/api'
import { useLoad } from '../lib/hooks'
import { Async, EmptyState, MetricCard, Notice, PageHeading, Panel, RiskPill, ScoreCell, scoreTone } from '../components/Primitives'
import type { Intervention, Profile, Recommendation } from '../lib/types'

type StudentIntervention = Pick<Intervention, 'intervention_id' | 'intervention_type' | 'assigned_date' | 'status'>
type PersonalProfile = Omit<Profile, 'interventions'> & {
  interventions: StudentIntervention[]
  institution: { id: string; name: string }
}

const sectionTitles: Record<string, string> = {
  profile: 'My profile',
  academics: 'My academics',
  attendance: 'My attendance',
  learning: 'Learning activity',
  placement: 'My skills and placement',
  recommendations: 'My recommendations',
  support: 'My support plan',
}

const format = (value: unknown, suffix = '') =>
  value === null || value === undefined || value === '' ? 'Unavailable' : `${String(value)}${suffix}`

function Details({ fields }: { fields: [string, unknown][] }) {
  return <dl className="saas-fields">
    {fields.map(([label, value]) => (
      <div key={label}><dt>{label}</dt><dd>{format(value)}</dd></div>
    ))}
  </dl>
}

function RecommendationList({ items }: { items: Recommendation[] }) {
  if (!items.length) return <EmptyState icon={<Lightbulb size={22} />} title="No recommendations right now" body="There are no recorded indicators that currently trigger a recommendation." />
  return <div>
    {items.map(item => (
      <article className="saas-recommendation" key={item.id}>
        <div className="metric-top">
          <strong>{item.title}</strong>
          <span className={`pill ${item.priority === 'High' ? 'risk-high' : item.priority === 'Medium' ? 'risk-moderate' : 'risk-neutral'}`}><i />{item.priority} priority</span>
        </div>
        <p>{item.description}</p>
        {item.based_on.length > 0 && <p className="stage-hint">Based on {item.based_on.map(f => `${f.label}: ${f.value}`).join(' · ')}</p>}
        <ul>{item.suggested_steps.map(step => <li key={step}>{step}</li>)}</ul>
        {item.existing_open_intervention && <p className="stage-hint">A related support intervention is already open.</p>}
      </article>
    ))}
  </div>
}

function RiskDetails({ profile }: { profile: PersonalProfile }) {
  return <Panel title="Current support indicators" subtitle="These are rule-based support indicators, not predictions or probabilities.">
    <div className="saas-grid">
      {([
        ['Academic indicators', profile.risk.academic],
        ['Placement readiness indicators', profile.risk.placement],
      ] as const).map(([title, risk]) => (
        <section key={title}>
          <div className="metric-top"><strong>{title}</strong><RiskPill risk={risk.level} /></div>
          <p className="stage-hint">{risk.note ?? 'Based on the indicators currently available in your record.'}</p>
          {risk.reasons.length > 0
            ? <ul>{risk.reasons.map(reason => <li key={reason}>{reason}</li>)}</ul>
            : <p>No support indicators are currently recorded.</p>}
          {risk.missing_inputs.length > 0 && <p className="stage-hint">Unavailable inputs: {risk.missing_inputs.join(', ')}</p>}
        </section>
      ))}
    </div>
    <p className="stage-hint">{profile.risk.disclaimer}</p>
  </Panel>
}

function SupportPlan({ interventions }: { interventions: StudentIntervention[] }) {
  return <Panel title="My support plan" subtitle="Read-only status of interventions assigned to your student record.">
    {interventions.length === 0
      ? <EmptyState icon={<ListChecks size={22} />} title="No support plan is recorded" body="If you expected an assigned intervention, contact your institution administrator." />
      : <div className="saas-table"><table>
        <thead><tr><th>Support</th><th>Assigned date</th><th>Status</th></tr></thead>
        <tbody>{interventions.map(item => (
          <tr key={item.intervention_id}>
            <td>{item.intervention_type}</td><td>{item.assigned_date || 'Unavailable'}</td>
            <td><span className={`saas-status status-${item.status.toLowerCase().replaceAll(' ', '-')}`}>{item.status}</span></td>
          </tr>
        ))}</tbody>
      </table></div>}
    <Notice>Current intervention records do not include student-facing instructions, deadlines, mentor assignments, or priority. Staff-only follow-up notes are not shown here.</Notice>
  </Panel>
}

export default function StudentPortal() {
  const path = useLocation().pathname.split('/')[2] ?? ''
  const result = useLoad<PersonalProfile>(() => get('/api/student/me'), 'own-profile')
  const profile = result.data
  const attendanceRecommendation = profile?.recommendations.find(recommendation => recommendation.category === 'Attendance')

  return <Async loading={result.loading} error={result.error} onRetry={result.reload}>
    {profile && <>
      <PageHeading
        title={path ? sectionTitles[path] ?? 'My dashboard' : `Welcome, ${String(profile.personal.student_name ?? profile.student_id)}`}
        description={`${profile.institution.name} · Student ID: ${profile.student_id}`}
      />

      {!path && <div className="metric-grid">
        <MetricCard label="Student success score" value={profile.success_score.score ?? '—'} sub={`${scoreTone(profile.success_score.score).label} · out of 100`} icon={<Sparkles size={18} />} />
        <MetricCard label="CGPA" value={format(profile.academics.cgpa)} sub="From your current student record" icon={<GraduationCap size={18} />} />
        <MetricCard label="Overall attendance" value={format(profile.attendance.overall_attendance_pct, profile.attendance.overall_attendance_pct == null ? '' : '%')} sub="Recorded attendance" icon={<CalendarDays size={18} />} />
        <MetricCard label="Backlogs" value={format(profile.academics.backlogs)} sub="Existing recorded count" icon={<BookOpenCheck size={18} />} />
      </div>}

      {(!path || path === 'academics') && <div className="dashboard-grid">
        <Panel title="Student success score" subtitle="The existing Round 1 score, calculated from available academic, attendance, learning and placement-readiness data. It is not a predictive risk score.">
          <div className="metric-top">
            <ScoreCell score={profile.success_score.score} complete={profile.data_quality.completeness_pct === 100} />
            <span style={{ color: scoreTone(profile.success_score.score).color }}>{scoreTone(profile.success_score.score).label}</span>
          </div>
          <p className="stage-hint">{profile.success_score.note}</p>
          <div className="saas-summary">
            {Object.entries(profile.success_score.components).map(([key, component]) => (
              <MetricCard key={key} label={key.replaceAll('_', ' ')} value={component.score ?? '—'} sub={`Existing score component · ${Math.round(component.weight * 100)}% weight`} icon={<Activity size={18} />} />
            ))}
          </div>
          <p className="stage-hint">Historical score trends are not shown because historical snapshots are not available.</p>
        </Panel>
        <Panel title="Academic performance" subtitle="Values come from your linked student record; missing values are shown as unavailable.">
          <Details fields={[
            ['CGPA', profile.academics.cgpa],
            ['Internal assessment', format(profile.academics.internal_score_pct, profile.academics.internal_score_pct == null ? '' : '%')],
            ['Semester performance', format(profile.academics.semester_score_pct, profile.academics.semester_score_pct == null ? '' : '%')],
            ['Backlogs recorded', profile.academics.backlogs],
            ['Academic risk', profile.risk.academic.level],
          ]} />
        </Panel>
      </div>}

      {(!path || path === 'profile') && <Panel title="My profile" subtitle="Your identity and enrollment information from the institution's student record.">
        <Details fields={[
          ['Name', profile.personal.student_name],
          ['Student ID', profile.student_id],
          ['Department', profile.personal.department],
          ['Year of study', profile.personal.year_of_study],
          ['Section', profile.personal.section],
          ['Admission year', profile.personal.admission_year],
          ['Institution', profile.institution.name],
        ]} />
        {path === 'profile' && <div className="saas-grid">
          <Panel title="Engagement"><Details fields={[
            ['Events attended', profile.engagement.events_attended],
            ['Hackathons participated', profile.engagement.hackathons_participated],
            ['Club participation', profile.engagement.club_participation],
            ['Volunteer hours', profile.engagement.volunteer_hours],
          ]} /></Panel>
          <Panel title="Student feedback"><Details fields={[
            ['Satisfaction (1–5)', profile.feedback.student_satisfaction_1_to_5],
            ['Support requested', profile.feedback.support_requested],
            ['Feedback topic', profile.feedback.feedback_topic],
          ]} /></Panel>
        </div>}
      </Panel>}

      {(!path || path === 'attendance') && <Panel title="Attendance" subtitle="Attendance measurements currently recorded for your profile.">
        <div className="metric-grid">
          <MetricCard label="Overall attendance" value={format(profile.attendance.overall_attendance_pct, profile.attendance.overall_attendance_pct == null ? '' : '%')} sub="Recorded percentage" icon={<CalendarDays size={18} />} />
          <MetricCard label="Subjects below threshold" value={format(profile.attendance.subjects_below_attendance_threshold)} sub="Recorded count" icon={<BookOpenCheck size={18} />} />
          <div><span>Academic support indicator</span> <RiskPill risk={profile.risk.academic.level} /></div>
        </div>
        {attendanceRecommendation
          ? <ul>{attendanceRecommendation.suggested_steps.map(action => <li key={action}>{action}</li>)}</ul>
          : <p>No attendance-related recommendation is triggered by the currently recorded indicators.</p>}
      </Panel>}

      {(!path || path === 'learning') && <Panel title="Learning engagement" subtitle="Activity metrics from the available learning and engagement records.">
        <div className="metric-grid">
          <MetricCard label="LMS logins (30 days)" value={format(profile.lms.logins_last_30_days)} sub="Recorded logins" icon={<Activity size={18} />} />
          <MetricCard label="Assignment completion" value={format(profile.lms.assignment_completion_pct, profile.lms.assignment_completion_pct == null ? '' : '%')} sub="Recorded completion" icon={<BookOpenCheck size={18} />} />
          <MetricCard label="Weekly learning hours" value={format(profile.lms.avg_weekly_learning_hours)} sub="Recorded average" icon={<CalendarDays size={18} />} />
          <MetricCard label="Events attended" value={format(profile.engagement.events_attended)} sub="Recorded participation" icon={<Users size={18} />} />
          <MetricCard label="Club participation" value={format(profile.engagement.club_participation)} sub="Recorded engagement" icon={<Users size={18} />} />
          <MetricCard label="Volunteer hours" value={format(profile.engagement.volunteer_hours)} sub="Recorded hours" icon={<Activity size={18} />} />
        </div>
      </Panel>}

      {(!path || path === 'placement') && <Panel title="Placement readiness" subtitle="Recorded preparation indicators only. These are not forecasts of future placement outcomes.">
        <div className="metric-grid">
          <MetricCard label="Aptitude score" value={format(profile.placement.aptitude_score)} sub="Recorded score" icon={<BriefcaseBusiness size={18} />} />
          <MetricCard label="Coding score" value={format(profile.placement.coding_score)} sub="Recorded score" icon={<Activity size={18} />} />
          <MetricCard label="Mock interview" value={format(profile.placement.mock_interview_score)} sub="Recorded score" icon={<Users size={18} />} />
          <MetricCard label="Resume readiness" value={format(profile.placement.resume_readiness_pct, profile.placement.resume_readiness_pct == null ? '' : '%')} sub="Recorded percentage" icon={<BriefcaseBusiness size={18} />} />
          <MetricCard label="Technical skill score" value={format(profile.skills.technical_skill_score)} sub="Recorded score" icon={<GraduationCap size={18} />} />
          <MetricCard label="Soft skill score" value={format(profile.skills.soft_skill_score)} sub="Recorded score" icon={<Users size={18} />} />
          <MetricCard label="Projects" value={format(profile.skills.projects_count)} sub="Recorded count" icon={<BookOpenCheck size={18} />} />
          <MetricCard label="Certifications" value={format(profile.skills.certifications_count)} sub="Recorded count" icon={<GraduationCap size={18} />} />
          <MetricCard label="Placement status" value={format(profile.placement.placement_status)} sub="Recorded status, not a prediction" icon={<BriefcaseBusiness size={18} />} />
        </div>
      </Panel>}

      {(!path || path === 'academics' || path === 'attendance' || path === 'placement') && <RiskDetails profile={profile} />}

      {(!path || path === 'recommendations') && <Panel title="My recommendations" subtitle="Suggestions generated by existing rules from indicators actually recorded in your profile.">
        <RecommendationList items={profile.recommendations} />
      </Panel>}

      {(!path || path === 'support') && <SupportPlan interventions={profile.interventions} />}

      {profile.data_quality.completeness_pct < 100 && <Notice>
        Your profile is {profile.data_quality.completeness_pct}% complete. Missing data is shown as unavailable, not treated as zero.
      </Notice>}
    </>}
  </Async>
}
