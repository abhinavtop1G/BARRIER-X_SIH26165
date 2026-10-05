import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { AuthProvider, useAuth } from '@/context/AuthContext'
import LandingPage from '@/pages/LandingPage'
import LoginPage from '@/pages/LoginPage'
import DashboardLayout from '@/layouts/DashboardLayout'
import Overview from '@/pages/dashboard/Overview'
import Reports from '@/pages/dashboard/Reports'
import SifAnalysis from '@/pages/dashboard/SifAnalysis'
import AgentChat from '@/pages/dashboard/AgentChat'
import ComingSoon from '@/pages/dashboard/ComingSoon'

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { isAuthenticated } = useAuth()
  return isAuthenticated ? <>{children}</> : <Navigate to="/login" replace />
}

function PublicRoute({ children }: { children: React.ReactNode }) {
  const { isAuthenticated } = useAuth()
  return isAuthenticated ? <Navigate to="/dashboard" replace /> : <>{children}</>
}

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<LandingPage />} />
          <Route path="/login" element={<PublicRoute><LoginPage /></PublicRoute>} />

          <Route path="/dashboard" element={<ProtectedRoute><DashboardLayout /></ProtectedRoute>}>
            <Route index element={<Overview />} />
            <Route path="reports" element={<Reports />} />
            <Route path="sif-analysis" element={<SifAnalysis />} />
            <Route path="precursors"  element={<ComingSoon title="Precursor Pattern Detection"  desc="Identify recurring activity–location–barrier-failure combinations that signal emerging systemic risk." />} />
            <Route path="life-saving" element={<ComingSoon title="Life-Saving Rule Mapping"     desc="Automatically map safety reports to IOGP Life-Saving Rules using multi-label classification." />} />
            <Route path="3d-view"     element={<ComingSoon title="3D Safety Digital Twin"       desc="Visualize spatial safety risk density across industrial assets in an interactive 3D facility model." />} />
            <Route path="agent"       element={<AgentChat />} />
            <Route path="settings"    element={<ComingSoon title="Settings"                     desc="API configuration, user management, and system preferences." />} />
          </Route>

          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  )
}
