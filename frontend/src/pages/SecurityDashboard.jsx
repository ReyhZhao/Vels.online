import { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import api from '../lib/axios';
import { useOrganization } from '../context/OrgContext';
import { useAuth } from '../context/AuthContext';

function StatCard({ label, value, colorClass }) {
  return (
    <div className="rounded-lg border border-border bg-card p-4">
      <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">{label}</p>
      <p className={`mt-1 text-3xl font-bold ${colorClass ?? 'text-foreground'}`}>
        {value ?? '—'}
      </p>
    </div>
  );
}

function StatusBadge({ status }) {
  const isActive = status === 'active';
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${
        isActive
          ? 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400'
          : 'bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400'
      }`}
    >
      {status}
    </span>
  );
}

// ── Wazuh run modal (security overview context) ───────────────────────────────

function WazuhOverviewRunModal({ agent, response, orgSlug, onClose, onSuccess }) {
  const [args, setArgs] = useState(response.default_args || '');
  const [timeout, setTimeout_] = useState(String(response.timeout ?? 0));
  const [incidentId, setIncidentId] = useState('');
  const [confirmText, setConfirmText] = useState('');
  const [running, setRunning] = useState(false);
  const [error, setError] = useState(null);
  const [toast, setToast] = useState(null);

  const canDispatch = !running &&
    (!response.requires_confirmation || confirmText === response.command);

  async function handleDispatch() {
    setRunning(true);
    setError(null);
    try {
      const payload = {
        org: orgSlug,
        wazuh_response: response.id,
        args: args.trim(),
        timeout: Number(timeout) || 0,
      };
      if (incidentId.trim()) payload.incident = incidentId.trim();
      const res = await api.post(`/api/security/agents/${agent.id}/respond/`, payload);
      onSuccess(res.data);
      onClose();
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to dispatch.');
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="flex w-full max-w-md flex-col rounded-lg border border-border bg-card shadow-xl">
        <div className="flex items-center justify-between border-b border-border px-6 py-4">
          <div>
            <h3 className="text-base font-semibold text-foreground">{response.name}</h3>
            <p className="text-xs text-muted-foreground">{agent.name}</p>
          </div>
          <button onClick={onClose} className="rounded-md p-1 text-muted-foreground hover:text-foreground hover:bg-accent">✕</button>
        </div>

        <div className="space-y-4 px-6 py-4">
          <div>
            <label className="mb-1 block text-xs font-medium text-muted-foreground">Command</label>
            <code className="text-xs font-mono text-foreground">{response.command}</code>
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-muted-foreground">Arguments</label>
            <input
              value={args}
              onChange={e => setArgs(e.target.value)}
              className="w-full rounded border border-border bg-background px-2 py-1 text-sm font-mono"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-muted-foreground">Timeout (s, 0 = none)</label>
            <input
              type="number"
              value={timeout}
              onChange={e => setTimeout_(e.target.value)}
              min="0"
              className="w-24 rounded border border-border bg-background px-2 py-1 text-sm"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-muted-foreground">
              Link to incident <span className="font-normal text-muted-foreground/70">(optional — display ID)</span>
            </label>
            <input
              value={incidentId}
              onChange={e => setIncidentId(e.target.value)}
              placeholder="INC-2024-0001"
              className="w-full rounded border border-border bg-background px-2 py-1 text-sm font-mono"
            />
          </div>
          {response.requires_confirmation && (
            <div>
              <label className="mb-1 block text-xs font-medium text-muted-foreground">
                Type the command to confirm: <code className="font-mono">{response.command}</code>
              </label>
              <input
                value={confirmText}
                onChange={e => setConfirmText(e.target.value)}
                placeholder={response.command}
                className="w-full rounded border border-border bg-background px-2 py-1 text-sm font-mono"
              />
            </div>
          )}
          {error && <p className="text-sm text-red-600">{error}</p>}
        </div>

        <div className="flex justify-end gap-2 border-t border-border px-6 py-4">
          <button onClick={onClose} className="rounded-md border border-border bg-background px-4 py-2 text-sm font-medium text-foreground hover:bg-accent">
            Cancel
          </button>
          <button
            onClick={handleDispatch}
            disabled={!canDispatch}
            className="rounded-md bg-orange-600 px-4 py-2 text-sm font-semibold text-white hover:bg-orange-700 disabled:opacity-50"
          >
            {running ? 'Dispatching…' : 'Dispatch'}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Agent kebab menu ──────────────────────────────────────────────────────────

function AgentKebab({ agent, responses, orgSlug, onResponseSuccess }) {
  const [open, setOpen] = useState(false);
  const [selectedResponse, setSelectedResponse] = useState(null);
  const menuRef = useRef(null);

  useEffect(() => {
    if (!open) return;
    function handleClick(e) {
      if (menuRef.current && !menuRef.current.contains(e.target)) setOpen(false);
    }
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, [open]);

  const agentPlatform = (agent.os_platform || '').toLowerCase();
  const compatible = responses.filter(r =>
    r.available_in_security_overview &&
    (r.platforms.length === 0 || !agentPlatform || r.platforms.includes(agentPlatform))
  );

  if (compatible.length === 0) return null;

  return (
    <div className="relative" ref={menuRef} onClick={e => e.stopPropagation()}>
      <button
        onClick={() => setOpen(o => !o)}
        className="rounded p-1 text-muted-foreground hover:text-foreground hover:bg-accent transition-colors"
        aria-label="Actions"
      >
        ⋮
      </button>
      {open && (
        <div className="absolute right-0 z-20 mt-1 w-48 rounded-md border border-border bg-card shadow-lg">
          {compatible.map(r => (
            <button
              key={r.id}
              onClick={() => { setSelectedResponse(r); setOpen(false); }}
              className="w-full px-3 py-2 text-left text-sm text-foreground hover:bg-accent transition-colors first:rounded-t-md last:rounded-b-md"
            >
              {r.name}
            </button>
          ))}
        </div>
      )}
      {selectedResponse && (
        <WazuhOverviewRunModal
          agent={agent}
          response={selectedResponse}
          orgSlug={orgSlug}
          onClose={() => setSelectedResponse(null)}
          onSuccess={(result) => {
            setSelectedResponse(null);
            onResponseSuccess(result);
          }}
        />
      )}
    </div>
  );
}

// ── SecurityDashboard ─────────────────────────────────────────────────────────

export default function SecurityDashboard() {
  const { selectedOrg, isLoading: orgLoading } = useOrganization();
  const { user } = useAuth();
  const navigate = useNavigate();

  const [stats, setStats] = useState(null);
  const [agents, setAgents] = useState([]);
  const [wazuhResponses, setWazuhResponses] = useState([]);
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState(null);
  const [toast, setToast] = useState(null);

  // Embedded agents collection affordances (issue #584).
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [sortKey, setSortKey] = useState('name');
  const [sortOrder, setSortOrder] = useState('asc');

  const fetchData = useCallback(async (slug) => {
    setLoading(true);
    setError(null);
    try {
      const [dashRes, agentsRes] = await Promise.all([
        api.get(`/api/security/dashboard/?org=${slug}`),
        api.get(`/api/security/agents/?org=${slug}`),
      ]);
      setStats(dashRes.data);
      setAgents(agentsRes.data);
    } catch (err) {
      const detail = err.response?.data?.detail;
      setError(detail ? `Failed to load dashboard data: ${detail}` : 'Failed to load dashboard data.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (selectedOrg) fetchData(selectedOrg.slug);
  }, [selectedOrg, fetchData]);

  useEffect(() => {
    if (!user?.is_staff) return;
    api.get('/api/wazuh-responses/').then(res => setWazuhResponses(res.data)).catch(() => {});
  }, [user]);

  async function handleRefresh() {
    if (!selectedOrg || refreshing) return;
    setRefreshing(true);
    try {
      await api.post('/api/security/dashboard/refresh/', { org: selectedOrg.slug });
      await fetchData(selectedOrg.slug);
    } finally {
      setRefreshing(false);
    }
  }

  function handleResponseSuccess(result) {
    setToast(result.incident
      ? `Dispatched ${result.wazuh_response_name} — linked to incident ${result.incident}`
      : `Dispatched ${result.wazuh_response_name}`
    );
    setTimeout(() => setToast(null), 5000);
  }

  if (orgLoading) {
    return <p className="text-sm text-muted-foreground">Loading…</p>;
  }

  if (!selectedOrg) {
    return <p className="text-sm text-muted-foreground">No organisation assigned.</p>;
  }

  const isStaff = user?.is_staff ?? false;
  const hasWazuhResponses = wazuhResponses.length > 0;
  const showActions = isStaff && hasWazuhResponses;

  const AGENT_SORT = {
    name:      { label: 'Agent',     defaultOrder: 'asc' },
    status:    { label: 'Status',    defaultOrder: 'asc' },
    last_seen: { label: 'Last Seen', defaultOrder: 'desc' },
  };

  function setSort(key) {
    if (sortKey === key) {
      setSortOrder(o => (o === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortKey(key);
      setSortOrder(AGENT_SORT[key]?.defaultOrder ?? 'asc');
    }
  }

  const visibleAgents = useMemo(() => {
    const q = search.trim().toLowerCase();
    let rows = agents.filter(a => {
      if (statusFilter !== 'all' && a.status !== statusFilter) return false;
      if (!q) return true;
      return (
        (a.name || '').toLowerCase().includes(q) ||
        (a.ip || '').toLowerCase().includes(q) ||
        (a.os || '').toLowerCase().includes(q)
      );
    });
    const dir = sortOrder === 'asc' ? 1 : -1;
    rows = [...rows].sort((a, b) => {
      if (sortKey === 'last_seen') {
        return ((a.last_seen ? new Date(a.last_seen).getTime() : 0) - (b.last_seen ? new Date(b.last_seen).getTime() : 0)) * dir;
      }
      return (a[sortKey] || '').toString().toLowerCase()
        .localeCompare((b[sortKey] || '').toString().toLowerCase()) * dir;
    });
    return rows;
  }, [agents, search, statusFilter, sortKey, sortOrder]);

  function AgentSortHeader({ field }) {
    return (
      <th className="px-4 py-3 text-left font-medium text-muted-foreground">
        <button
          onClick={() => setSort(field)}
          className="flex items-center gap-1 hover:text-foreground transition-colors"
          aria-label={`Sort by ${AGENT_SORT[field].label}`}
        >
          {AGENT_SORT[field].label}
          {sortKey === field && <span aria-hidden="true">{sortOrder === 'asc' ? '▲' : '▼'}</span>}
        </button>
      </th>
    );
  }

  return (
    <div className="space-y-6 p-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold text-foreground">{selectedOrg.name}</h1>
        <button
          onClick={handleRefresh}
          disabled={refreshing || loading}
          className="rounded-md border border-border bg-background px-3 py-1.5 text-sm font-medium text-foreground shadow-sm hover:bg-accent disabled:opacity-50"
        >
          {refreshing ? 'Refreshing…' : 'Refresh'}
        </button>
      </div>

      {error && <p className="text-sm text-red-600">{error}</p>}

      {toast && (
        <div className="rounded-md bg-green-100 px-4 py-3 text-sm text-green-800 dark:bg-green-900/30 dark:text-green-400">
          {toast}
        </div>
      )}

      {loading ? (
        <p className="text-sm text-muted-foreground">Loading…</p>
      ) : (
        <>
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
            <StatCard label="Total Agents" value={stats?.agent_count} />
            <StatCard label="Active" value={stats?.active_count} />
            <StatCard
              label="Critical"
              value={stats?.vulnerabilities?.critical}
              colorClass="text-red-600 dark:text-red-400"
            />
            <StatCard
              label="High"
              value={stats?.vulnerabilities?.high}
              colorClass="text-orange-600 dark:text-orange-400"
            />
            <StatCard
              label="Medium"
              value={stats?.vulnerabilities?.medium}
              colorClass="text-yellow-600 dark:text-yellow-400"
            />
            <StatCard label="Events (24h)" value={stats?.events_24h} />
          </div>

          {agents.length > 0 && (
            <div className="flex flex-wrap gap-2 items-center">
              <input
                type="search"
                placeholder="Search agents…"
                value={search}
                onChange={e => setSearch(e.target.value)}
                aria-label="Search agents"
                className="rounded-md border border-border bg-background px-3 py-1.5 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring w-52"
              />
              <select
                value={statusFilter}
                onChange={e => setStatusFilter(e.target.value)}
                aria-label="Status filter"
                className="rounded-md border border-border bg-background px-2 py-1.5 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
              >
                <option value="all">All statuses</option>
                <option value="active">Active</option>
                <option value="disconnected">Disconnected</option>
              </select>
            </div>
          )}

          {/* Mobile card list */}
          <div className="sm:hidden space-y-2">
            {agents.length === 0 ? (
              <p className="py-8 text-center text-sm text-muted-foreground">No agents enrolled.</p>
            ) : visibleAgents.length === 0 ? (
              <p className="py-8 text-center text-sm text-muted-foreground">No agents match your filters.</p>
            ) : visibleAgents.map((agent) => (
              <div key={agent.id} className="rounded-lg border border-border bg-card px-4 py-3 space-y-2">
                <div className="flex items-start justify-between gap-2">
                  <button
                    type="button"
                    onClick={() => navigate(`/security/agents/${agent.id}`)}
                    className="text-left font-medium text-foreground hover:text-primary hover:underline leading-snug"
                  >
                    {agent.name}
                  </button>
                  <div className="flex items-center gap-1">
                    <StatusBadge status={agent.status} />
                    {showActions && agent.status === 'active' && (
                      <AgentKebab
                        agent={agent}
                        responses={wazuhResponses}
                        orgSlug={selectedOrg.slug}
                        onResponseSuccess={handleResponseSuccess}
                      />
                    )}
                  </div>
                </div>
                <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
                  <span>{agent.os || '—'}</span>
                  <span>{agent.ip || '—'}</span>
                  <span>Last seen: {agent.last_seen ? new Date(agent.last_seen).toLocaleString() : '—'}</span>
                </div>
              </div>
            ))}
          </div>

          {/* Desktop table */}
          <div className="hidden sm:block overflow-hidden rounded-lg border border-border bg-card">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border">
                  <AgentSortHeader field="name" />
                  <th className="px-4 py-3 text-left font-medium text-muted-foreground">OS</th>
                  <th className="px-4 py-3 text-left font-medium text-muted-foreground">IP</th>
                  <AgentSortHeader field="status" />
                  <AgentSortHeader field="last_seen" />
                  {showActions && <th className="px-4 py-3 w-12" />}
                </tr>
              </thead>
              <tbody>
                {agents.length === 0 ? (
                  <tr>
                    <td colSpan={showActions ? 6 : 5} className="px-4 py-8 text-center text-muted-foreground">
                      No agents enrolled.
                    </td>
                  </tr>
                ) : visibleAgents.length === 0 ? (
                  <tr>
                    <td colSpan={showActions ? 6 : 5} className="px-4 py-8 text-center text-muted-foreground">
                      No agents match your filters.
                    </td>
                  </tr>
                ) : (
                  visibleAgents.map((agent) => (
                    <tr
                      key={agent.id}
                      onClick={() => navigate(`/security/agents/${agent.id}`)}
                      className="cursor-pointer border-b border-border last:border-0 hover:bg-accent/50 transition-colors"
                    >
                      <td className="px-4 py-3 font-medium text-foreground">{agent.name}</td>
                      <td className="px-4 py-3 text-muted-foreground">{agent.os || '—'}</td>
                      <td className="px-4 py-3 text-muted-foreground">{agent.ip || '—'}</td>
                      <td className="px-4 py-3">
                        <StatusBadge status={agent.status} />
                      </td>
                      <td className="px-4 py-3 text-muted-foreground">
                        {agent.last_seen ? new Date(agent.last_seen).toLocaleString() : '—'}
                      </td>
                      {showActions && (
                        <td className="px-4 py-3" onClick={e => e.stopPropagation()}>
                          {agent.status === 'active' && (
                            <AgentKebab
                              agent={agent}
                              responses={wazuhResponses}
                              orgSlug={selectedOrg.slug}
                              onResponseSuccess={handleResponseSuccess}
                            />
                          )}
                        </td>
                      )}
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}
