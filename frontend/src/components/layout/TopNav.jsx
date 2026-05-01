import { Link, NavLink } from 'react-router-dom';
import StatusIndicator from './StatusIndicator';

function TopNav() {
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
        </nav>
      </div>
    </header>
  );
}

export default TopNav;
