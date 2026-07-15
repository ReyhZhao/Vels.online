import { useState, useEffect, useCallback } from 'react';
import { Link } from 'react-router-dom';
import {
  Shield, Globe, Siren, CalendarClock, Telescope, Package, RefreshCw, Inbox, UserX, CheckCheck,
} from 'lucide-react';
import api from '../lib/axios';
import { useOrganization } from '../context/OrgContext';
import { useAuth } from '../context/AuthContext';
import { OnCallWidgetCompact } from '../components/OnCallWidget';
import StatTile from '../components/dashboard/StatTile';
import ChartCard from '../components/dashboard/ChartCard';
import BreakdownBars from '../components/dashboard/BreakdownBars';
import IncidentTrendCard from '../components/dashboard/IncidentTrendCard';
import VulnTrendCard from '../components/dashboard/VulnTrendCard';
import AlertVolumeCard from '../components/dashboard/AlertVolumeCard';
import RecentIncidents from '../components/dashboard/RecentIncidents';
import {
  SEVERITY_COLORS, SEVERITY_ORDER, SEVERITY_LABELS, INCIDENT_STATES, CATEGORICAL,
} from '../components/dashboard/palette';

const RANGES = [7, 30, 90];

const SERVICES = [
  { icon: Shield, title: 'Security', description: 'Vulnerability and agent monitoring', to: '/security' },
  { icon: Globe, title: 'Ingress', description: 'Reverse proxy and WAF routes', to: '/routes' },
  { icon: Siren, title: 'Incidents', description: 'Security incident management', to: '/incidents' },
  { icon: Package, title: 'Work Package', description: 'Prioritised remediation work', to: '/security/work-package' },
  { icon: CalendarClock, title: 'On-Call', description: 'On-call schedule and shifts', to: '/admin/incidents/oncall', staffOnly: true },
  { icon: Telescope, title: 'Threat Hunting', description: 'LLM-assisted threat hunts', to: '/hunting', staffOnly: true },
];

function QueueTile({ icon: Icon, label, value, to }) {
  return (
    <Link
      to={to}
      className="flex items-center gap-3 rounded-lg border border-border bg-card px-4 py-3 transition-colors hover:bg-accent/60"
    >
      <Icon className="h-4 w-4 shrink-0 text-muted-foreground" />
      <span className="flex-1 text-sm text-muted-foreground">{label}</span>
      <span className="text-lg font-semibold text-foreground">{value ?? '—'}</span>
    </Link>
  );
}

