import { useCallback, useEffect, useRef, useState } from 'react';
import { NavLink } from 'react-router-dom';
import OrgSwitcher from '../OrgSwitcher';
import ReportIssueModal from '../ReportIssueModal';
import {
  ChevronLeft,
  ChevronRight,
  ChevronDown,
  Search,
  X,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { useAuth } from '../../context/AuthContext';
import { useNavCounts } from '../../hooks/useNavCounts';
import { useSwipeGesture } from '../../hooks/useSwipeGesture';
import { DASHBOARD_LINK, NAV_SECTIONS } from './navConfig';
import { VERSION_LABEL, VERSION_DETAIL, GIT_SHA } from '@/lib/version';

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

function formatCount(count) {
  return count > 99 ? '99+' : String(count);
}

function CountBadge({ count, tone = 'default' }) {
  return (
    <span
      className={cn(
        'ml-auto rounded-full px-1.5 py-0.5 text-xs font-semibold',
        tone === 'info' ? 'bg-blue-600 text-white' : 'bg-primary text-primary-foreground'
      )}
    >
      {formatCount(count)}
    </span>
  );
}

function SidebarLink({ to, end, icon: Icon, label, iconOnly, count = 0, badgeTone, onNavigate }) {
  return (
    <NavLink
      to={to}
      end={end}
      onClick={onNavigate}
      title={iconOnly ? label : undefined}
      className={({ isActive }) =>
        cn(
          'flex items-center rounded-md px-3 py-2.5 md:py-2 text-sm font-medium transition-colors',
          iconOnly ? 'justify-center px-2 gap-0' : 'gap-3',
          isActive
            ? 'bg-accent text-accent-foreground'
            : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground'
        )
      }
    >
      {Icon && (
        <span className="relative shrink-0">
          <Icon className="h-4 w-4" aria-hidden="true" />
          {iconOnly && count > 0 && (
            <span
              className={cn(
                'absolute -right-1.5 -top-1.5 h-2 w-2 rounded-full',
                badgeTone === 'info' ? 'bg-blue-600' : 'bg-primary'
              )}
              aria-hidden="true"
            />
          )}
        </span>
      )}
      {!iconOnly && (
        <>
          <span className="truncate">{label}</span>
          {count > 0 && <CountBadge count={count} tone={badgeTone} />}
        </>
      )}
    </NavLink>
  );
}

function DisabledItem({ icon: Icon, label, hint, iconOnly }) {
  return (
    <div
      className={cn(
        'flex items-center rounded-md px-3 py-2.5 md:py-2 text-sm text-muted-foreground/50 cursor-default select-none',
        iconOnly ? 'justify-center px-2' : 'gap-3'
      )}
      title={iconOnly ? `${label} (coming soon)` : undefined}
      aria-disabled="true"
    >
      <Icon className="h-4 w-4 shrink-0" aria-hidden="true" />
      {!iconOnly && (
        <>
          <span>{label}</span>
          {hint && <span className="ml-auto text-xs">{hint}</span>}
        </>
      )}
    </div>
  );
}

function SectionToggle({ label, open, onToggle, count = 0 }) {
  return (
    <button
      onClick={onToggle}
      aria-expanded={open}
      className="flex w-full items-center justify-between rounded-md px-3 py-2.5 md:py-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground hover:text-foreground transition-colors"
    >
      <span className="flex items-center gap-2">
        <span>{label}</span>
        {!open && count > 0 && (
          <span className="rounded-full bg-primary px-1.5 text-[10px] font-semibold leading-4 text-primary-foreground normal-case tracking-normal">
            {formatCount(count)}
          </span>
        )}
      </span>
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
  const counts = useNavCounts(isStaff);
  const asideRef = useRef(null);

  const [collapsed, setCollapsed] = useState(() => readLS('sidebar:collapsed', false));
  const [openSections, setOpenSections] = useState(() => {
    const initial = {};
    for (const section of NAV_SECTIONS) {
      initial[section.id] = readLS(`sidebar:${section.id}:open`, true);
    }
    return initial;
  });
  const [filter, setFilter] = useState('');
  const [reportOpen, setReportOpen] = useState(false);

  // The drawer always shows full labels; icon-only mode is desktop-only.
  const iconOnly = collapsed && !mobileOpen;

  useEffect(() => { writeLS('sidebar:collapsed', collapsed); }, [collapsed]);

  const toggleSection = useCallback((id) => {
    setOpenSections((prev) => {
      const next = { ...prev, [id]: !prev[id] };
      writeLS(`sidebar:${id}:open`, next[id]);
      return next;
    });
  }, []);

  // Close the mobile drawer when a destination is chosen.
  const handleNavigate = useCallback(() => {
    if (mobileOpen) onMobileClose?.();
  }, [mobileOpen, onMobileClose]);

  // Escape closes the mobile drawer.
  useEffect(() => {
    if (!mobileOpen) return undefined;
    const onKey = (e) => {
      if (e.key === 'Escape') onMobileClose?.();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [mobileOpen, onMobileClose]);

  // Swipe left on the drawer closes it.
  useSwipeGesture(
    asideRef,
    useCallback(() => {
      if (mobileOpen) onMobileClose?.();
    }, [mobileOpen, onMobileClose]),
    { direction: 'left' }
  );

  const query = filter.trim().toLowerCase();
  const filtering = query.length > 0;

  const visibleSections = NAV_SECTIONS
    .filter((section) => !section.staffOnly || isStaff)
    .map((section) => ({
      ...section,
      items: section.items.filter(
        (item) =>
          (!item.staffOnly || isStaff) &&
          (!filtering || item.label.toLowerCase().includes(query))
      ),
    }))
    .filter((section) => section.items.length > 0);

  const dashboardVisible = !filtering || DASHBOARD_LINK.label.toLowerCase().includes(query);

  const itemCount = (item) => (item.badge ? counts[item.badge] ?? 0 : 0);
  const sectionCount = (section) => section.items.reduce((sum, item) => sum + itemCount(item), 0);

  return (
    <>
      <ReportIssueModal open={reportOpen} onClose={() => setReportOpen(false)} />

      {mobileOpen && (
        <div
          className="fixed inset-0 z-[60] bg-black/40 md:hidden"
          onClick={onMobileClose}
          aria-hidden="true"
        />
      )}

      <aside
        ref={asideRef}
        className={cn(
          'flex-col border-r border-border bg-card transition-all duration-200',
          mobileOpen
            ? 'fixed inset-y-0 left-0 z-[70] flex w-72 max-w-[85vw] shadow-xl'
            : cn('hidden md:flex', collapsed ? 'w-14' : 'w-56')
        )}
      >
        <div className="flex h-16 shrink-0 items-center border-b border-border px-4 gap-2">
          {!iconOnly && <OrgSwitcher />}
          {mobileOpen ? (
            <button
              onClick={onMobileClose}
              aria-label="Close menu"
              className="ml-auto rounded-md p-1.5 text-muted-foreground hover:bg-accent hover:text-accent-foreground transition-colors"
            >
              <X className="h-5 w-5" aria-hidden="true" />
            </button>
          ) : (
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
          )}
        </div>

        {!iconOnly && (
          <div className="shrink-0 px-3 pt-3">
            <div className="relative">
              <Search
                className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground"
                aria-hidden="true"
              />
              <input
                value={filter}
                onChange={(e) => setFilter(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Escape' && filter) {
                    e.stopPropagation();
                    setFilter('');
                  }
                }}
                placeholder="Filter menu…"
                aria-label="Filter menu"
                className="w-full rounded-md border border-border bg-background py-1.5 pl-8 pr-7 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
              />
              {filtering && (
                <button
                  onClick={() => setFilter('')}
                  aria-label="Clear filter"
                  className="absolute right-1.5 top-1/2 -translate-y-1/2 rounded p-0.5 text-muted-foreground hover:text-foreground"
                >
                  <X className="h-3.5 w-3.5" aria-hidden="true" />
                </button>
              )}
            </div>
          </div>
        )}

        <nav aria-label="Primary" className="flex flex-col gap-2 p-3 flex-1 overflow-y-auto no-scrollbar">
          {dashboardVisible && (
            <SidebarLink
              {...DASHBOARD_LINK}
              iconOnly={iconOnly}
              onNavigate={handleNavigate}
            />
          )}

          {visibleSections.map((section) => {
            const open = filtering || openSections[section.id];
            return (
              <div key={section.id} className="space-y-1">
                {!iconOnly && (
                  <SectionToggle
                    label={section.label}
                    open={open}
                    onToggle={() => toggleSection(section.id)}
                    count={sectionCount(section)}
                  />
                )}
                {(open || iconOnly) &&
                  section.items.map((item) =>
                    item.disabled ? (
                      <DisabledItem key={item.label} {...item} iconOnly={iconOnly} />
                    ) : (
                      <SidebarLink
                        key={item.to}
                        {...item}
                        iconOnly={iconOnly}
                        count={itemCount(item)}
                        onNavigate={handleNavigate}
                      />
                    )
                  )}
              </div>
            );
          })}

          {filtering && !dashboardVisible && visibleSections.length === 0 && (
            <p className="px-3 py-2 text-sm text-muted-foreground">No menu items match.</p>
          )}
        </nav>

        {isStaff && (
          <div className="shrink-0 border-t border-border p-3 space-y-2">
            {!iconOnly && (
              <button
                onClick={() => setReportOpen(true)}
                className="w-full rounded-md border border-border bg-background px-3 py-1.5 text-sm font-medium text-foreground hover:bg-accent transition-colors text-left"
                aria-label="Report issue"
              >
                Report issue
              </button>
            )}
            <p
              title={VERSION_DETAIL}
              aria-label={VERSION_DETAIL}
              className={cn(
                'select-none text-[10px] leading-tight text-muted-foreground/50',
                iconOnly ? 'text-center' : 'px-1'
              )}
            >
              {iconOnly ? GIT_SHA.slice(0, 4) : VERSION_LABEL}
            </p>
          </div>
        )}
      </aside>
    </>
  );
}

export default AppSidebar;
