import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import api from '../lib/axios';
import { useOrganization } from '../context/OrgContext';

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

export default function SecurityDashboard() {
  const { selectedOrg, isLoading: orgLoading } = useOrganization();
  const navigate = useNavigate();

  const [stats, setStats] = useState(null);
  const [agents, setAgents] = useState([]);
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState(null);

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

  if (orgLoading) {
    return <p className="text-sm text-muted-foreground">Loading…</p>;
  }

  if (!selectedOrg) {
    return <p className="text-sm text-muted-foreground">No organisation assigned.</p>;
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

          <div className="overflow-hidden rounded-lg border border-border bg-card">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border">
                  <th className="px-4 py-3 text-left font-medium text-muted-foreground">Agent</th>
                  <th className="px-4 py-3 text-left font-medium text-muted-foreground">OS</th>
                  <th className="px-4 py-3 text-left font-medium text-muted-foreground">IP</th>
                  <th className="px-4 py-3 text-left font-medium text-muted-foreground">Status</th>
                  <th className="px-4 py-3 text-left font-medium text-muted-foreground">Last Seen</th>
                </tr>
              </thead>
              <tbody>
                {agents.length === 0 ? (
                  <tr>
                    <td colSpan={5} className="px-4 py-8 text-center text-muted-foreground">
                      No agents enrolled.
                    </td>
                  </tr>
                ) : (
                  agents.map((agent) => (
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
