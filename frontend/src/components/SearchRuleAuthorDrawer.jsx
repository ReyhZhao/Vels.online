import { useState, useEffect, useRef } from 'react';
import api from '../lib/axios';

const EMPTY_CONDITION = { field_name: '', operator: 'equals', value: '' };
const EMPTY_DRAFT = {
  name: '',
  description: '',
  correlation_key: 'none',
  window_minutes: 60,
  interval_minutes: 60,
  baseline_lookback_days: 30,
  max_findings_per_run: 50,
  severity: 'medium',
  include_agentless: false,
  enabled: true,
  time_window_start: null,
  time_window_end: null,
  time_window_days: [],
  time_window_mode: 'inside',
  legs: [{ count: 1, count_operator: 'gte', display_order: 0, conditions: [{ ...EMPTY_CONDITION }] }],
  organization: undefined,
};

const WEEKDAYS = [[1, 'Mon'], [2, 'Tue'], [3, 'Wed'], [4, 'Thu'], [5, 'Fri'], [6, 'Sat'], [7, 'Sun']];

const SEARCH_OPERATORS = [
  { value: 'equals', label: 'Equals' },
  { value: 'contains', label: 'Contains' },
  { value: 'gte', label: '>=' },
  { value: 'lte', label: '<=' },
  { value: 'cidr', label: 'IP in CIDR' },
];

