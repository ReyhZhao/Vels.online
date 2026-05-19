import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { Shield, Globe } from 'lucide-react';
import api from '../lib/axios';
import { useOrganization } from '../context/OrgContext';

function ServiceCard({ icon: Icon, title, description, to }) {
  return (
    <Link
      to={to}
      className="flex flex-col gap-3 rounded-lg border border-border bg-card p-5 transition-colors hover:bg-accent"
    >
      <Icon className="h-6 w-6 text-muted-foreground" />
      <div>
        <p className="text-sm font-semibold text-foreground">{title}</p>
        {description && (
          <p className="mt-0.5 text-xs text-muted-foreground">{description}</p>
        )}
      </div>
    </Link>
  );
}


function SummaryWidget({ label, value, isLoading }) {
  return (
    <div className="rounded-lg border border-border bg-card p-4">
      <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">{label}</p>
      <p className="mt-1 text-3xl font-bold text-foreground">
        {isLoading ? (
          <span className="text-base text-muted-foreground" aria-label="loading">Loading…</span>
        ) : (
          value ?? '—'
        )}
      </p>
    </div>
  );
}

export default function DashboardPage() {
  const orgContext = useOrganization();
  const selectedOrg = orgContext?.selectedOrg ?? null;

  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);

  const [routeCount, setRouteCount] = useState(null);
  const [routesLoading, setRoutesLoading] = useState(false);

  useEffect(() => {
    if (!selectedOrg) return;
    setLoading(true);
    setError(false);
    api
      .get(`/api/security/dashboard/?org=${selectedOrg.slug}`)
      .then((res) => setStats(res.data))
      .catch(() => setError(true))
      .finally(() => setLoading(false));
  }, [selectedOrg]);

  useEffect(() => {
    if (!selectedOrg) return;
    setRoutesLoading(true);
    api
      .get('/api/ingress/routes/', { params: { org: selectedOrg.slug } })
      .then((res) => setRouteCount(res.data.length))
      .catch(() => setRouteCount(null))
      .finally(() => setRoutesLoading(false));
  }, [selectedOrg]);

  const vulnCount =
    stats?.vulnerabilities != null
      ? Object.values(stats.vulnerabilities).reduce((a, b) => a + b, 0)
      : null;

  return (
    <div className="space-y-8 p-6">
      <h1 className="text-2xl font-semibold text-foreground">Dashboard</h1>

      <section aria-label="Services">
        <h2 className="mb-4 text-sm font-semibold uppercase tracking-wider text-muted-foreground">
          Services
        </h2>
        <div
          className="grid gap-4"
          style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))' }}
        >
          <ServiceCard
            icon={Shield}
            title="Security"
            description="Vulnerability and agent monitoring"
            to="/security"
          />
          <ServiceCard
            icon={Globe}
            title="Ingress"
            description="Reverse proxy and WAF routes"
            to="/routes"
          />
        </div>
      </section>

      <section aria-label="Summary">
        <h2 className="mb-4 text-sm font-semibold uppercase tracking-wider text-muted-foreground">
          Summary
        </h2>
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
          <SummaryWidget
            label="Vulnerabilities"
            value={error ? '—' : vulnCount}
            isLoading={loading}
          />
          <SummaryWidget
            label="Agents"
            value={error ? '—' : stats?.agent_count ?? null}
            isLoading={loading}
          />
          <SummaryWidget
            label="Routes"
            value={routeCount}
            isLoading={routesLoading}
          />
        </div>
      </section>

    </div>
  );
}
