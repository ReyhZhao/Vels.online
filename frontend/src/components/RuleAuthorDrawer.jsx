import { useState, useEffect, useRef } from 'react';
import api from '../lib/axios';

const EMPTY_CONDITION = { field_kind: 'alert_field', field_name: '', operator: '', value: '' };
const EMPTY_DRAFT = {
  name: '',
  description: '',
  correlation_key: 'none',
  window_minutes: 60,
  severity: 'medium',
  enabled: true,
  legs: [{ count: 1, display_order: 0, conditions: [{ ...EMPTY_CONDITION }] }],
  organization: undefined,
};

function ConditionRow({ cond, index, catalog, onChange, onRemove }) {
  const fieldOptions = catalog?.fields?.[cond.field_kind] ?? [];
  const operatorOptions = catalog?.operators?.[cond.field_kind] ?? [];

  return (
    <div className="flex gap-2 items-start flex-wrap">
      <select
        value={cond.field_kind}
        onChange={e => onChange(index, { field_kind: e.target.value, field_name: '', operator: '', value: '' })}
        aria-label="Field kind"
        className="rounded border border-border bg-background px-2 py-1 text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
      >
        {(catalog?.field_kinds ?? []).map(fk => (
          <option key={fk.value} value={fk.value}>{fk.label}</option>
        ))}
      </select>

      <select
        value={cond.field_name}
        onChange={e => onChange(index, { ...cond, field_name: e.target.value })}
        aria-label="Field name"
        className="rounded border border-border bg-background px-2 py-1 text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
      >
        <option value="">Field…</option>
        {fieldOptions.map(f => (
          <option key={f.value} value={f.value}>{f.label}</option>
        ))}
      </select>

      <select
        value={cond.operator}
        onChange={e => onChange(index, { ...cond, operator: e.target.value })}
        aria-label="Operator"
        className="rounded border border-border bg-background px-2 py-1 text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
      >
        <option value="">Op…</option>
        {operatorOptions.map(op => (
          <option key={op.value} value={op.value}>{op.label}</option>
        ))}
      </select>

      <input
        value={cond.value}
        onChange={e => onChange(index, { ...cond, value: e.target.value })}
        placeholder="Value"
        aria-label="Value"
        className="flex-1 min-w-20 rounded border border-border bg-background px-2 py-1 text-xs focus:outline-none focus:ring-1 focus:ring-ring"
      />

      <button
        type="button"
        onClick={() => onRemove(index)}
        aria-label="Remove condition"
        className="text-xs text-red-500 hover:text-red-700 px-1"
      >
        ✕
      </button>
    </div>
  );
}

function LegEditor({ leg, legIndex, catalog, onChange, onRemove }) {
  function updateCondition(condIdx, updates) {
    const conds = leg.conditions.map((c, i) => i === condIdx ? { ...c, ...updates } : c);
    onChange(legIndex, { ...leg, conditions: conds });
  }

  function removeCondition(condIdx) {
    const conds = leg.conditions.filter((_, i) => i !== condIdx);
    onChange(legIndex, { ...leg, conditions: conds });
  }

  function addCondition() {
    onChange(legIndex, { ...leg, conditions: [...leg.conditions, { ...EMPTY_CONDITION }] });
  }

  return (
    <div className="rounded border border-border bg-muted/20 p-3 space-y-2">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
            Leg {legIndex + 1}
          </span>
          <label className="flex items-center gap-1 text-xs text-foreground">
            Count ≥
            <input
              type="number"
              min={1}
              value={leg.count}
              onChange={e => onChange(legIndex, { ...leg, count: Number(e.target.value) })}
              aria-label={`Leg ${legIndex + 1} count`}
              className="w-14 rounded border border-border bg-background px-2 py-0.5 text-xs focus:outline-none focus:ring-1 focus:ring-ring"
            />
            alerts
          </label>
        </div>
        <button
          type="button"
          onClick={() => onRemove(legIndex)}
          className="text-xs text-muted-foreground hover:text-red-600"
        >
          Remove leg
        </button>
      </div>

      <div className="space-y-1.5">
        {leg.conditions.map((cond, ci) => (
          <ConditionRow
            key={ci}
            cond={cond}
            index={ci}
            catalog={catalog}
            onChange={updateCondition}
            onRemove={removeCondition}
          />
        ))}
      </div>

      <button
        type="button"
        onClick={addCondition}
        className="text-xs text-primary hover:underline"
      >
        + Add condition
      </button>
    </div>
  );
}

