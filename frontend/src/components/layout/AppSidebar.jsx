import { useEffect, useState } from 'react';
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
  Activity,
  UserPlus,
  BarChart2,
  ClipboardList,
  ShieldOff,
  AlertTriangle,
  Tag,
  ListChecks,
  ChevronLeft,
  ChevronRight,
  ChevronDown,
  Filter,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { useAuth } from '../../context/AuthContext';

function readLS(key, fallback) {
  try {
    const raw = localStorage.getItem(key);
    return raw != null ? JSON.parse(raw) : fallback;
  } catch {
    return fallback;
  }
}

function writeLS(key, value) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // localStorage unavailable (e.g. test environment without storage)
  }
}

function SidebarLink({ to, end, icon: Icon, collapsed, children }) {
  return (
    <NavLink
      to={to}
      end={end}
      title={collapsed ? String(children) : undefined}
      className={({ isActive }) =>
        cn(
          'flex items-center rounded-md px-3 py-2 text-sm font-medium transition-colors',
          collapsed ? 'justify-center px-2 gap-0' : 'gap-3',
          isActive
            ? 'bg-accent text-accent-foreground'
            : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground'
        )
      }
    >
      {Icon && <Icon className="h-4 w-4 shrink-0" />}
      {!collapsed && children}
    </NavLink>
  );
}

function SectionToggle({ label, open, onToggle }) {
  return (
    <button
      onClick={onToggle}
      aria-expanded={open}
      className="flex w-full items-center justify-between px-3 py-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground hover:text-foreground transition-colors"
    >
      <span>{label}</span>
      {open ? (
        <ChevronDown className="h-3 w-3" aria-hidden="true" />
      ) : (
        <ChevronRight className="h-3 w-3" aria-hidden="true" />
      )}
    </button>
  );
}

