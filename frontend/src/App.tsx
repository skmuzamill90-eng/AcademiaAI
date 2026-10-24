import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { AuthProvider, STAFF, useAuth } from './lib/auth'
import type { Role } from './lib/types'
import AppShell from './components/AppShell'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import Students from './pages/Students'
import Academics from './pages/Academics'
import RiskPage from './pages/RiskPage'
import Interventions from './pages/Interventions'
import Reports from './pages/Reports'
import DataPage from './pages/DataPage'
import Settings from './pages/Settings'
import ImportStudents from './pages/ImportStudents'
import AiAssistant from './pages/AiAssistant'
import PredictionsPage from './pages/PredictionsPage'
import { useState, type ReactNode } from 'react'
import { ToastProvider } from './components/Toast'
import Platform from './pages/Platform'
import StudentPortal from './pages/StudentPortal'
import { AccountSettings, InstitutionSettings, Loading } from './pages/Accounts'

function Guard({ roles, children }: { roles: Role[]; children: ReactNode }) {
  const { can } = useAuth()
  return can(...roles) ? <>{children}</> : <Navigate to="/" replace />
}

function Routed() {
  const { user, checking } = useAuth()
  const [setupToken] = useState(() => {
    const value = new URLSearchParams(window.location.hash.slice(1)).get('setup')
    if (value) window.history.replaceState(null, '', window.location.pathname)
    return value
  })
  if (setupToken) return <AccountSettings setupToken={setupToken} />
  if (checking) return <Loading />
  if (!user) return <Login />
  if (user.must_change_password) return <AccountSettings />
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<AppShell />}>
          <Route index element={user.role === 'super_admin' ? <Platform /> : user.role === 'student' ? <StudentPortal /> : <Dashboard />} />
          <Route path="institutions" element={<Guard roles={['super_admin']}><Platform /></Guard>} />
          <Route path="audit" element={<Guard roles={['super_admin']}><Platform /></Guard>} />
          <Route path="my/:section" element={<Guard roles={['student']}><StudentPortal /></Guard>} />
          <Route path="institution" element={<Guard roles={STAFF}><InstitutionSettings /></Guard>} />
          <Route path="account" element={<AccountSettings />} />
          <Route path="students" element={<Guard roles={STAFF}><Students /></Guard>} />
          <Route path="academics" element={<Guard roles={STAFF}><Academics /></Guard>} />
          <Route path="academic-risk" element={<Guard roles={STAFF}><RiskPage kind="academic" /></Guard>} />
          <Route path="placement-risk" element={<Guard roles={STAFF}><RiskPage kind="placement" /></Guard>} />
          <Route path="segments" element={<Navigate to="/" replace />} />
          <Route path="interventions" element={<Guard roles={STAFF}><Interventions /></Guard>} />
          <Route path="reports" element={<Guard roles={STAFF}><Reports /></Guard>} />
          <Route path="assistant" element={<Guard roles={STAFF}><AiAssistant /></Guard>} />
          <Route path="predictions" element={<Guard roles={STAFF}><PredictionsPage /></Guard>} />
          <Route path="data" element={<Guard roles={STAFF}><DataPage /></Guard>} />
          <Route path="import" element={<Guard roles={STAFF}><ImportStudents /></Guard>} />
          <Route path="settings" element={<Guard roles={STAFF}><Settings /></Guard>} />
          <Route path="discovery" element={<Navigate to="/students" replace />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}

export default function App() {
  return <ToastProvider><AuthProvider><Routed /></AuthProvider></ToastProvider>
}
