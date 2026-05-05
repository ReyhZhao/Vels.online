import { useState, useEffect, useCallback } from 'react';
import api from '../lib/axios';
import { useOrganization } from '../context/OrgContext';

const SEVERITY_CLASSES = {
  critical: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400',
  high:     'bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-400',
  medium:   'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400',
  low:      'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400',
};

const STATUS_CLASSES = {
  open:          'bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300',
  in_progress:   'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400',
  resolved:      'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400',
  accepted_risk: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400',
};

const STATUS_LABELS = {
  open:          'Open',
  in_progress:   'In Progress',
  resolved:      'Resolved',
  accepted_risk: 'Accepted Risk',
};

function SeverityBadge({ severity }) {
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${SEVERITY_CLASSES[severity] ?? SEVERITY_CLASSES.low}`}>
      {severity}
    </span>
  );
}

function StatusBadge({ status }) {
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_CLASSES[status] ?? STATUS_CLASSES.open}`}>
      {STATUS_LABELS[status] ?? status}
    </span>
  );
}

function CveItem({ item }) {
  const [open, setOpen] = useState(false);

  return (
    <div className="rounded-lg border border-border bg-card overflow-hidden">
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-start gap-4 px-5 py-4 text-left hover:bg-accent/40 transition-colors"
      >
        <div className="flex-1 min-w-0">
          <div className="flex flex-wrap items-center gap-2 mb-1">
            <span className="font-mono text-sm font-semibold text-foreground">{item.cve_id}</span>
            <SeverityBadge severity={item.severity} />
            <StatusBadge status={item.status} />
          </div>
          <p className="text-sm text-muted-foreground line-clamp-2">{item.description || 'No description available.'}</p>
        </div>
        <div className="shrink-0 text-right text-xs text-muted-foreground space-y-1">
          <div>CVSS <span className="font-semibold text-foreground">{item.cvss_score?.toFixed(1) ?? '—'}</span></div>
          <div>Agents <span className="font-semibold text-foreground">{item.affected_agent_count}</span></div>
          <div>Score <span className="font-semibold text-foreground">{item.impact_score}</span></div>
        </div>
      </button>

      {open && (
        <div className="border-t border-border px-5 py-4 space-y-4 bg-card">
          {item.description && (
            <div>
              <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-1">Description</p>
              <p className="text-sm text-foreground">{item.description}</p>
            </div>
          )}

          {item.references?.length > 0 && (
            <div>
              <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-1">References</p>
              <ul className="space-y-0.5">
                {item.references.map((ref, i) => (
                  <li key={i}>
                    <a
                      href={ref}
                      target="_blank"
                      rel="noreferrer"
                      className="text-sm text-blue-600 dark:text-blue-400 hover:underline break-all"
                    >
                      {ref}
                    </a>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {item.affected_agents?.length > 0 && (
            <div>
              <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-2">
                Affected Agents ({item.affected_agents.length})
              </p>
              <div className="overflow-x-auto rounded-md border border-border">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-b border-border">
                      <th className="px-3 py-2 text-left font-medium text-muted-foreground">Hostname</th>
                      <th className="px-3 py-2 text-left font-medium text-muted-foreground">Package</th>
                      <th className="px-3 py-2 text-left font-medium text-muted-foreground">Installed Version</th>
                      <th className="px-3 py-2 text-left font-medium text-muted-foreground">Fixed Version</th>
                    </tr>
                  </thead>
                  <tbody>
                    {item.affected_agents.map((agent, i) => (
                      <tr key={i} className="border-b border-border last:border-0">
                        <td className="px-3 py-2 font-mono text-foreground">{agent.hostname || agent.agent_id}</td>
                        <td className="px-3 py-2 text-muted-foreground">{agent.package_name || '—'}</td>
                        <td className="px-3 py-2 text-muted-foreground">{agent.current_version || '—'}</td>
                        <td className="px-3 py-2 text-muted-foreground">{agent.fixed_version || '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {item.note && (
            <div>
              <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-1">Note</p>
              <p className="text-sm text-foreground">{item.note}</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default function WorkPackagePage() {
  const { selectedOrg, isLoading: orgLoading } = useOrganization();
  const [packageData, setPackageData] = useState(undefined);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const fetchPackage = useCallback(async (slug) => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.get(`/api/security/work-package/?org=${slug}`);
      setPackageData(res.data.package);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to load work package.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (selectedOrg) fetchPackage(selectedOrg.slug);
  }, [selectedOrg, fetchPackage]);

  if (orgLoading) return <p className="text-sm text-muted-foreground p-6">Loading…</p>;
  if (!selectedOrg) return <p className="text-sm text-muted-foreground p-6">No organisation assigned.</p>;

  return (
    <div className="space-y-6 p-6">
      <div>
        <h1 className="text-2xl font-semibold text-foreground">Work Package — {selectedOrg.name}</h1>
        {packageData && (
          <p className="mt-1 text-sm text-muted-foreground">
            Generated {new Date(packageData.created_at).toLocaleDateString(undefined, {
              weekday: 'long', year: 'numeric', month: 'long', day: 'numeric',
            })}
            {packageData.generated_by ? ` by ${packageData.generated_by}` : ' automatically'}
          </p>
        )}
      </div>

      {error && <p className="text-sm text-red-600">{error}</p>}

      {loading && (
        <p className="text-sm text-muted-foreground">Loading…</p>
      )}

      {!loading && packageData === null && (
        <div className="flex flex-col items-center justify-center rounded-lg border border-dashed border-border bg-card py-20 text-center">
          <p className="text-lg font-medium text-foreground">No active work package</p>
          <p className="mt-1 text-sm text-muted-foreground">
            A work package will be generated automatically each Monday, or ask a staff member to generate one now.
          </p>
        </div>
      )}

      {!loading && packageData && (
        <div className="space-y-3">
          <p className="text-sm text-muted-foreground">
            {packageData.items.length} prioritised {packageData.items.length === 1 ? 'vulnerability' : 'vulnerabilities'}
          </p>
          {packageData.items.map(item => (
            <CveItem key={item.id} item={item} />
          ))}
        </div>
      )}
    </div>
  );
}
