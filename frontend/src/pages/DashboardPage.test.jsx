import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';

vi.mock('../lib/axios', () => ({
  default: { get: vi.fn(), post: vi.fn() },
}));

// recharts needs layout (ResizeObserver); stub it so we can assert which
// series render — same pattern as IncidentTrendChart.test.jsx.
vi.mock('recharts', () => {
  const Stub = ({ children }) => <div>{children}</div>;
  const Mark = ({ name, onClick }) => (
    <button data-testid="mark" onClick={onClick}>{name}</button>
  );
  return {
    BarChart: Stub, Bar: Mark, LineChart: Stub, Line: Mark,
    XAxis: Stub, YAxis: Stub, CartesianGrid: Stub,
    Tooltip: Stub, Legend: Stub, ResponsiveContainer: Stub,
  };
});

import api from '../lib/axios';
import { AuthContext } from '../context/AuthContext';
import { OrgContext } from '../context/OrgContext';
import DashboardPage from './DashboardPage';

const SELECTED_ORG = { id: 1, name: 'Acme', slug: 'acme', wazuh_group: 'acme' };

const STATS = {
  agent_count: 5,
  active_count: 4,
  vulnerabilities: { critical: 2, high: 7, medium: 12, low: 3 },
  events_24h: 42,
};

const OVERVIEW = {
  incidents: {
    open_total: 6,
    by_state: { new: 2, triaged: 1, in_progress: 3, on_hold: 0, needs_tuning: 0, pending_closure: 0 },
    by_severity: { critical: 1, high: 2, medium: 3, low: 0, info: 0 },
    created_7d: 4,
    closed_7d: 2,
    recent: [
      {
        display_id: 'INC-2026-0007',
        title: 'Suspicious login burst',
        severity: 'high',
        state: 'new',
        created_at: new Date().toISOString(),
        assignee: null,
      },
    ],
  },
  alerts: {
    new_total: 9,
    last_24h: 3,
    by_severity: { critical: 1, high: 2, medium: 3, low: 3, info: 0 },
    unrated: 0,
    daily_7d: [
      { date: '2026-06-30', count: 1 },
      { date: '2026-07-01', count: 2 },
      { date: '2026-07-02', count: 0 },
      { date: '2026-07-03', count: 1 },
      { date: '2026-07-04', count: 2 },
      { date: '2026-07-05', count: 0 },
      { date: '2026-07-06', count: 3 },
    ],
  },
  routes: { total: 2, by_status: { active: 2, pending: 0, error: 0 } },
};

const STAFF_OVERVIEW = {
  ...OVERVIEW,
  staff: { needs_triage: 2, pending_closure: 0, unassigned_open: 5 },
};

const TREND = {
  days: 30,
  buckets: [{ date: '2026-07-05', counts: { 3: 2 } }, { date: '2026-07-06', counts: { 3: 1 } }],
  subjects: [{ key: '3', subject_id: 3, name: 'Brute Force', kind: 'real' }],
};

const VULN_TREND = {
  snapshots: [
    { date: '2026-07-05', critical: 2, high: 7, medium: 12, low: 3, new_count: 1, resolved_count: 0 },
    { date: '2026-07-06', critical: 2, high: 6, medium: 12, low: 3, new_count: 0, resolved_count: 1 },
  ],
};

function mockEndpoints({ overview = OVERVIEW } = {}) {
  api.get.mockImplementation((url) => {
    if (url.includes('/api/dashboard/overview/')) return Promise.resolve({ data: overview });
    if (url.includes('/api/security/dashboard/')) return Promise.resolve({ data: STATS });
    if (url.includes('/api/incidents/trend/')) return Promise.resolve({ data: TREND });
    if (url.includes('/api/security/vulnerabilities/trend/')) return Promise.resolve({ data: VULN_TREND });
    if (url.includes('/api/oncall/current/')) return Promise.resolve({ data: { analyst: null } });
    return Promise.reject(new Error(`unmocked url ${url}`));
  });
}

function renderPage({ selectedOrg = SELECTED_ORG, isStaff = false, viewAllOrgs = false } = {}) {
  return render(
    <MemoryRouter>
      <AuthContext.Provider
        value={{ user: { is_staff: isStaff }, isAuthenticated: true, isLoading: false, staffProfile: null }}
      >
        <OrgContext.Provider
          value={{ orgs: [SELECTED_ORG], selectedOrg, setSelectedOrg: vi.fn(), isLoading: false, viewAllOrgs, setViewAllOrgs: vi.fn() }}
        >
          <DashboardPage />
        </OrgContext.Provider>
      </AuthContext.Provider>
    </MemoryRouter>
  );
}

