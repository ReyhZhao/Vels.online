import { useState, useEffect } from 'react';
import api from '../lib/axios';

const FIELD_TYPE_OPTIONS = ['literal', 'pcre2'];
const SCOPE_OPTIONS      = ['org', 'global'];

const inputCls = 'w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring';
const labelCls = 'block text-xs font-medium text-muted-foreground uppercase tracking-wider mb-1';

export default function EditExceptionModal({ rule, onClose, onSaved }) {
  const [form, setForm]       = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError]     = useState(null);

  useEffect(() => {
    if (!rule) return;
    setForm({
      description:     rule.description     || '',
      trigger_rule_id: rule.trigger_rule_id != null ? String(rule.trigger_rule_id) : '',
      match_value:     rule.match_value     || '',
      field_name:      rule.field_name      || '',
      field_value:     rule.field_value     || '',
      field_type:      rule.field_type      || 'literal',
      scope:           rule.scope           || 'org',
      agent_name:      rule.agent_name      || '',
    });
    setError(null);
  }, [rule]);

  if (!rule || !form) return null;

  const field = (key) => ({
    value: form[key],
    onChange: e => setForm(f => ({ ...f, [key]: e.target.value })),
  });

  async function handleSubmit(e) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const res = await api.patch(`/api/exceptions/${rule.id}/`, {
        ...form,
        trigger_rule_id: form.trigger_rule_id ? parseInt(form.trigger_rule_id, 10) : null,
      });
      onSaved(res.data);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to update exception rule.');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="w-full max-w-lg rounded-lg border border-border bg-card p-6 shadow-xl">
        <h2 className="text-lg font-semibold text-foreground mb-4">Edit Exception Rule #{rule.wazuh_rule_id}</h2>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className={labelCls}>Description *</label>
            <textarea
              {...field('description')}
              required
              rows={2}
              aria-label="Description"
              className={`${inputCls} resize-none`}
            />
          </div>

          <div>
            <label className={labelCls}>Trigger Rule ID</label>
            <input
              type="number"
              {...field('trigger_rule_id')}
              aria-label="Trigger Rule ID"
              className={inputCls}
            />
          </div>

          <div>
            <label className={labelCls}>Match Value</label>
            <input {...field('match_value')} aria-label="Match Value" className={inputCls} />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className={labelCls}>Field Name</label>
              <input {...field('field_name')} aria-label="Field Name" className={inputCls} />
            </div>
            <div>
              <label className={labelCls}>Field Value</label>
              <input {...field('field_value')} aria-label="Field Value" className={inputCls} />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className={labelCls}>Field Type</label>
              <select {...field('field_type')} aria-label="Field Type" className={inputCls}>
                {FIELD_TYPE_OPTIONS.map(o => <option key={o} value={o}>{o}</option>)}
              </select>
            </div>
            <div>
              <label className={labelCls}>Scope</label>
              <select {...field('scope')} aria-label="Scope" className={inputCls}>
                {SCOPE_OPTIONS.map(o => <option key={o} value={o}>{o}</option>)}
              </select>
            </div>
          </div>

          <div>
            <label className={labelCls}>Agent Name</label>
            <input {...field('agent_name')} aria-label="Agent Name" className={inputCls} />
          </div>

          {error && <p className="text-sm text-red-600">{error}</p>}

          <div className="flex justify-end gap-3 pt-2">
            <button
              type="button"
              onClick={onClose}
              disabled={submitting}
              className="rounded-md border border-border bg-background px-4 py-2 text-sm font-medium text-foreground hover:bg-accent disabled:opacity-50"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={submitting || !form.description.trim()}
              className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-colors"
            >
              {submitting ? 'Saving…' : 'Save changes'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
