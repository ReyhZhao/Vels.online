import { Link, NavLink } from 'react-router-dom';
import StatusIndicator from './StatusIndicator';
import { useAuth } from '../../context/AuthContext';
import api from '../../lib/axios';

function TopNav() {
  const { user, isAuthenticated } = useAuth();

  async function handleLogout() {
    await api.post('/api/logout/');
    window.location.href = '/';
  }

  return (
    <header className="sticky top-0 z-50 w-full border-b border-border bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
      <div className="container mx-auto flex h-16 items-center justify-between px-4">
        <Link
          to="/"
          className="text-lg font-semibold tracking-tight text-foreground hover:text-primary transition-colors"
        >
          vels.online
        </Link>
        <nav className="flex items-center gap-6">
          <NavLink
            to="/blog"
            className={({ isActive }) =>
              `text-sm font-medium transition-colors hover:text-foreground ${
                isActive ? 'text-foreground' : 'text-muted-foreground'
              }`
            }
          >
            Blog
          </NavLink>
          <StatusIndicator />
          {isAuthenticated ? (
            <div className="flex items-center gap-3">
              <span className="text-sm text-muted-foreground" data-testid="nav-username">
                {user.username}
              </span>
              <button
                onClick={handleLogout}
                className="rounded-md border border-border bg-background px-3 py-1.5 text-sm font-medium text-foreground shadow-sm hover:bg-accent transition-colors"
              >
                Logout
              </button>
            </div>
          ) : (
            <a
              href="/auth/oidc/authentik/login/"
              className="rounded-md border border-border bg-background px-3 py-1.5 text-sm font-medium text-foreground shadow-sm hover:bg-accent transition-colors"
            >
              Login
            </a>
          )}
        </nav>
      </div>
    </header>
  );
}

export default TopNav;
