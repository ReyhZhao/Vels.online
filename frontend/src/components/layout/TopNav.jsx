import { Link, NavLink } from 'react-router-dom';
import { Menu } from 'lucide-react';
import StatusIndicator from './StatusIndicator';
import { useAuth } from '../../context/AuthContext';
import NotificationBell from '../NotificationBell';
import api from '../../lib/axios';

function TopNav({ onMenuClick }) {
  const { user, isAuthenticated } = useAuth();

  async function handleLogout() {
    await api.post('/api/logout/');
    window.location.href = '/';
  }

  return (
    <header className="sticky top-0 z-50 w-full border-b border-border bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
      <div className="container mx-auto flex h-16 items-center justify-between px-4">
        <div className="flex items-center gap-2">
          {onMenuClick && (
            <button
              onClick={onMenuClick}
              aria-label="Toggle menu"
              className="md:hidden -ml-1.5 rounded-md p-1.5 text-muted-foreground hover:bg-accent hover:text-accent-foreground transition-colors"
            >
              <Menu className="h-5 w-5" aria-hidden="true" />
            </button>
          )}
          <Link
            to="/"
            className="text-lg font-semibold tracking-tight text-foreground hover:text-primary transition-colors"
          >
            Polaris Security
          </Link>
        </div>
        <nav className="flex items-center gap-6">
          <NavLink
            to="/blog"
            className={({ isActive }) =>
              `hidden md:inline-flex text-sm font-medium transition-colors hover:text-foreground ${
                isActive ? 'text-foreground' : 'text-muted-foreground'
              }`
            }
          >
            Blog
          </NavLink>
          <span className="hidden md:flex"><StatusIndicator /></span>
          {isAuthenticated ? (
            <>
              <NavLink
                to="/dashboard"
                className={({ isActive }) =>
                  `text-sm font-medium transition-colors hover:text-foreground ${
                    isActive ? 'text-foreground' : 'text-muted-foreground'
                  }`
                }
              >
                Dashboard
              </NavLink>
              <NotificationBell />
              <div className="flex items-center gap-3">
                <span className="hidden md:inline text-sm text-muted-foreground" data-testid="nav-username">
                  {user.username}
                </span>
                <button
                  onClick={handleLogout}
                  className="rounded-md border border-border bg-background px-3 py-1.5 text-sm font-medium text-foreground shadow-sm hover:bg-accent transition-colors"
                >
                  Logout
                </button>
              </div>
            </>
          ) : (
            <div className="flex items-center gap-2">
              <Link
                to="/signup"
                className="rounded-md px-3 py-1.5 text-sm font-medium text-muted-foreground hover:text-foreground transition-colors"
              >
                Sign up
              </Link>
              <a
                href={import.meta.env.VITE_LOGIN_URL ?? '/auth/oidc/authentik/login/'}
                className="rounded-md border border-border bg-background px-3 py-1.5 text-sm font-medium text-foreground shadow-sm hover:bg-accent transition-colors"
              >
                Login
              </a>
            </div>
          )}
        </nav>
      </div>
    </header>
  );
}

export default TopNav;