export default function DashboardPage() {
  const orgContext = useOrganization();
  const selectedOrg = orgContext?.selectedOrg ?? null;
  const setViewAllOrgs = orgContext?.setViewAllOrgs;
  const { user } = useAuth();
  const isStaff = !!user?.is_staff;
  // Staff "All organisations" view: aggregate the DB-backed panels across every
  // tenant. Only staff can enter it; the switcher never offers it otherwise.
  const allOrgs = isStaff && !!orgContext?.viewAllOrgs;

  const [days, setDays] = useState(30);

  // Leaving the dashboard drops the all-orgs view so it never leaks into the
  // concrete-org selection every other page depends on.
  useEffect(() => () => setViewAllOrgs?.(false), [setViewAllOrgs]);

  // /api/dashboard/overview/ — incidents, alerts, routes (+ staff queues)
  const [overview, setOverview] = useState(null);
  const [overviewLoading, setOverviewLoading] = useState(false);
  const [overviewError, setOverviewError] = useState(false);

  // /api/security/dashboard/ — Wazuh-backed agents / vulnerabilities / events
  const [stats, setStats] = useState(null);
  const [statsLoading, setStatsLoading] = useState(false);

  const [refreshing, setRefreshing] = useState(false);

  const fetchAll = useCallback((slug, aggregate) => {
    setOverviewLoading(true);
    setOverviewError(false);
    api.get('/api/dashboard/overview/', { params: { org: aggregate ? '__all__' : slug } })
      .then(res => setOverview(res.data))
      .catch(() => { setOverview(null); setOverviewError(true); })
      .finally(() => setOverviewLoading(false));

    if (aggregate) {
      // Wazuh/OpenSearch numbers are per-org only in the all-orgs view.
      setStats(null);
      setStatsLoading(false);
      return;
    }
    setStatsLoading(true);
    api.get(`/api/security/dashboard/?org=${slug}`)
      .then(res => setStats(res.data))
      .catch(() => setStats(null))
      .finally(() => setStatsLoading(false));
  }, []);

  useEffect(() => {
    if (!selectedOrg) return;
    fetchAll(selectedOrg.slug, allOrgs);
  }, [selectedOrg, allOrgs, fetchAll]);

  async function handleRefresh() {
    if (!selectedOrg || refreshing) return;
    setRefreshing(true);
    try {
      await api.post('/api/security/dashboard/refresh/', { org: selectedOrg.slug });
    } catch {
      // cache clear is best-effort; still refetch
    }
    fetchAll(selectedOrg.slug);
    setRefreshing(false);
  }

  if (!selectedOrg) {
    return (
      <div className="p-6">
        <h1 className="text-2xl font-semibold text-foreground">Dashboard</h1>
        <p className="mt-4 text-sm text-muted-foreground">No organisation selected.</p>
      </div>
    );
  }

  const inc = overview?.incidents;
  const alerts = overview?.alerts;
  const routes = overview?.routes;
  const staff = overview?.staff;

  const vulnTotal = stats?.vulnerabilities != null
    ? Object.values(stats.vulnerabilities).reduce((a, b) => a + b, 0)
    : null;
  const criticalVulns = stats?.vulnerabilities?.critical ?? 0;

  const severityItems = SEVERITY_ORDER.map(key => ({
    key,
    label: SEVERITY_LABELS[key],
    count: inc?.by_severity?.[key] ?? 0,
    color: SEVERITY_COLORS[key],
    to: `/incidents?severity=${key}`,
  }));

  // One series, one hue: the rows are already labeled, so color would only
  // repeat what the bar length says.
  const stateItems = INCIDENT_STATES.map(s => ({
    key: s.key,
    label: s.label,
    count: inc?.by_state?.[s.key] ?? 0,
    color: CATEGORICAL[0],
    to: `/incidents?state=${s.key}`,
  }));

  const openBreakdownTable = {
    columns: [
      { key: 'group', label: 'Breakdown' },
      { key: 'label', label: 'Category' },
      { key: 'count', label: 'Open', align: 'right' },
    ],
    rows: [
      ...severityItems.map(({ label, count }) => ({ group: 'Severity', label, count })),
      ...stateItems.map(({ label, count }) => ({ group: 'State', label, count })),
    ],
  };

  return (
    <div className="space-y-6 p-6">
      {/* Header + the one filter row that scopes the trend charts below */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-foreground">Dashboard</h1>
          <p className="text-sm text-muted-foreground">{allOrgs ? 'All organisations' : selectedOrg.name}</p>
        </div>
        <div className="flex items-center gap-2">
          <div className="flex gap-1 rounded-md border border-border bg-card p-0.5" role="group" aria-label="Trend range">
            {RANGES.map(d => (
              <button
                key={d}
                onClick={() => setDays(d)}
                aria-pressed={days === d}
                className={`rounded px-2.5 py-1 text-xs font-medium transition-colors ${
                  days === d
                    ? 'bg-foreground text-background'
                    : 'text-muted-foreground hover:text-foreground hover:bg-accent'
                }`}
              >
                {d}d
              </button>
            ))}
          </div>
          {!allOrgs && (
            <button
              onClick={handleRefresh}
              disabled={refreshing}
              className="flex items-center gap-1.5 rounded-md border border-border bg-card px-3 py-1.5 text-xs font-medium text-foreground hover:bg-accent disabled:opacity-50"
            >
              <RefreshCw className={`h-3.5 w-3.5 ${refreshing ? 'animate-spin' : ''}`} aria-hidden="true" />
              {refreshing ? 'Refreshing…' : 'Refresh'}
            </button>
          )}
        </div>
      </div>

      {overviewError && (
        <p className="rounded-md border border-destructive/50 bg-destructive/10 px-4 py-2 text-sm text-destructive">
          Failed to load dashboard data — some panels may be empty.
        </p>
      )}

      {/* KPI row */}
      <section aria-label="Key metrics" className="grid grid-cols-2 gap-4 sm:grid-cols-3 xl:grid-cols-6">
        <StatTile
          label="Open incidents"
          value={inc?.open_total}
          isLoading={overviewLoading}
          delta={inc ? `+${inc.created_7d} / −${inc.closed_7d}` : null}
          sub="opened / closed, 7d"
          to="/incidents"
        />
        <StatTile
          label="New alerts"
          value={alerts?.new_total}
          isLoading={overviewLoading}
          sub={alerts ? `${alerts.last_24h} in last 24h` : null}
          trend={alerts?.daily_7d?.map(d => d.count)}
          to="/alerts"
        />
        <StatTile
          label="Vulnerabilities"
          value={allOrgs ? '—' : vulnTotal}
          isLoading={statsLoading}
          delta={allOrgs ? null : (criticalVulns > 0 ? `${criticalVulns} critical` : null)}
          deltaGood={allOrgs ? null : (criticalVulns === 0 ? null : false)}
          sub={allOrgs ? 'Per-org only' : null}
          to="/security/vulnerabilities"
        />
        <StatTile
          label="Agents active"
          value={allOrgs ? '—' : (stats ? `${stats.active_count}/${stats.agent_count}` : null)}
          isLoading={statsLoading}
          delta={allOrgs ? null : (stats && stats.active_count < stats.agent_count
            ? `${stats.agent_count - stats.active_count} disconnected`
            : null)}
          deltaGood={allOrgs ? null : (stats ? stats.active_count === stats.agent_count : null)}
          sub={allOrgs ? 'Per-org only' : null}
          to="/security"
        />
        <StatTile
          label="Routes"
          value={routes?.total}
          isLoading={overviewLoading}
          delta={routes?.by_status?.error ? `${routes.by_status.error} in error` : null}
          deltaGood={routes ? routes.by_status.error === 0 : null}
          sub={routes ? `${routes.by_status.active} active` : null}
          to="/routes"
        />
        <StatTile
          label="Events (24h)"
          value={allOrgs ? '—' : stats?.events_24h}
          isLoading={statsLoading}
          sub={allOrgs ? 'Per-org only' : null}
          to="/security"
        />
      </section>

      {/* Staff work queues */}
      {isStaff && (
        <section aria-label="Staff queues" className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <OnCallWidgetCompact />
          <QueueTile icon={Inbox} label="Needs triage" value={staff?.needs_triage} to="/incidents?state=new" />
          <QueueTile icon={CheckCheck} label="Pending closure" value={staff?.pending_closure} to="/incidents?state=pending_closure" />
          <QueueTile icon={UserX} label="Unassigned" value={staff?.unassigned_open} to="/incidents?tab=unassigned" />
        </section>
      )}

      {/* Charts */}
      <section aria-label="Trends" className="grid grid-cols-1 items-start gap-4 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <IncidentTrendCard orgSlug={allOrgs ? '__all__' : selectedOrg.slug} days={days} />
        </div>
        <ChartCard title="Open incidents" to="/incidents" table={openBreakdownTable}>
          <div className="space-y-4">
            <div>
              <p className="mb-1.5 text-xs font-medium uppercase tracking-wider text-muted-foreground">By severity</p>
              <BreakdownBars items={severityItems} ariaLabel="Open incidents by severity" />
            </div>
            <div>
              <p className="mb-1.5 text-xs font-medium uppercase tracking-wider text-muted-foreground">By state</p>
              <BreakdownBars items={stateItems} ariaLabel="Open incidents by state" />
            </div>
          </div>
        </ChartCard>

        <div className="lg:col-span-2">
          {allOrgs ? (
            <div className="flex h-full min-h-[12rem] flex-col rounded-lg border border-border bg-card p-4">
              <h3 className="text-sm font-medium text-foreground">Vulnerability trend</h3>
              <div className="flex flex-1 items-center justify-center">
                <p className="text-sm text-muted-foreground">Select an organisation to view vulnerability trends.</p>
              </div>
            </div>
          ) : (
            <VulnTrendCard orgSlug={selectedOrg.slug} days={days} />
          )}
        </div>
        <AlertVolumeCard daily={alerts?.daily_7d} loading={overviewLoading} />
      </section>

      <section aria-label="Activity" className="grid grid-cols-1 items-start gap-4 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <RecentIncidents incidents={inc?.recent} loading={overviewLoading} />
        </div>

        {/* Services quick links */}
        <div className="rounded-lg border border-border bg-card">
          <h3 className="px-4 pt-3 pb-1 text-sm font-medium text-foreground">Services</h3>
          <ul className="px-2 pb-2 pt-1">
            {SERVICES.filter(s => isStaff || !s.staffOnly).map(({ icon: Icon, title, description, to }) => (
              <li key={to}>
                <Link
                  to={to}
                  className="flex items-center gap-3 rounded-md px-2 py-2 transition-colors hover:bg-accent/60"
                >
                  <Icon className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />
                  <span className="min-w-0">
                    <span className="block text-sm text-foreground">{title}</span>
                    <span className="block truncate text-xs text-muted-foreground">{description}</span>
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        </div>
      </section>
    </div>
  );
}
