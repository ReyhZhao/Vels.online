import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import api from '../lib/axios';
import { useOrganization } from '../context/OrgContext';

const SEVERITY_OPTIONS = ['critical', 'high', 'medium', 'low', 'info'];

const STATE_CLASSES = {
  new:         'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400',
  triaged:     'bg-purple-100 text-purple-800 dark:bg-purple-900/30 dark:text-purple-400',
  in_progress: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400',
  on_hold:     'bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-400',
  pending_closure: 'bg-teal-100 text-teal-800 dark:bg-teal-900/30 dark:text-teal-400',
  resolved:    'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400',
};

export default function PromoteToIncidentButton({ sourceKind, sourceRef, orgSlug: orgSlugProp }) {
  const navigate = useNavigate();
  const { selectedOrg } = useOrganization();
  const orgSlug = orgSlugProp || selectedOrg?.slug;

  const [prefetching, setPrefetching] = useState(false);
  const [open, setOpen] = useState(false);
  const [formData, setFormData] = useState(null);
  const [openIncidents, setOpenIncidents] = useState([]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  async function handleOpen() {
    setPrefetching(true);
    setError(null);
    try {
      const res = await api.post('/api/incidents/promote/', {
        source_kind: sourceKind,
        source_ref: sourceRef,
      });
      setFormData(res.data.form_payload);
      setOpenIncidents(res.data.open_incidents);
      setOpen(true);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to load promote form.');
    } finally {
      setPrefetching(false);
    }
  }

  async function handleSubmit(e) {
    e.preventDefault();
    if (!orgSlug) return;
    setSubmitting(true);
    setError(null);
    try {
      const res = await api.post('/api/incidents/promote/', {
        ...formData,
        commit: true,
        org: orgSlug,
      });
      setOpen(false);
      navigate(`/incidents/${res.data.display_id}`);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to create incident.');
    } finally {
      setSubmitting(false);
    }
  }

  function handleClose() {
    setOpen(false);
    setFormData(null);
    setOpenIncidents([]);
    setError(null);
  }

  return (
    <>
      <button
        onClick={handleOpen}
        disabled={prefetching}
        className="rounded-md border border-border bg-background px-3 py-1.5 text-sm font-medium text-foreground hover:bg-accent disabled:opacity-50 transition-colors"
      >
        {prefetching ? 'Loading…' : 'Promote to incident'}
      </button>

      {error && !open && (
        <p className="text-sm text-red-600 mt-1">{error}</p>
      )}

      {open && formData && (
        <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/50 pt-12 pb-12">
          <div className="w-full max-w-lg rounded-lg border border-border bg-card p-6 shadow-lg space-y-5 mx-4">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-semibold text-foreground">Create Incident</h2>
              <button
                onClick={handleClose}
                className="text-sm text-muted-foreground hover:text-foreground"
              >
                ✕
              </button>
            </div>

            {openIncidents.length > 0 && (
              <div className="rounded-md border border-amber-300 bg-amber-50 dark:bg-amber-900/20 dark:border-amber-700 p-3 space-y-2">
                <p className="text-xs font-semibold uppercase tracking-wider text-amber-800 dark:text-amber-400">
                  {openIncidents.length === 1
                    ? 'Existing open incident for this source'
                    : `${openIncidents.length} existing open incidents for this source`}
                </p>
                {openIncidents.map(inc => (
                  <a
                    key={inc.id}
                    href={`/incidents/${inc.display_id}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="block text-sm text-blue-600 dark:text-blue-400 hover:underline"
                  >
                    {inc.display_id} — {inc.title}
                    <span className={`ml-2 inline-flex items-center rounded-full px-1.5 py-0.5 text-xs font-medium ${STATE_CLASSES[inc.state] ?? ''}`}>
                      {inc.state}
                    </span>
                  </a>
                ))}
                <p className="text-xs text-muted-foreground">You can still create a parallel incident below.</p>
              </div>
            )}

            <form onSubmit={handleSubmit} className="space-y-3">
              <div className="space-y-1">
                <label className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Title</label>
                <input
                  value={formData.title}
                  onChange={e => setFormData(d => ({ ...d, title: e.target.value }))}
                  required
                  className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                />
              </div>

              <div className="space-y-1">
                <label className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Severity</label>
                <select
                  value={formData.severity}
                  onChange={e => setFormData(d => ({ ...d, severity: e.target.value }))}
                  aria-label="Severity"
                  className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
                >
                  {SEVERITY_OPTIONS.map(s => (
                    <option key={s} value={s}>{s}</option>
                  ))}
                </select>
              </div>

              <div className="space-y-1">
                <label className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Description</label>
                <textarea
                  value={formData.description}
                  onChange={e => setFormData(d => ({ ...d, description: e.target.value }))}
                  rows={3}
                  className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring resize-none"
                />
              </div>

              {error && <p className="text-sm text-red-600">{error}</p>}

              <div className="flex justify-end gap-3 pt-1">
                <button
                  type="button"
                  onClick={handleClose}
                  disabled={submitting}
                  className="rounded-md border border-border bg-background px-4 py-2 text-sm font-medium text-foreground hover:bg-accent disabled:opacity-50"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={submitting || !formData.title?.trim()}
                  className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-colors"
                >
                  {submitting ? 'Creating…' : 'Create incident'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </>
  );
}
