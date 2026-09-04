import { Navigate, Outlet } from 'react-router-dom'

import { adminSessionValid } from '../../api/adminClient'

/**
 * Guards the operator area.
 *
 * Deliberately checks the ADMIN token, not `access_token`. A customer session
 * must not open this tree, and an operator session must not be mistaken for a
 * customer one — the backend refuses both directions, and the router should
 * not pretend otherwise on the way in.
 */
export default function AdminRoute() {
  if (!adminSessionValid()) return <Navigate to="/admin/login" replace />
  return <Outlet />
}
