import { NavLink } from 'react-router-dom';
import { LayoutDashboard, FileText, FilePlus, Server } from 'lucide-react';
import { cn } from '@/lib/utils';

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

function Sidebar() {
  return (
    <aside className="flex w-56 shrink-0 flex-col border-r border-border bg-card">
      <div className="flex h-16 items-center border-b border-border px-4">
        <span className="text-sm font-semibold text-foreground">Admin</span>
      </div>
      <nav className="flex flex-col gap-4 p-3">
        <SidebarSection title="General">
          <SidebarLink to="/admin" end icon={LayoutDashboard}>
            Dashboard
          </SidebarLink>
        </SidebarSection>

        <SidebarSection title="Content">
          <SidebarLink to="/admin/posts" icon={FileText}>
            All Posts
          </SidebarLink>
          <SidebarLink to="/admin/posts/new" icon={FilePlus}>
            New Post
          </SidebarLink>
        </SidebarSection>

        <SidebarSection title="Services">
          <SidebarLink to="/admin/status-settings" icon={Server}>
            Service Monitor
          </SidebarLink>
          <div className="flex items-center gap-3 rounded-md px-3 py-2 text-sm text-muted-foreground/50 cursor-default select-none">
            <Server className="h-4 w-4 shrink-0" />
            <span>Analytics</span>
            <span className="ml-auto text-xs">Soon</span>
          </div>
        </SidebarSection>
      </nav>
    </aside>
  );
}

export default Sidebar;
