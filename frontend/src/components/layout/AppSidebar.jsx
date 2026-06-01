import { useCallback, useEffect, useState } from 'react';
import { NavLink } from 'react-router-dom';
import OrgSwitcher from '../OrgSwitcher';
import ReportIssueModal from '../ReportIssueModal';
import {
  LayoutDashboard,
  FileText,
  FilePlus,
  HardDrive,
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
  Zap,
  ChevronLeft,
  ChevronRight,
  ChevronDown,
  Filter,
  Bell,
  Globe,
  History,
  CalendarClock,
  Mail,
  Users,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { useAuth } from '../../context/AuthContext';
import api from '@/lib/axios';

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
  const [ingressOpen, setIngressOpen] = useState(() => readLS('sidebar:ingress:open', true));
  const [blogOpen, setBlogOpen] = useState(() => readLS('sidebar:blog:open', true));
  const [adminOpen, setAdminOpen] = useState(() => readLS('sidebar:admin:open', true));
  const [reportOpen, setReportOpen] = useState(false);
  const [pendingSignups, setPendingSignups] = useState(0);
  const [newAlertCount, setNewAlertCount] = useState(0);

  const fetchNewAlertCount = useCallback(() => {
    api
      .get('/api/alerts/', { params: { state: 'new', per_page: 1 } })
      .then((res) => setNewAlertCount(res.data.count ?? 0))
      .catch(() => {});
  }, []);

  const fetchPendingCount = useCallback(() => {
    if (!isStaff) return;
    api
      .get('/api/signups/pending-count/')
      .then((res) => setPendingSignups(res.data.count ?? 0))
      .catch(() => {});
  }, [isStaff]);

  useEffect(() => {
    fetchPendingCount();
    fetchNewAlertCount();
    const interval = setInterval(fetchNewAlertCount, 60000);
    return () => clearInterval(interval);
  }, [fetchPendingCount, fetchNewAlertCount]);

  useEffect(() => {
    window.addEventListener('signuprequest:changed', fetchPendingCount);
    return () => window.removeEventListener('signuprequest:changed', fetchPendingCount);
  }, [fetchPendingCount]);

  useEffect(() => { writeLS('sidebar:collapsed', collapsed); }, [collapsed]);
  useEffect(() => { writeLS('sidebar:incidents:open', incidentsOpen); }, [incidentsOpen]);
  useEffect(() => { writeLS('sidebar:security:open', securityOpen); }, [securityOpen]);
  useEffect(() => { writeLS('sidebar:ingress:open', ingressOpen); }, [ingressOpen]);
  useEffect(() => { writeLS('sidebar:blog:open', blogOpen); }, [blogOpen]);
  useEffect(() => { writeLS('sidebar:admin:open', adminOpen); }, [adminOpen]);

  const showItems = !collapsed;

  return (
    <>
      <ReportIssueModal open={reportOpen} onClose={() => setReportOpen(false)} />

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
        <div className="flex h-16 shrink-0 items-center border-b border-border px-4 gap-2">
          {!collapsed && <OrgSwitcher />}
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

        <nav className="flex flex-col gap-2 p-3 flex-1 overflow-y-auto no-scrollbar">

          <SidebarLink to="/dashboard" end icon={LayoutDashboard} collapsed={collapsed}>
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
                <NavLink
                  to="/alerts"
                  title={collapsed ? 'Alert Inbox' : undefined}
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
                  <Bell className="h-4 w-4 shrink-0" />
                  {!collapsed && (
                    <>
                      <span>Alert Inbox</span>
                      {newAlertCount > 0 && (
                        <span className="ml-auto rounded-full bg-blue-600 px-1.5 py-0.5 text-xs font-semibold text-white">
                          {newAlertCount}
                        </span>
                      )}
                    </>
                  )}
                </NavLink>
                <SidebarLink to="/tasks" icon={ListChecks} collapsed={collapsed}>
                  Tasks
                </SidebarLink>
                <SidebarLink to="/contacts" icon={Users} collapsed={collapsed}>
                  Contacts
                </SidebarLink>
                <SidebarLink to="/assets" icon={HardDrive} collapsed={collapsed}>
                  Assets
                </SidebarLink>
                {isStaff && (
                  <>
                    <SidebarLink to="/admin/incidents/subjects" icon={Tag} collapsed={collapsed}>
                      Subjects
                    </SidebarLink>
                    <SidebarLink to="/admin/incidents/task-templates" icon={ListChecks} collapsed={collapsed}>
                      Task Templates
                    </SidebarLink>
                    <SidebarLink to="/admin/incidents/automations" icon={Zap} collapsed={collapsed}>
                      Automations
                    </SidebarLink>
                    <SidebarLink to="/admin/wazuh-responses" icon={ShieldCheck} collapsed={collapsed}>
                      Wazuh Responses
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

          <div className="space-y-1">
            {showItems && (
              <SectionToggle
                label="App Ingress"
                open={ingressOpen}
                onToggle={() => setIngressOpen((o) => !o)}
              />
            )}
            {(ingressOpen || collapsed) && (
              <SidebarLink to="/routes" icon={Globe} collapsed={collapsed}>
                Routes
              </SidebarLink>
            )}
          </div>

          {isStaff && (
            <div className="space-y-1">
              {showItems && (
                <SectionToggle
                  label="Blog"
                  open={blogOpen}
                  onToggle={() => setBlogOpen((o) => !o)}
                />
              )}
              {(blogOpen || collapsed) && (
                <>
                  <SidebarLink to="/admin" end icon={FileText} collapsed={collapsed}>
                    Blog Administration
                  </SidebarLink>
                  <SidebarLink to="/admin/posts" icon={FileText} collapsed={collapsed}>
                    Posts
                  </SidebarLink>
                  <SidebarLink to="/admin/posts/new" icon={FilePlus} collapsed={collapsed}>
                    New Post
                  </SidebarLink>
                </>
              )}
            </div>
          )}

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
                  <SidebarLink to="/admin/status-settings" icon={Server} collapsed={collapsed}>
                    Service Monitor
                  </SidebarLink>
                  <SidebarLink to="/admin/security/organizations" icon={Shield} collapsed={collapsed}>
                    Organisations
                  </SidebarLink>
                  <SidebarLink to="/admin/security/downloads" icon={Download} collapsed={collapsed}>
                    Downloads
                  </SidebarLink>
                  <NavLink
                    to="/admin/signup-requests"
                    title={collapsed ? 'Signup Requests' : undefined}
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
                    <UserPlus className="h-4 w-4 shrink-0" />
                    {!collapsed && (
                      <>
                        <span>Signup Requests</span>
                        {pendingSignups > 0 && (
                          <span className="ml-auto rounded-full bg-primary px-1.5 py-0.5 text-xs font-semibold text-primary-foreground">
                            {pendingSignups}
                          </span>
                        )}
                      </>
                    )}
                  </NavLink>
                  <SidebarLink to="/admin/tasks/history" icon={History} collapsed={collapsed}>
                    Task History
                  </SidebarLink>
                  <SidebarLink to="/admin/tasks/scheduled" icon={CalendarClock} collapsed={collapsed}>
                    Scheduled Tasks
                  </SidebarLink>
                  <SidebarLink to="/admin/email-templates" icon={Mail} collapsed={collapsed}>
                    Email Templates
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

          <div className="space-y-1">
            {showItems && (
              <span className="px-3 py-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                Account
              </span>
            )}
            <SidebarLink to="/account/notifications" icon={Bell} collapsed={collapsed}>
              Notifications
            </SidebarLink>
          </div>
        </nav>

        {isStaff && !collapsed && (
          <div className="shrink-0 border-t border-border p-3">
            <button
              onClick={() => setReportOpen(true)}
              className="w-full rounded-md border border-border bg-background px-3 py-1.5 text-sm font-medium text-foreground hover:bg-accent transition-colors text-left"
              aria-label="Report issue"
            >
              Report issue
            </button>
          </div>
        )}
      </aside>
    </>
  );
}

export default AppSidebar;