describe('DashboardPage', () => {
  beforeEach(() => vi.clearAllMocks());

  it('renders KPI tiles from the overview and security endpoints', async () => {
    mockEndpoints();
    renderPage();

    await waitFor(() => expect(screen.getByText('6')).toBeInTheDocument()); // open incidents
    expect(screen.getByText('9')).toBeInTheDocument(); // new alerts
    expect(screen.getByText('24')).toBeInTheDocument(); // 2+7+12+3 vulnerabilities
    expect(screen.getByText('4/5')).toBeInTheDocument(); // agents active/total
    expect(screen.getByText('42')).toBeInTheDocument(); // events 24h
  });

  it('links KPI tiles to their detail pages', async () => {
    mockEndpoints();
    renderPage();

    await waitFor(() => expect(screen.getByText('6')).toBeInTheDocument());
    expect(screen.getByRole('link', { name: /open incidents/i })).toHaveAttribute('href', '/incidents');
    expect(screen.getByRole('link', { name: /new alerts/i })).toHaveAttribute('href', '/alerts');
    expect(screen.getByRole('link', { name: /vulnerabilities/i })).toHaveAttribute('href', '/security/vulnerabilities');
  });

  it('renders severity and state breakdowns that drill into the incident list', async () => {
    mockEndpoints();
    renderPage();

    const severityList = await screen.findByRole('list', { name: /open incidents by severity/i });
    expect(severityList).toBeInTheDocument();
    const stateList = screen.getByRole('list', { name: /open incidents by state/i });
    expect(stateList).toBeInTheDocument();
    expect(within(severityList).getByRole('button', { name: /critical/i })).toBeEnabled();
  });

  it('shows recent incidents with links to their detail pages', async () => {
    mockEndpoints();
    renderPage();

    const link = await screen.findByRole('link', { name: /suspicious login burst/i });
    expect(link).toHaveAttribute('href', '/incidents/INC-2026-0007');
  });

  it('hides staff queues and staff services for regular users', async () => {
    mockEndpoints();
    renderPage();

    await waitFor(() => expect(screen.getByText('6')).toBeInTheDocument());
    expect(screen.queryByText(/needs triage/i)).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /threat hunting/i })).not.toBeInTheDocument();
  });

  it('shows staff queues with filtered links for staff', async () => {
    mockEndpoints({ overview: STAFF_OVERVIEW });
    renderPage({ isStaff: true });

    // Wait on count-bearing names so the assertions resolve against the
    // populated render, not the initial `value ?? '—'` placeholder (the counts
    // can land a commit after the labels on a slow/loaded runner).
    expect(await screen.findByRole('link', { name: /needs triage 2/i })).toHaveAttribute('href', '/incidents?state=new');
    expect(await screen.findByRole('link', { name: /unassigned 5/i })).toHaveAttribute('href', '/incidents?tab=unassigned');
    expect(await screen.findByRole('link', { name: /pending closure 0/i })).toHaveAttribute('href', '/incidents?state=pending_closure');
  });

  it('refetches trends when the range changes', async () => {
    mockEndpoints();
    renderPage();
    await waitFor(() => expect(screen.getByText('6')).toBeInTheDocument());

    const trendCalls = () =>
      api.get.mock.calls.filter(([url]) => url.includes('/api/incidents/trend/')).length;
    const before = trendCalls();
    await userEvent.click(screen.getByRole('button', { name: '7d' }));
    await waitFor(() => expect(trendCalls()).toBe(before + 1));
    expect(
      api.get.mock.calls
        .filter(([url]) => url.includes('/api/incidents/trend/'))
        .at(-1)[1].params.days,
    ).toBe(7);
  });

  it('refresh clears the security cache and refetches', async () => {
    mockEndpoints();
    api.post.mockResolvedValue({ data: { detail: 'Cache cleared.' } });
    renderPage();
    await waitFor(() => expect(screen.getByText('6')).toBeInTheDocument());

    const overviewCalls = () =>
      api.get.mock.calls.filter(([url]) => url.includes('/api/dashboard/overview/')).length;
    const before = overviewCalls();
    await userEvent.click(screen.getByRole('button', { name: /refresh/i }));
    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith('/api/security/dashboard/refresh/', { org: 'acme' }),
    );
    await waitFor(() => expect(overviewCalls()).toBe(before + 1));
  });

  it('shows an error banner when the overview fails but keeps the page up', async () => {
    api.get.mockImplementation((url) => {
      if (url.includes('/api/dashboard/overview/')) return Promise.reject(new Error('boom'));
      if (url.includes('/api/security/dashboard/')) return Promise.resolve({ data: STATS });
      return Promise.resolve({ data: { buckets: [], subjects: [], snapshots: [] } });
    });
    renderPage();

    await waitFor(() =>
      expect(screen.getByText(/failed to load dashboard data/i)).toBeInTheDocument(),
    );
    // Wazuh-backed tiles still render
    expect(screen.getByText('24')).toBeInTheDocument();
  });

  it('does not fetch when no org is selected', () => {
    mockEndpoints();
    renderPage({ selectedOrg: null });
    expect(api.get).not.toHaveBeenCalled();
    expect(screen.getByText(/no organisation selected/i)).toBeInTheDocument();
  });
});

describe('DashboardPage — All organisations view (staff)', () => {
  beforeEach(() => vi.clearAllMocks());

  it('aggregates DB panels across all orgs and never calls the per-org Wazuh endpoint', async () => {
    mockEndpoints({ overview: STAFF_OVERVIEW });
    renderPage({ isStaff: true, viewAllOrgs: true });

    // Overview + incident trend are requested with the all-orgs sentinel.
    await waitFor(() =>
      expect(api.get).toHaveBeenCalledWith('/api/dashboard/overview/', { params: { org: '__all__' } })
    );
    const urls = api.get.mock.calls.map(([u]) => u);
    // The Wazuh/OpenSearch dashboard endpoint is per-org only — never called here.
    expect(urls.some(u => u.includes('/api/security/dashboard/'))).toBe(false);

    // Header reflects the aggregate scope, Wazuh tiles show the placeholder.
    expect(screen.getByText('All organisations')).toBeInTheDocument();
    expect(screen.getAllByText('Per-org only').length).toBeGreaterThan(0);
  });
});