function AppSidebar({ mobileOpen = false, onMobileClose }) {
  const { user } = useAuth();
  const isStaff = user?.is_staff;

  const [collapsed, setCollapsed] = useState(() => readLS('sidebar:collapsed', false));
  const [incidentsOpen, setIncidentsOpen] = useState(() => readLS('sidebar:incidents:open', true));
  const [securityOpen, setSecurityOpen] = useState(() => readLS('sidebar:security:open', true));
  const [adminOpen, setAdminOpen] = useState(() => readLS('sidebar:admin:open', true));

  useEffect(() => { writeLS('sidebar:collapsed', collapsed); }, [collapsed]);
  useEffect(() => { writeLS('sidebar:incidents:open', incidentsOpen); }, [incidentsOpen]);
  useEffect(() => { writeLS('sidebar:security:open', securityOpen); }, [securityOpen]);
  useEffect(() => { writeLS('sidebar:admin:open', adminOpen); }, [adminOpen]);

  const showItems = !collapsed;

  return (
    <>
      {mobileOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/40 md:hidden"
          onClick={onMobileClose}
          aria-hidden="true"
        />
      )}

      <aside
        className={cn(
          'flex-col border-r border-border bg-card transition-all duration-200',
          mobileOpen
            ? 'fixed top-28 bottom-0 left-0 z-50 w-56 flex'
            : cn('hidden md:flex', collapsed ? 'w-14' : 'w-56')
        )}
      >
        <div className="flex h-16 items-center border-b border-border px-4">
          {!collapsed && (
            <span className="text-sm font-semibold text-foreground">vels.online</span>
          )}
          <button
            onClick={() => setCollapsed((c) => !c)}
            aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
            className="ml-auto rounded-md p-1 text-muted-foreground hover:bg-accent hover:text-accent-foreground transition-colors"
          >
            {collapsed ? (
              <ChevronRight className="h-4 w-4" aria-hidden="true" />
            ) : (
              <ChevronLeft className="h-4 w-4" aria-hidden="true" />
            )}
          </button>
        </div>

        <nav className="flex flex-col gap-2 p-3">
          <SidebarLink to="/admin" end icon={LayoutDashboard} collapsed={collapsed}>
            Dashboard
          </SidebarLink>

          <div className="space-y-1">
            {showItems && (
              <SectionToggle
                label="Incidents"
                open={incidentsOpen}
                onToggle={() => setIncidentsOpen((o) => !o)}
              />
            )}
            {(incidentsOpen || collapsed) && (
              <>
                <SidebarLink to="/incidents" icon={AlertTriangle} collapsed={collapsed}>
                  Incidents
                </SidebarLink>
                {isStaff && (
                  <>
                    <SidebarLink to="/admin/incidents/subjects" icon={Tag} collapsed={collapsed}>
                      Subjects
                    </SidebarLink>
                    <SidebarLink to="/admin/incidents/task-templates" icon={ListChecks} collapsed={collapsed}>
                      Task Templates
                    </SidebarLink>
                  </>
                )}
              </>
            )}
          </div>

          <div className="space-y-1">
            {showItems && (
              <SectionToggle
                label="Security"
                open={securityOpen}
                onToggle={() => setSecurityOpen((o) => !o)}
              />
            )}
            {(securityOpen || collapsed) && (
              <>
                <SidebarLink to="/security" end icon={ShieldCheck} collapsed={collapsed}>
                  Overview
                </SidebarLink>
                <SidebarLink to="/security/vulnerabilities" icon={Bug} collapsed={collapsed}>
                  Vulnerabilities
                </SidebarLink>
                <SidebarLink to="/security/events" icon={Activity} collapsed={collapsed}>
                  Events
                </SidebarLink>
                <SidebarLink to="/security/work-package" icon={ClipboardList} collapsed={collapsed}>
                  Work Package
                </SidebarLink>
                <SidebarLink to="/security/risk-acceptances" icon={ShieldOff} collapsed={collapsed}>
                  Accepted Risks
                </SidebarLink>
                <SidebarLink to="/exceptions" icon={Filter} collapsed={collapsed}>
                  Exception Rules
                </SidebarLink>
                <SidebarLink to="/security/enroll" icon={UserPlus} collapsed={collapsed}>
                  Enroll
                </SidebarLink>
              </>
            )}
          </div>

          {isStaff && (
            <div className="space-y-1">
              {showItems && (
                <SectionToggle
                  label="Admin"
                  open={adminOpen}
                  onToggle={() => setAdminOpen((o) => !o)}
                />
              )}
              {(adminOpen || collapsed) && (
                <>
                  <SidebarLink to="/admin/posts" icon={FileText} collapsed={collapsed}>
                    Posts
                  </SidebarLink>
                  <SidebarLink to="/admin/posts/new" icon={FilePlus} collapsed={collapsed}>
                    New Post
                  </SidebarLink>
                  <SidebarLink to="/admin/status-settings" icon={Server} collapsed={collapsed}>
                    Service Monitor
                  </SidebarLink>
                  <SidebarLink to="/admin/security/organizations" icon={Shield} collapsed={collapsed}>
                    Organisations
                  </SidebarLink>
                  <SidebarLink to="/admin/security/downloads" icon={Download} collapsed={collapsed}>
                    Downloads
                  </SidebarLink>
                  <div
                    className={cn(
                      'flex items-center rounded-md px-3 py-2 text-sm text-muted-foreground/50 cursor-default select-none',
                      collapsed ? 'justify-center px-2' : 'gap-3'
                    )}
                    title={collapsed ? 'Analytics (coming soon)' : undefined}
                    aria-disabled="true"
                  >
                    <BarChart2 className="h-4 w-4 shrink-0" aria-hidden="true" />
                    {!collapsed && (
                      <>
                        <span>Analytics</span>
                        <span className="ml-auto text-xs">Soon</span>
                      </>
                    )}
                  </div>
                </>
              )}
            </div>
          )}
        </nav>
      </aside>
    </>
  );
}

export default AppSidebar;
