import { NavLink, Outlet } from 'react-router-dom';
import { cn } from '@/lib/utils';
import { OrgProvider } from '../../context/OrgContext';
import OrgSwitcher from '../OrgSwitcher';
import Breadcrumb from './Breadcrumb';

function NavItem({ to, end, children }) {
  return (
    <NavLink
      to={to}
      end={end}
      className={({ isActive }) =>
        cn(
          'text-sm font-medium transition-colors',
          isActive ? 'text-foreground' : 'text-muted-foreground hover:text-foreground'
        )
      }
    >
      {children}
    </NavLink>
  );
}

function SecurityLayout() {
  return (
    <OrgProvider>
      <div className="flex min-h-screen flex-col bg-background">
        <header className="flex h-14 items-center justify-between border-b border-border px-6">
          <nav className="flex items-center gap-6">
            <span className="text-sm font-semibold text-foreground">Security</span>
            <NavItem to="/security" end>Dashboard</NavItem>
            <NavItem to="/security/enroll">Enroll</NavItem>
          </nav>
          <OrgSwitcher />
        </header>
        <main className="flex-1 p-6">
          <Breadcrumb />
          <Outlet />
        </main>
      </div>
    </OrgProvider>
  );
}

export default SecurityLayout;
