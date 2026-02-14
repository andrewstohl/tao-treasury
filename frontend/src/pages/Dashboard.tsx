import { Navigate } from 'react-router-dom'

// Dashboard is deprecated - redirects to Command Center
// The old Dashboard relied on a Python backend that no longer exists.
// All operations data now comes from Supabase via the Command Center.
export default function Dashboard() {
  return <Navigate to="/command-center" replace />
}
