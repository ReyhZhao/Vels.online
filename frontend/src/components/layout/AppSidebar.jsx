import { NavLink } from 'react-router-dom';
import {
  LayoutDashboard,
  FileText,
  FilePlus,
  Server,
  Shield,
  Download,
  ShieldCheck,
  Bug,
  UserPlus,
  BarChart2,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { useAuth } from '../../context/AuthContext';

function SidebarLink({ to, end, icon: Icon, children }) {
  return (
    <NavLink
      to={to}
      end={end}
      className={({ isActive }) =>
        cn(
          'flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors',
          isActive
            ? 'bg-accent text-accent-foreground'
            : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground'
        )
      }
    >
      {Icon && <Icon className="h-4 w-4 shrink-0" />}
      {children}
    </NavLink>
  );
}

function SidebarSection({ title, children }) {
  return (
    <div className="space-y-1">
      <p className="px-3 py-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
        {title}
      </p>
      {children}
    </div>
  );
}

function AppSidebar() {
  const { user } = useAuth();
  const isStaff = user?.is_staff;

  return (
    <aside className="flex w-56 shrink-0 flex-col border-r border-border bg-card">
      <div className="flex h-16 items-center border-b border-border px-4">
        <span className="text-sm font-semibold text-foreground">vels.online</span>
      </div>
      <nav className="flex flex-col gap-4 p-3">
        <SidebarLink to="/admin" end icon={LayoutDashboard}>
          Dashboard
        </SidebarLink>

        <SidebarSection title="Security">
          <SidebarLink to="/security" end icon={ShieldCheck}>
            Overview
          </SidebarLink>
          <SidebarLink to="/security/vulnerabilities" icon={Bug}>
            Vulnerabilities
          </SidebarLink>
          <SidebarLink to="/security/enroll" icon={UserPlus}>
            Enroll
          </SidebarLink>
        </SidebarSection>

        {isStaff && (
          <SidebarSection title="Admin">
            <SidebarLink to="/admin/posts" icon={FileText}>
              Posts
            </SidebarLink>
            <SidebarLink to="/admin/posts/new" icon={FilePlus}>
              New Post
            </SidebarLink>
            <SidebarLink to="/admin/status-settings" icon={Server}>
              Service Monitor
            </SidebarLink>
            <SidebarLink to="/admin/security/organizations" icon={Shield}>
              Organisations
            </SidebarLink>
            <SidebarLink to="/admin/security/downloads" icon={Download}>
              Downloads
            </SidebarLink>
            <div
              className="flex items-center gap-3 rounded-md px-3 py-2 text-sm text-muted-foreground/50 cursor-default select-none"
              aria-disabled="true"
            >
              <BarChart2 className="h-4 w-4 shrink-0" />
              <span>Analytics</span>
              <span className="ml-auto text-xs">Soon</span>
            </div>
          </SidebarSection>
        )}
      </nav>
    </aside>
  );
}

export default AppSidebar;