/**
 * Conversational rule-drafting drawer.
 * Replays messages[] + current_draft to the draft endpoint each turn.
 * Server stays stateless; conversation lives in client state and disappears on close.
 */
export default function RuleAuthorDrawer({ initialDraft, onClose, onSaved }) {
  const [messages, setMessages] = useState([]);
  const [draft, setDraft] = useState(() => ({ ...EMPTY_DRAFT, ...(initialDraft || {}) }));
  const [warnings, setWarnings] = useState([]);
  const [scope, setScope] = useState('all');
  const [orgs, setOrgs] = useState([]);
  const [catalog, setCatalog] = useState(null);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const threadRef = useRef(null);

  useEffect(() => {
    Promise.all([
      api.get('/api/correlations/catalog/'),
      api.get('/api/security/organizations/'),
    ]).then(([catalogRes, orgsRes]) => {
      setCatalog(catalogRes.data);
      setOrgs(orgsRes.data);
    }).catch(() => {});
  }, []);

  // Keep draft.organization in sync with the scope selector so pre-AI saves are correct.
  useEffect(() => {
    if (scope === 'all') {
      setDraft(prev => ({ ...prev, organization: null }));
    } else {
      const org = orgs.find(o => o.slug === scope);
      if (org) setDraft(prev => ({ ...prev, organization: org.id }));
    }
  }, [scope, orgs]);

  // Auto-scroll conversation thread to bottom.
  useEffect(() => {
    if (threadRef.current) {
      threadRef.current.scrollTop = threadRef.current.scrollHeight;
    }
  }, [messages, loading]);

  async function handleSend() {
    if (!input.trim() || loading) return;
    const userMsg = { role: 'user', content: input.trim() };
    const nextMessages = [...messages, userMsg];
    setMessages(nextMessages);
    setInput('');
    setLoading(true);
    setError(null);

    try {
      const res = await api.post('/api/correlations/draft/', {
        messages: nextMessages,
        current_draft: draft.name ? draft : null,
        scope,
      });
      const { updated_draft, assistant_reply, warnings: w } = res.data;
      setMessages(prev => [...prev, { role: 'assistant', content: assistant_reply }]);
      setDraft(updated_draft);
      setWarnings(w || []);
    } catch (err) {
      const d = err.response?.data;
      setError(d?.detail || d?.reason || 'Failed to generate draft.');
    } finally {
      setLoading(false);
    }
  }

  function updateDraft(updates) {
    setDraft(prev => ({ ...prev, ...updates }));
  }

  function updateLeg(legIdx, updated) {
    setDraft(prev => ({
      ...prev,
      legs: prev.legs.map((l, i) => i === legIdx ? updated : l),
    }));
  }

  function removeLeg(legIdx) {
    setDraft(prev => ({
      ...prev,
      legs: prev.legs.filter((_, i) => i !== legIdx),
    }));
  }

  function addLeg() {
    setDraft(prev => ({
      ...prev,
      legs: [...prev.legs, { count: 1, display_order: prev.legs.length, conditions: [{ ...EMPTY_CONDITION }] }],
    }));
  }

  async function handleSave() {
    setSaving(true);
    setError(null);
    const payload = {
      ...draft,
      legs: draft.legs.map((l, i) => ({ ...l, display_order: i })),
    };
    try {
      const res = await api.post('/api/correlations/rules/', payload);
      onSaved(res.data);
    } catch (err) {
      const d = err.response?.data;
      if (typeof d === 'object' && d !== null) {
        setError(Object.entries(d).map(([k, v]) => `${k}: ${Array.isArray(v) ? v.join(', ') : v}`).join('; '));
      } else {
        setError('Failed to save rule.');
      }
    } finally {
      setSaving(false);
    }
  }

  const canSave = draft.name.trim().length > 0 && draft.legs.length > 0;

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div className="absolute inset-0 bg-black/40" onClick={onClose} />
      <div className="relative flex h-full w-full max-w-4xl flex-col border-l border-border bg-card shadow-2xl">

        {/* Header */}
        <div className="flex shrink-0 items-center justify-between border-b border-border px-6 py-4">
          <div>
            <h2 className="text-lg font-semibold text-foreground">Draft with AI</h2>
            <p className="mt-0.5 text-xs text-muted-foreground">
              Converse to refine — edit any field directly, then save
            </p>
          </div>
          <button
            onClick={onClose}
            aria-label="Close drawer"
            className="text-lg text-muted-foreground hover:text-foreground transition-colors"
          >
            ✕
          </button>
        </div>

        {/* Body: conversation | draft editor */}
        <div className="flex flex-1 min-h-0">

          {/* Left: conversation panel */}
          <div className="flex flex-col w-2/5 border-r border-border min-h-0">

            {/* Scope selector */}
            <div className="shrink-0 border-b border-border px-4 py-3 space-y-1.5">
              <label className="block text-xs font-medium text-foreground">Scope</label>
              <select
                value={scope}
                onChange={e => setScope(e.target.value)}
                aria-label="Grounding scope"
                className="w-full rounded-md border border-border bg-background px-2 py-1.5 text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
              >
                <option value="all">All organizations — System Rule</option>
                {orgs.map(o => (
                  <option key={o.slug} value={o.slug}>{o.name} — Org Rule</option>
                ))}
              </select>
            </div>

            {/* Message thread */}
            <div ref={threadRef} className="flex-1 overflow-y-auto thin-scrollbar px-4 py-3 space-y-3 min-h-0">
              {messages.length === 0 && !loading && (
                <p className="text-xs text-muted-foreground text-center mt-8">
                  Describe what to detect. Follow up to refine the draft.
                </p>
              )}
              {messages.map((msg, i) => (
                <div key={i} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                  <div
                    className={`rounded-lg px-3 py-2 text-xs max-w-[85%] whitespace-pre-wrap ${
                      msg.role === 'user'
                        ? 'bg-primary text-primary-foreground'
                        : 'bg-muted text-foreground'
                    }`}
                  >
                    {msg.content}
                  </div>
                </div>
              ))}
              {loading && (
                <div className="flex justify-start">
                  <div className="rounded-lg px-3 py-2 text-xs bg-muted text-muted-foreground">
                    Drafting…
                  </div>
                </div>
              )}
            </div>

            {/* Warnings */}
            {warnings.length > 0 && (
              <div className="shrink-0 border-t border-yellow-200 bg-yellow-50 dark:border-yellow-700 dark:bg-yellow-900/20 px-4 py-2 space-y-1">
                <p className="text-xs font-semibold text-yellow-800 dark:text-yellow-300">Warnings:</p>
                <ul className="list-disc list-inside space-y-0.5">
                  {warnings.map((w, i) => (
                    <li key={i} className="text-xs text-yellow-700 dark:text-yellow-400">{w}</li>
                  ))}
                </ul>
              </div>
            )}

            {/* Message input */}
            <div className="shrink-0 border-t border-border px-4 py-3">
              <div className="flex gap-2">
                <textarea
                  value={input}
                  onChange={e => setInput(e.target.value)}
                  onKeyDown={e => {
                    if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) handleSend();
                  }}
                  placeholder="Describe what to detect… (⌘Enter to send)"
                  rows={2}
                  disabled={loading}
                  className="flex-1 rounded-md border border-border bg-background px-2 py-1.5 text-xs focus:outline-none focus:ring-1 focus:ring-ring resize-none disabled:opacity-50"
                />
                <button
                  type="button"
                  onClick={handleSend}
                  disabled={!input.trim() || loading}
                  aria-label="Send message"
                  className="self-end rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-colors"
                >
                  Send
                </button>
              </div>
            </div>
          </div>

          {/* Right: draft editor */}
          <div className="flex flex-col flex-1 min-w-0 min-h-0">
            <div className="flex-1 overflow-y-auto thin-scrollbar px-5 py-4 space-y-4">

              <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                Rule details
              </p>

              {draft.organization !== undefined && (
                <div
                  className={`rounded-md px-3 py-2 text-xs font-medium ${
                    draft.organization
                      ? 'bg-blue-50 text-blue-800 dark:bg-blue-900/20 dark:text-blue-300'
                      : 'bg-purple-50 text-purple-800 dark:bg-purple-900/20 dark:text-purple-300'
                  }`}
                >
                  {draft.organization
                    ? `Org Rule (organization #${draft.organization})`
                    : 'System Rule — applies to all organizations'}
                </div>
              )}

              <div className="grid grid-cols-2 gap-3">
                <div className="col-span-2">
                  <label className="block text-xs font-medium text-foreground mb-1">Name *</label>
                  <input
                    value={draft.name}
                    onChange={e => updateDraft({ name: e.target.value })}
                    placeholder="Rule name"
                    className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
                  />
                </div>
                <div className="col-span-2">
                  <label className="block text-xs font-medium text-foreground mb-1">Description</label>
                  <input
                    value={draft.description}
                    onChange={e => updateDraft({ description: e.target.value })}
                    placeholder="Optional description"
                    className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-foreground mb-1">Correlation key</label>
                  <select
                    value={draft.correlation_key}
                    onChange={e => updateDraft({ correlation_key: e.target.value })}
                    aria-label="Correlation key"
                    className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
                  >
                    {(catalog?.correlation_keys ?? []).map(ck => (
                      <option key={ck.value} value={ck.value}>{ck.label}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-medium text-foreground mb-1">Window (minutes)</label>
                  <input
                    type="number"
                    min={1}
                    value={draft.window_minutes}
                    onChange={e => updateDraft({ window_minutes: Number(e.target.value) })}
                    aria-label="Window minutes"
                    className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-foreground mb-1">Incident severity</label>
                  <select
                    value={draft.severity}
                    onChange={e => updateDraft({ severity: e.target.value })}
                    aria-label="Severity"
                    className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
                  >
                    {(catalog?.severities ?? ['critical', 'high', 'medium', 'low', 'info']).map(s => (
                      <option key={s} value={s}>{s.charAt(0).toUpperCase() + s.slice(1)}</option>
                    ))}
                  </select>
                </div>
                <div className="flex items-end pb-1">
                  <label className="flex items-center gap-2 text-sm text-foreground cursor-pointer">
                    <input
                      type="checkbox"
                      checked={draft.enabled}
                      onChange={e => updateDraft({ enabled: e.target.checked })}
                      className="rounded"
                    />
                    Enabled
                  </label>
                </div>
              </div>

              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Legs</p>
                  <button
                    type="button"
                    onClick={addLeg}
                    className="text-xs text-primary hover:underline"
                  >
                    + Add leg
                  </button>
                </div>
                {draft.legs.length === 0 && (
                  <p className="text-xs text-muted-foreground">No legs. Add at least one leg.</p>
                )}
                {draft.legs.map((leg, li) => (
                  <LegEditor
                    key={li}
                    leg={leg}
                    legIndex={li}
                    catalog={catalog}
                    onChange={updateLeg}
                    onRemove={removeLeg}
                  />
                ))}
              </div>

            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="shrink-0 border-t border-border bg-card px-6 py-4 space-y-3">
          {error && <p className="text-sm text-destructive">{error}</p>}
          <div className="flex gap-3">
            <button
              type="button"
              onClick={onClose}
              className="flex-1 rounded-md border border-border px-4 py-2 text-sm font-medium text-foreground hover:bg-accent transition-colors"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={handleSave}
              disabled={!canSave || saving}
              className="flex-1 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-colors"
            >
              {saving ? 'Saving…' : 'Save rule'}
            </button>
          </div>
        </div>

      </div>
    </div>
  );
}
