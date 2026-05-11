import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import api from '../lib/axios';
import { useOrganization } from '../context/OrgContext';

const SEVERITY_OPTIONS = ['critical', 'high', 'medium', 'low', 'info'];
const TLP_PAP_OPTIONS  = ['white', 'green', 'amber', 'red'];

const INITIAL_FORM = {
  title:       '',
  description: '',
  severity:    'medium',
  tlp:         'amber',
  pap:         'amber',
};

export default function CreateIncidentModal({ open, onClose }) {
  const navigate = useNavigate();
  const { selectedOrg } = useOrganization();
  const [form, setForm]           = useState(INITIAL_FORM);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError]         = useState(null);

  function handleClose() {
    setForm(INITIAL_FORM);
    setError(null);
    onClose();
  }

  async function handleSubmit(e) {
    e.preventDefault();
    if (!selectedOrg?.slug) return;
    setSubmitting(true);
    setError(null);
    try {
      const res = await api.post('/api/incidents/', {
        ...form,
        source_kind: 'manual',
        org: selectedOrg.slug,
      });
      handleClose();
      navigate(`/incidents/${res.data.display_id}`);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to create incident.');
    } finally {
      setSubmitting(false);
    }
  }

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/50 pt-12 pb-12">
      <div className="w-full max-w-lg rounded-lg border border-border bg-card p-6 shadow-lg space-y-5 mx-4">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold text-foreground">New Incident</h2>
          <button
            onClick={handleClose}
            aria-label="Close"
            className="text-sm text-muted-foreground hover:text-foreground"
          >
            ✕
          </button>
        </div>

        {!selectedOrg && (
          <p className="text-sm text-amber-600 dark:text-amber-400">
            No organisation selected. Please select an organisation to continue.
          </p>
        )}

        <form onSubmit={handleSubmit} className="space-y-3">
          <div className="space-y-1">
            <label className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
              Title
            </label>
            <input
              value={form.title}
              onChange={e => setForm(f => ({ ...f, title: e.target.value }))}
              required
              aria-label="Title"
              className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
            />
          </div>

          <div className="space-y-1">
            <label className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
              Description
            </label>
            <textarea
              value={form.description}
              onChange={e => setForm(f => ({ ...f, description: e.target.value }))}
              rows={3}
              aria-label="Description"
              className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring resize-none"
            />
          </div>

          <div className="space-y-1">
            <label className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
              Severity
            </label>
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
            <label className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
              TLP
            </label>
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
            <label className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
              PAP
            </label>
            <select
              value={form.pap}
              onChange={e => setForm(f => ({ ...f, pap: e.target.value }))}
              aria-label="PAP"
              className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
            >
              {TLP_PAP_OPTIONS.map(t => <option key={t} value={t}>PAP:{t.toUpperCase()}</option>)}
            </select>
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
              disabled={submitting || !form.title.trim() || !selectedOrg}
              title={!selectedOrg ? 'Select an organisation first' : undefined}
              className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-colors"
            >
              {submitting ? 'Creating…' : 'Create incident'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
