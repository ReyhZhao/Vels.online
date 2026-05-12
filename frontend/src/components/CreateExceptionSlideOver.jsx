import { useState, useEffect } from 'react';
import api from '../lib/axios';
import { useOrganization } from '../context/OrgContext';
import SlideOver from './SlideOver';

const FIELD_TYPE_OPTIONS = ['literal', 'pcre2'];
const SCOPE_OPTIONS      = ['org', 'global'];

const INITIAL_FORM = {
  description:    '',
  trigger_rule_id: '',
  match_value:    '',
  field_name:     '',
  field_value:    '',
  field_type:     'literal',
  scope:          'org',
  agent_name:     '',
};

export default function CreateExceptionSlideOver({ open, onClose, incident }) {
  const { selectedOrg } = useOrganization();
  const [form, setForm]           = useState(INITIAL_FORM);
  const [generating, setGenerating] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError]         = useState(null);
  const [success, setSuccess]     = useState(false);

  useEffect(() => {
    if (!open || !incident) return;
    setForm(INITIAL_FORM);
    setError(null);
    setSuccess(false);

    // Pre-fill with LLM proposal
    setGenerating(true);
    api.post('/api/exceptions/generate/', { display_id: incident.display_id })
      .then(res => {
        setForm(f => ({
          ...f,
          description:     res.data.description     || '',
          trigger_rule_id: res.data.trigger_rule_id != null ? String(res.data.trigger_rule_id) : '',
          match_value:     res.data.match_value     || '',
          field_name:      res.data.field_name      || '',
          field_value:     res.data.field_value     || '',
          field_type:      res.data.field_type      || 'literal',
          agent_name:      res.data.agent_name      || '',
        }));
      })
      .catch(() => setError('Could not generate a proposal — please fill in manually.'))
      .finally(() => setGenerating(false));
  }, [open, incident]);

  async function handleSubmit(e) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await api.post('/api/exceptions/', {
        ...form,
        trigger_rule_id: form.trigger_rule_id ? parseInt(form.trigger_rule_id, 10) : null,
        org: selectedOrg?.slug || incident?.org_slug,
        incident: incident?.display_id,
      });
      setSuccess(true);
      setTimeout(onClose, 1200);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to create exception rule.');
    } finally {
      setSubmitting(false);
    }
  }

  const field = (key) => ({
    value: form[key],
    onChange: e => setForm(f => ({ ...f, [key]: e.target.value })),
  });

  const inputCls = 'w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring';
  const labelCls = 'block text-xs font-medium text-muted-foreground uppercase tracking-wider mb-1';

  return (
    <SlideOver
      open={open}
      onClose={onClose}
      title="Create Exception Rule"
      loading={generating}
    >
      <div className="px-6 py-4">
        {generating && (
          <p className="text-sm text-muted-foreground mb-4">Generating proposal from incident data…</p>
        )}

        {success ? (
          <p className="text-sm text-green-600 font-medium">Exception rule created successfully.</p>
        ) : (
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
              <input
                {...field('match_value')}
                aria-label="Match Value"
                className={inputCls}
              />
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className={labelCls}>Field Name</label>
                <input
                  {...field('field_name')}
                  aria-label="Field Name"
                  className={inputCls}
                />
              </div>
              <div>
                <label className={labelCls}>Field Value</label>
                <input
                  {...field('field_value')}
                  aria-label="Field Value"
                  className={inputCls}
                />
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
              <input
                {...field('agent_name')}
                aria-label="Agent Name"
                className={inputCls}
              />
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
                {submitting ? 'Saving…' : 'Create exception'}
              </button>
            </div>
          </form>
        )}
      </div>
    </SlideOver>
  );
}
