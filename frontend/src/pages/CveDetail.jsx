import { useState, useEffect } from 'react';
import { useParams, useNavigate, useSearchParams } from 'react-router-dom';
import api from '../lib/axios';
import { useOrganization } from '../context/OrgContext';

const SEVERITY_CLASSES = {
  critical: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400',
  high:     'bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-400',
  medium:   'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400',
  low:      'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400',
};

function SeverityBadge({ severity }) {
  return (
    <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-sm font-medium ${SEVERITY_CLASSES[severity] ?? SEVERITY_CLASSES.low}`}>
      {severity}
    </span>
  );
}

function Field({ label, children }) {
  return (
    <div className="flex gap-2 text-sm">
      <dt className="w-36 shrink-0 text-muted-foreground">{label}</dt>
      <dd className="text-foreground">{children}</dd>
    </div>
  );
}

export default function CveDetail() {
  const { cveId } = useParams();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { selectedOrg, isLoading: orgLoading } = useOrganization();

  const orgSlug = searchParams.get('org') || selectedOrg?.slug || '';

  const [detail, setDetail] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!orgSlug || !cveId) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    api.get(`/api/security/vulnerabilities/${encodeURIComponent(cveId)}/?org=${orgSlug}`)
      .then(res => { if (!cancelled) { setDetail(res.data); setLoading(false); } })
      .catch(err => {
        if (!cancelled) {
          setError(err.response?.status === 404 ? 'CVE not found in this organisation.' : 'Failed to load CVE details.');
          setLoading(false);
        }
      });
    return () => { cancelled = true; };
  }, [cveId, orgSlug]);

  if (orgLoading || loading) {
    return <p className="text-sm text-muted-foreground">Loading…</p>;
  }

  if (error) {
    return <p className="text-sm text-red-600">{error}</p>;
  }

  if (!detail) return null;

  return (
    <div className="space-y-6 max-w-4xl p-6">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold font-mono text-foreground">{detail.cve}</h1>
          <div className="flex items-center gap-3 mt-2">
            <SeverityBadge severity={detail.severity} />
            {detail.cvss_score != null && (
              <span className="text-sm text-muted-foreground">CVSS {detail.cvss_score.toFixed(1)}</span>
            )}
            {detail.published && (
              <span className="text-sm text-muted-foreground">
                Published {new Date(detail.published).toLocaleDateString()}
              </span>
            )}
          </div>
        </div>
        <button
          onClick={() => navigate(-1)}
          className="shrink-0 rounded-md border border-border px-3 py-1.5 text-sm text-muted-foreground hover:text-foreground hover:bg-accent transition-colors"
        >
          ← Back
        </button>
      </div>

      {/* CVE details */}
      <div className="rounded-lg border border-border bg-card p-5 space-y-3">
        <dl className="space-y-2">
          <Field label="Package">{detail.package || '—'}</Field>
          {detail.cvss_score != null && <Field label="CVSS Score">{detail.cvss_score.toFixed(1)}</Field>}
          <Field label="Affected agents">{detail.affected_agents?.length ?? 0}</Field>
        </dl>

        {detail.description && (
          <div className="pt-3 border-t border-border">
            <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground mb-1">Description</p>
            <p className="text-sm text-foreground leading-relaxed">{detail.description}</p>
          </div>
        )}

        {detail.references?.length > 0 && (
          <div className="pt-3 border-t border-border">
            <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground mb-2">References</p>
            <ul className="space-y-1">
              {detail.references.map((ref, i) => (
                <li key={i}>
                  <a
                    href={ref}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-sm text-blue-600 dark:text-blue-400 hover:underline break-all"
                  >
                    {ref}
                  </a>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>

      {/* Affected agents table */}
      <div>
        <h2 className="text-base font-semibold text-foreground mb-3">
          Affected Systems ({detail.affected_agents?.length ?? 0})
        </h2>
        <div className="overflow-hidden rounded-lg border border-border bg-card">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border">
                <th className="px-4 py-3 text-left font-medium text-muted-foreground">Agent</th>
                <th className="px-4 py-3 text-left font-medium text-muted-foreground">Installed Version</th>
                <th className="px-4 py-3 text-left font-medium text-muted-foreground">Fixed Version</th>
                <th className="px-4 py-3 text-left font-medium text-muted-foreground">Fix Available</th>
              </tr>
            </thead>
            <tbody>
              {detail.affected_agents?.length === 0 ? (
                <tr>
                  <td colSpan={4} className="px-4 py-8 text-center text-muted-foreground">No affected agents.</td>
                </tr>
              ) : (
                detail.affected_agents?.map(agent => (
                  <tr
                    key={agent.agent_id}
                    onClick={() => navigate(`/security/agents/${agent.agent_id}`)}
                    className="cursor-pointer border-b border-border last:border-0 hover:bg-accent/50 transition-colors"
                  >
                    <td className="px-4 py-3 font-medium text-foreground">{agent.agent_name || agent.agent_id}</td>
                    <td className="px-4 py-3 font-mono text-xs text-muted-foreground">{agent.installed_version || '—'}</td>
                    <td className="px-4 py-3 font-mono text-xs text-muted-foreground">{agent.fixed_version || '—'}</td>
                    <td className="px-4 py-3">
                      {agent.fix_available ? (
                        <span className="text-green-600 dark:text-green-400 text-xs font-medium">Yes</span>
                      ) : (
                        <span className="text-muted-foreground text-xs">No</span>
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