function ConditionRow({ cond, index, onChange, onRemove }) {
  return (
    <div className="flex gap-2 items-start flex-wrap">
      <input
        value={cond.field_name}
        onChange={e => onChange(index, { ...cond, field_name: e.target.value })}
        placeholder="Wazuh field (e.g. rule.id)"
        aria-label="Field name"
        className="flex-1 min-w-32 rounded border border-border bg-background px-2 py-1 text-xs focus:outline-none focus:ring-1 focus:ring-ring"
      />
      <select
        value={cond.operator}
        onChange={e => onChange(index, { ...cond, operator: e.target.value })}
        aria-label="Operator"
        className="rounded border border-border bg-background px-2 py-1 text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
      >
        {SEARCH_OPERATORS.map(op => (
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

function LegEditor({ leg, legIndex, correlationKey, onChange, onRemove }) {
  const hasDiversity = !!(leg.distinct_field && leg.distinct_field.trim());
  const diversityNeedsKey = hasDiversity && correlationKey === 'none';
  const countOperator = leg.count_operator ?? 'gte';
  const isAbsence = countOperator === 'lte';
  const hasNovelty = !!(leg.novelty_field && leg.novelty_field.trim());
  const noveltyNeedsKey = hasNovelty && correlationKey === 'none';
  const noveltyConflictsAbsence = hasNovelty && isAbsence;
  const absenceNeedsNoneKey = isAbsence && correlationKey !== 'none';

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
            Count
            <select
              value={countOperator}
              onChange={e => onChange(legIndex, { ...leg, count_operator: e.target.value })}
              aria-label={`Leg ${legIndex + 1} count operator`}
              className="rounded border border-border bg-background px-1 py-0.5 text-xs focus:outline-none focus:ring-1 focus:ring-ring"
            >
              <option value="gte">≥</option>
              <option value="lte">≤</option>
            </select>
            <input
              type="number"
              min={isAbsence ? 0 : 1}
              value={leg.count}
              onChange={e => onChange(legIndex, { ...leg, count: Number(e.target.value) })}
              aria-label={`Leg ${legIndex + 1} count`}
              className="w-14 rounded border border-border bg-background px-2 py-0.5 text-xs focus:outline-none focus:ring-1 focus:ring-ring"
            />
            matching docs
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

      {isAbsence && (
        <p className="text-xs text-muted-foreground">
          Absence firing: this leg triggers when <em>at most</em> {leg.count} document(s) match in the
          window (e.g. ≤ 0 = “no matching documents”). It produces an incident with no evidence alerts.
        </p>
      )}
      {absenceNeedsNoneKey && (
        <p className="text-xs text-destructive">
          The “at most (≤)” operator is only supported when the correlation key is “None”.
        </p>
      )}

      <div className="space-y-1.5">
        {leg.conditions.map((cond, ci) => (
          <ConditionRow
            key={ci}
            cond={cond}
            index={ci}
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

      {/* Diversity Constraint (ADR-0009) */}
      <div className="border-t border-border/60 pt-2 space-y-1">
        <div className="flex items-center gap-2 flex-wrap text-xs text-foreground">
          <span className="text-muted-foreground">Diversity (optional):</span>
          <span>distinct values of</span>
          <input
            value={leg.distinct_field ?? ''}
            onChange={e => onChange(legIndex, { ...leg, distinct_field: e.target.value })}
            placeholder="e.g. GeoLocation.country_name"
            aria-label={`Leg ${legIndex + 1} distinct field`}
            className="flex-1 min-w-40 rounded border border-border bg-background px-2 py-0.5 text-xs focus:outline-none focus:ring-1 focus:ring-ring"
          />
          {hasDiversity && (
            <label className="flex items-center gap-1 whitespace-nowrap">
              ≥
              <input
                type="number"
                min={2}
                value={leg.min_distinct ?? 2}
                onChange={e => onChange(legIndex, { ...leg, min_distinct: Number(e.target.value) })}
                aria-label={`Leg ${legIndex + 1} min distinct`}
                className="w-14 rounded border border-border bg-background px-2 py-0.5 text-xs focus:outline-none focus:ring-1 focus:ring-ring"
              />
              distinct
            </label>
          )}
        </div>
        {diversityNeedsKey && (
          <p className="text-xs text-destructive">
            A diversity constraint requires a correlation key (not “None”) to group by.
          </p>
        )}
      </div>

      {/* Novelty Constraint (ADR-0021): fire on a value never seen before in the baseline */}
      <div className="border-t border-border/60 pt-2 space-y-1">
        <div className="flex items-center gap-2 flex-wrap text-xs text-foreground">
          <span className="text-muted-foreground">Novelty (optional):</span>
          <span>first-seen value of</span>
          <input
            value={leg.novelty_field ?? ''}
            onChange={e => onChange(legIndex, { ...leg, novelty_field: e.target.value })}
            placeholder="e.g. agent.name"
            aria-label={`Leg ${legIndex + 1} novelty field`}
            className="flex-1 min-w-40 rounded border border-border bg-background px-2 py-0.5 text-xs focus:outline-none focus:ring-1 focus:ring-ring"
          />
        </div>
        {hasNovelty && (
          <p className="text-xs text-muted-foreground">
            Fires when <code>{leg.novelty_field}</code> takes a value <strong>never seen before</strong>{' '}
            for the correlation key, judged against the rule’s baseline lookback (distinct from
            Diversity, which counts distinct values <em>within</em> the window).
          </p>
        )}
        {noveltyNeedsKey && (
          <p className="text-xs text-destructive">
            A novelty constraint requires a correlation key (not “None”) to group by.
          </p>
        )}
        {noveltyConflictsAbsence && (
          <p className="text-xs text-destructive">
            A novelty constraint cannot be combined with the “at most (≤)” operator (an absence firing).
          </p>
        )}
      </div>
    </div>
  );
}

/**
 * Two-pass AI drafting drawer for Scheduled Search Rules.
 * Replays messages[] + current_draft to the search-draft endpoint each turn.
 * Server stays stateless (ADR-0005); conversation lives in client state.
 */
export default function SearchRuleAuthorDrawer({ initialScope, onClose, onSaved }) {
  const [messages, setMessages] = useState([]);
  const [draft, setDraft] = useState({ ...EMPTY_DRAFT });
  const [warnings, setWarnings] = useState([]);
  const [scope, setScope] = useState(initialScope || 'all');
  const [orgs, setOrgs] = useState([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const threadRef = useRef(null);

  useEffect(() => {
    api.get('/api/security/organizations/').then(res => setOrgs(res.data)).catch(() => {});
  }, []);

  // Keep draft.organization in sync with the scope selector.
  useEffect(() => {
    if (scope === 'all') {
      setDraft(prev => ({ ...prev, organization: null }));
    } else {
      const org = orgs.find(o => o.slug === scope);
      if (org) setDraft(prev => ({ ...prev, organization: org.id }));
    }
  }, [scope, orgs]);

  useEffect(() => {
    if (threadRef.current) {
      threadRef.current.scrollTop = threadRef.current.scrollHeight;
    }
  }, [messages, loading]);

  async function handleSend(messageOverride) {
    const content = messageOverride !== undefined ? messageOverride : input.trim();
    if (!content || loading) return;
    const userMsg = { role: 'user', content };
    const nextMessages = [...messages, userMsg];
    setMessages(nextMessages);
    if (messageOverride === undefined) setInput('');
    setLoading(true);
    setError(null);

    try {
      const res = await api.post('/api/correlations/search-draft/', {
        messages: nextMessages,
        current_draft: draft.name ? draft : null,
        scope,
      });
      const { updated_draft, assistant_reply, warnings: w, tool_trace } = res.data;
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: assistant_reply,
        tool_trace: tool_trace || [],
      }]);
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
      legs: [...prev.legs, { count: 1, count_operator: 'gte', display_order: prev.legs.length, novelty_field: '', conditions: [{ ...EMPTY_CONDITION }] }],
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
      const res = await api.post('/api/correlations/search-rules/', payload);
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

  const SEVERITIES = ['critical', 'high', 'medium', 'low', 'info'];
  const CORR_KEYS = [
    { value: 'none', label: 'None (org-wide)' },
    { value: 'host.name', label: 'Host' },
    { value: 'source.ip', label: 'Source IP' },
    { value: 'user.name', label: 'Username' },
    { value: 'file.hash.sha256', label: 'File Hash' },
    { value: 'process.name', label: 'Process' },
  ];

  const canSave = draft.name.trim().length > 0 && draft.legs.length > 0;

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div className="absolute inset-0 bg-black/40" onClick={onClose} />
      <div className="relative flex h-full w-full max-w-4xl flex-col border-l border-border bg-card shadow-2xl">

        {/* Header */}
        <div className="flex shrink-0 items-center justify-between border-b border-border px-6 py-4">
          <div>
            <h2 className="text-lg font-semibold text-foreground">Draft Search Rule with AI</h2>
            <p className="mt-0.5 text-xs text-muted-foreground">
              Two-pass drafting: AI selects relevant Wazuh rules, then drafts conditions. Edit and save.
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
                  Describe what to detect in raw Wazuh events. Follow up to refine the draft.
                </p>
              )}
              {messages.map((msg, i) => (
                <div key={i} className={`flex flex-col ${msg.role === 'user' ? 'items-end' : 'items-start'}`}>
                  <div
                    className={`rounded-lg px-3 py-2 text-xs max-w-[85%] whitespace-pre-wrap ${
                      msg.role === 'user'
                        ? 'bg-primary text-primary-foreground'
                        : 'bg-muted text-foreground'
                    }`}
                  >
                    {msg.content}
                  </div>
                  {msg.role === 'assistant' && msg.tool_trace?.length > 0 && (
                    <div className="mt-1 max-w-[85%] text-[11px] text-muted-foreground space-y-0.5">
                      {msg.tool_trace.map((t, j) => (
                        <p key={j} className={t.error ? 'text-amber-600 dark:text-amber-400' : ''}>
                          🔎 {t.error ? `${t.tool}: ${t.error}` : (t.summary || t.tool)}
                        </p>
                      ))}
                    </div>
                  )}
                </div>
              ))}
              {loading && (
                <div className="flex justify-start">
                  <div className="rounded-lg px-3 py-2 text-xs bg-muted text-muted-foreground">
                    Selecting rules + drafting…
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
                  rows={4}
                  disabled={loading}
                  className="flex-1 rounded-md border border-border bg-background px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-ring resize-none disabled:opacity-50"
                />
                <button
                  type="button"
                  onClick={() => handleSend()}
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
                    {CORR_KEYS.map(ck => (
                      <option key={ck.value} value={ck.value}>{ck.label}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-medium text-foreground mb-1">Severity</label>
                  <select
                    value={draft.severity}
                    onChange={e => updateDraft({ severity: e.target.value })}
                    aria-label="Severity"
                    className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
                  >
                    {SEVERITIES.map(s => (
                      <option key={s} value={s}>{s.charAt(0).toUpperCase() + s.slice(1)}</option>
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
                  <label className="block text-xs font-medium text-foreground mb-1">Interval (minutes)</label>
                  <input
                    type="number"
                    min={5}
                    value={draft.interval_minutes}
                    onChange={e => updateDraft({ interval_minutes: Number(e.target.value) })}
                    aria-label="Interval minutes"
                    className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-foreground mb-1">Baseline lookback (days)</label>
                  <input
                    type="number"
                    min={1}
                    value={draft.baseline_lookback_days ?? 30}
                    onChange={e => updateDraft({ baseline_lookback_days: Number(e.target.value) })}
                    aria-label="Baseline lookback days"
                    className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
                  />
                  <p className="mt-1 text-[11px] text-muted-foreground">
                    History depth for Novelty legs (first-seen). Larger ≈ “ever”.
                  </p>
                </div>
                <div>
                  <label className="block text-xs font-medium text-foreground mb-1">Max findings / run</label>
                  <input
                    type="number"
                    min={1}
                    value={draft.max_findings_per_run}
                    onChange={e => updateDraft({ max_findings_per_run: Number(e.target.value) })}
                    aria-label="Max findings per run"
                    className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
                  />
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
                <div className="col-span-2">
                  <label className="flex items-center gap-2 text-sm text-foreground cursor-pointer">
                    <input
                      type="checkbox"
                      checked={draft.include_agentless ?? false}
                      onChange={e => updateDraft({ include_agentless: e.target.checked })}
                      className="rounded"
                    />
                    Include agentless events
                  </label>
                  <p className="mt-1 text-xs text-muted-foreground">
                    Match events from infrastructure components (e.g. reverse proxy, firewalls) that are not linked to a registered Wazuh agent.
                  </p>
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
                    correlationKey={draft.correlation_key}
                    onChange={updateLeg}
                    onRemove={removeLeg}
                  />
                ))}
              </div>

              {/* Time-of-day window (#440): optional, may be set by the assistant or by hand */}
              <div className="space-y-3 border-t border-border pt-4">
                <div className="flex items-center justify-between">
                  <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Time-of-day window (optional)</p>
                  {(draft.time_window_start || draft.time_window_end || (draft.time_window_days ?? []).length > 0) && (
                    <button
                      type="button"
                      onClick={() => updateDraft({ time_window_start: null, time_window_end: null, time_window_days: [], time_window_mode: 'inside' })}
                      className="text-xs text-muted-foreground hover:text-red-600"
                    >
                      Clear
                    </button>
                  )}
                </div>
                <p className="text-xs text-muted-foreground">
                  Restrict matches to (or away from) hours of the day, evaluated in the organization's timezone.
                  Ask the assistant (e.g. "only outside working hours") or set it here. Leave empty for no constraint.
                </p>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs font-medium text-foreground mb-1">Start</label>
                    <input
                      type="time"
                      value={(draft.time_window_start ?? '').slice(0, 5)}
                      onChange={e => updateDraft({ time_window_start: e.target.value ? `${e.target.value}:00` : null })}
                      aria-label="Time window start"
                      className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-foreground mb-1">End</label>
                    <input
                      type="time"
                      value={(draft.time_window_end ?? '').slice(0, 5)}
                      onChange={e => updateDraft({ time_window_end: e.target.value ? `${e.target.value}:00` : null })}
                      aria-label="Time window end"
                      className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
                    />
                  </div>
                </div>
                <div>
                  <label className="block text-xs font-medium text-foreground mb-1">Days</label>
                  <div className="flex gap-1 flex-wrap">
                    {WEEKDAYS.map(([d, label]) => {
                      const days = draft.time_window_days ?? [];
                      const active = days.includes(d);
                      return (
                        <button
                          key={d}
                          type="button"
                          aria-pressed={active}
                          onClick={() => updateDraft({ time_window_days: active ? days.filter(x => x !== d) : [...days, d].sort((a, b) => a - b) })}
                          className={`rounded-md px-2 py-1 text-xs font-medium border transition-colors ${active ? 'bg-primary text-primary-foreground border-primary' : 'bg-background text-muted-foreground border-border hover:bg-accent'}`}
                        >
                          {label}
                        </button>
                      );
                    })}
                  </div>
                </div>
                <div>
                  <label className="block text-xs font-medium text-foreground mb-1">Mode</label>
                  <select
                    value={draft.time_window_mode ?? 'inside'}
                    onChange={e => updateDraft({ time_window_mode: e.target.value })}
                    aria-label="Time window mode"
                    className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
                  >
                    <option value="inside">Inside window (only during these hours)</option>
                    <option value="outside">Outside window (only outside these hours)</option>
                  </select>
                </div>
                {draft.time_window_start && draft.time_window_end && (draft.time_window_days ?? []).length === 0 && (
                  <p className="text-xs text-destructive">Select at least one day, or clear the window.</p>
                )}
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
