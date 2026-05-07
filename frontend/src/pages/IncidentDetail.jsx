import { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import api from '../lib/axios';

const SEVERITY_CLASSES = {
  critical: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400',
  high:     'bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-400',
  medium:   'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400',
  low:      'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400',
  info:     'bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-400',
};

const TLP_CLASSES = {
  white: 'bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-300',
  green: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400',
  amber: 'bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-400',
  red:   'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400',
};

function Badge({ label, value, badgeClass }) {
  return (
    <div className="flex flex-col gap-1">
      <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">{label}</span>
      <span className={`inline-flex w-fit items-center rounded-full px-2 py-0.5 text-xs font-medium ${badgeClass}`}>
        {value}
      </span>
    </div>
  );
}

function Field({ label, value }) {
  return (
    <div className="flex flex-col gap-1">
      <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">{label}</span>
      <span className="text-sm text-foreground">{value || '—'}</span>
    </div>
  );
}

export default function IncidentDetail() {
  const { incidentId } = useParams();
  const [incident, setIncident] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    async function fetch() {
      setLoading(true);
      setError(null);
      try {
        const res = await api.get(`/api/incidents/${incidentId}/`);
        setIncident(res.data);
      } catch (err) {
        setError(err.response?.status === 404 ? 'Incident not found.' : 'Failed to load incident.');
      } finally {
        setLoading(false);
      }
    }
    fetch();
  }, [incidentId]);

  if (loading) return <p className="text-sm text-muted-foreground p-6">Loading…</p>;
  if (error) return <p className="text-sm text-red-600 p-6">{error}</p>;
  if (!incident) return null;

  return (
    <div className="space-y-6 p-6">
      <div className="flex items-center gap-3">
        <Link to="/incidents" className="text-sm text-muted-foreground hover:text-foreground transition-colors">
          ← Incidents
        </Link>
      </div>

      <div className="rounded-lg border border-border bg-card p-6 space-y-6">
        <div>
          <p className="font-mono text-xs text-muted-foreground">{incident.display_id}</p>
          <h1 className="mt-1 text-2xl font-semibold text-foreground">{incident.title}</h1>
        </div>

        <div className="grid grid-cols-2 gap-6 sm:grid-cols-3 lg:grid-cols-4">
          <Badge
            label="Severity"
            value={incident.severity}
            badgeClass={SEVERITY_CLASSES[incident.severity] ?? ''}
          />
          <Badge
            label="TLP"
            value={`TLP:${incident.tlp.toUpperCase()}`}
            badgeClass={TLP_CLASSES[incident.tlp] ?? ''}
          />
          <Badge
            label="PAP"
            value={`PAP:${incident.pap.toUpperCase()}`}
            badgeClass={TLP_CLASSES[incident.pap] ?? ''}
          />
          <Field label="State" value={incident.state} />
          <Field label="Organisation" value={incident.org_slug} />
          <Field label="Source" value={incident.source_kind} />
          <Field label="Assignee" value={incident.assignee_username} />
          <Field label="Created By" value={incident.created_by_username} />
        </div>

        {incident.description && (
          <div className="flex flex-col gap-1">
            <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Description</span>
            <p className="text-sm text-foreground whitespace-pre-wrap">{incident.description}</p>
          </div>
        )}

        <div className="grid grid-cols-2 gap-4 text-xs text-muted-foreground">
          <span>Created: {incident.created_at ? new Date(incident.created_at).toLocaleString() : '—'}</span>
          <span>Updated: {incident.updated_at ? new Date(incident.updated_at).toLocaleString() : '—'}</span>
        </div>
      </div>
    </div>
  );
}
