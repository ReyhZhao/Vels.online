import { useState, useEffect } from 'react';
import api from '../lib/axios';

const SEVERITY_OPTIONS = ['critical', 'high', 'medium', 'low', 'info'];
const TLP_PAP_OPTIONS = ['white', 'green', 'amber', 'red'];

export default function BulkPromoteModal({ open, alertIds, orgSlug, onClose, onSuccess }) {
  const [phase, setPhase] = useState('loading'); // loading | form | submitting
  const [form, setForm] = useState({ title: '', description: '', severity: 'medium', tlp: 'amber', pap: 'amber' });
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!open || alertIds.length === 0) return;
    setPhase('loading');
    setError(null);

    api.post('/api/alerts/bulk-promote/preview/', { alerts: alertIds, org: orgSlug })
      .then(r => {
        setForm({
          title: r.data.title ?? '',
          description: r.data.description ?? '',
          severity: r.data.severity ?? 'medium',
          tlp: r.data.tlp ?? 'amber',
          pap: r.data.pap ?? 'amber',
        });
        setPhase('form');
      })
      .catch(err => {
        setError(err.response?.data?.detail || 'Could not load preview.');
        setPhase('form');
      });
  }, [open, alertIds, orgSlug]);

  const handleClose = () => {
    setError(null);
    onClose();
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setPhase('submitting');
    setError(null);
    try {
      const resp = await api.post('/api/alerts/bulk-promote/', {
        alerts: alertIds,
        org: orgSlug,
        ...form,
      });
      handleClose();
      onSuccess(resp.data.display_id);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to create incident.');
      setPhase('form');
    }
  };

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/50 pt-12 pb-12">
      <div className="w-full max-w-lg rounded-lg border border-border bg-card p-6 shadow-lg space-y-5 mx-4">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-lg font-semibold text-foreground">Create Incident</h2>
            <p className="text-xs text-muted-foreground mt-0.5">
              {alertIds.length} alert{alertIds.length !== 1 ? 's' : ''} will be linked
            </p>
          </div>
          <button onClick={handleClose} aria-label="Close" className="text-sm text-muted-foreground hover:text-foreground">
            ✕
          </button>
        </div>

        {phase === 'loading' ? (
          <div className="flex flex-col items-center gap-3 py-8 text-muted-foreground">
            <svg className="animate-spin h-6 w-6" viewBox="0 0 24 24" fill="none">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z" />
            </svg>
            <span className="text-sm">Loading preview…</span>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-3">
            <div className="space-y-1">
              <label className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Title</label>
              <input
                value={form.title}
                onChange={e => setForm(f => ({ ...f, title: e.target.value }))}
                required
                aria-label="Title"
                className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
              />
            </div>

            <div className="space-y-1">
              <label className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Description</label>
              <textarea
                value={form.description}
                onChange={e => setForm(f => ({ ...f, description: e.target.value }))}
                rows={3}
                aria-label="Description"
                className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring resize-none"
              />
            </div>

            <div className="grid grid-cols-3 gap-3">
              <div className="space-y-1">
                <label className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Severity</label>
                <select
                  value={form.severity}
                  onChange={e => setForm(f => ({ ...f, severity: e.target.value }))}
                  aria-label="Severity"
                  className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
                >
                  {SEVERITY_OPTIONS.map(s => <option key={s} value={s}>{s}</option>)}
                </select>
              </div>

              <div className="space-y-1">
                <label className="text-xs font-medium text-muted-foreground uppercase tracking-wider">TLP</label>
                <select
                  value={form.tlp}
                  onChange={e => setForm(f => ({ ...f, tlp: e.target.value }))}
                  aria-label="TLP"
                  className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
                >
                  {TLP_PAP_OPTIONS.map(t => <option key={t} value={t}>TLP:{t.toUpperCase()}</option>)}
                </select>
              </div>

              <div className="space-y-1">
                <label className="text-xs font-medium text-muted-foreground uppercase tracking-wider">PAP</label>
                <select
                  value={form.pap}
                  onChange={e => setForm(f => ({ ...f, pap: e.target.value }))}
                  aria-label="PAP"
                  className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
                >
                  {TLP_PAP_OPTIONS.map(t => <option key={t} value={t}>PAP:{t.toUpperCase()}</option>)}
                </select>
              </div>
            </div>

            {error && <p className="text-sm text-red-600 dark:text-red-400">{error}</p>}

            <div className="flex justify-end gap-3 pt-1">
              <button
                type="button"
                onClick={handleClose}
                disabled={phase === 'submitting'}
                className="rounded-md border border-border bg-background px-4 py-2 text-sm font-medium text-foreground hover:bg-accent disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={phase === 'submitting' || !form.title.trim()}
                className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-colors"
              >
                {phase === 'submitting' ? 'Creating…' : 'Create incident'}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
