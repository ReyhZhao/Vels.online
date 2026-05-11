import { Navigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

function StaffOnlyRoute({ children }) {
  const { user, isAuthenticated, isLoading } = useAuth();

  if (isLoading) return null;

  if (!isAuthenticated) {
    window.location.href = '/auth/oidc/authentik/login/';
    return null;
  }

  if (!user?.is_staff) {
    return <Navigate to="/incidents" replace />;
  }

  return children;
}

export default StaffOnlyRoute;
