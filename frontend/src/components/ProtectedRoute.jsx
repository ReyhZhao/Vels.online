import { useAuth } from '../context/AuthContext';

function ProtectedRoute({ children }) {
  const { isAuthenticated, isLoading } = useAuth();

  if (isLoading) return null;

  if (!isAuthenticated) {
    window.location.href = '/auth/oidc/authentik/login/';
    return null;
  }

  return children;
}

export default ProtectedRoute;
