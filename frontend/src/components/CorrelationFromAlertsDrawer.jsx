import { useState, useEffect } from 'react';
import api from '../lib/axios';

const SEVERITY_RANK = ['info', 'low', 'medium', 'high', 'critical'];

const EMPTY_CONDITION = { field_kind: 'alert_field', field_name: '', operator: '', value: '' };

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

function deriveInitialState(alerts) {
  const uniqueSourceKinds = [...new Set(alerts.map(a => a.source_kind).filter(Boolean))];
  const uniqueSeverities = [...new Set(alerts.map(a => a.severity).filter(Boolean))];

  const maxSeverity = SEVERITY_RANK.reduce(
    (max, s) => alerts.some(a => a.severity === s) ? s : max,
    'info',
  );

  const conditions = [];
  if (uniqueSourceKinds.length === 1) {
    conditions.push({ field_kind: 'alert_field', field_name: 'source_kind', operator: 'equals', value: uniqueSourceKinds[0] });
  }
  if (uniqueSeverities.length === 1) {
    conditions.push({ field_kind: 'alert_field', field_name: 'severity', operator: 'equals', value: uniqueSeverities[0] });
  }
  if (conditions.length === 0) {
    conditions.push({ ...EMPTY_CONDITION });
  }

  const ids = alerts.map(a => a.display_id).slice(0, 3).join(', ');
  const suffix = alerts.length > 3 ? ` +${alerts.length - 3} more` : '';
  const name = `Pattern: ${ids}${suffix}`;

  return {
    name,
    description: '',
    correlationKey: 'none',
    windowMinutes: 60,
    severity: maxSeverity,
    enabled: true,
    legs: [{ count: alerts.length, display_order: 0, conditions }],
  };
}

export default function CorrelationFromAlertsDrawer({ alerts, onClose, onCreated }) {
  const init = deriveInitialState(alerts);

  const [name, setName] = useState(init.name);
  const [description, setDescription] = useState(init.description);
  const [correlationKey, setCorrelationKey] = useState(init.correlationKey);
  const [windowMinutes, setWindowMinutes] = useState(init.windowMinutes);
  const [severity, setSeverity] = useState(init.severity);
  const [enabled, setEnabled] = useState(init.enabled);
  const [legs, setLegs] = useState(init.legs);
  const [catalog, setCatalog] = useState(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    api.get('/api/correlations/catalog/')
      .then(r => setCatalog(r.data))
      .catch(() => {});
  }, []);

  function updateLeg(legIdx, updated) {
    setLegs(prev => prev.map((l, i) => i === legIdx ? updated : l));
  }

  function removeLeg(legIdx) {
    setLegs(prev => prev.filter((_, i) => i !== legIdx));
  }

  function addLeg() {
    setLegs(prev => [...prev, { count: 1, display_order: prev.length, conditions: [{ ...EMPTY_CONDITION }] }]);
  }

  async function handleSave() {
    setError(null);
    setSaving(true);
    const payload = {
      name: name.trim(),
      description: description.trim(),
      correlation_key: correlationKey,
      window_minutes: Number(windowMinutes),
      severity,
      enabled,
      legs: legs.map((l, i) => ({ ...l, display_order: i })),
    };
    try {
      const res = await api.post('/api/correlations/rules/', payload);
      onCreated(res.data);
    } catch (err) {
      const data = err.response?.data;
      if (typeof data === 'object' && data !== null) {
        const msgs = Object.entries(data)
          .map(([k, v]) => `${k}: ${Array.isArray(v) ? v.join(', ') : v}`)
          .join('; ');
        setError(msgs);
      } else {
        setError('Failed to create rule.');
      }
    } finally {
      setSaving(false);
    }
  }

  const canSave = name.trim().length > 0 && legs.length > 0;

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div className="absolute inset-0 bg-black/40" onClick={onClose} />
      <div className="relative flex h-full w-full max-w-lg flex-col border-l border-border bg-card shadow-2xl">

        <div className="flex shrink-0 items-center justify-between border-b border-border px-6 py-4">
          <div>
            <h2 className="text-lg font-semibold text-foreground">Create Correlation Rule</h2>
            <p className="mt-0.5 text-xs text-muted-foreground">
              Pre-populated from {alerts.length} selected alert{alerts.length !== 1 ? 's' : ''}
            </p>
          </div>
          <button onClick={onClose} className="text-lg text-muted-foreground hover:text-foreground transition-colors">✕</button>
        </div>

        <div className="flex-1 overflow-y-auto thin-scrollbar px-6 py-5 space-y-5">

          {/* Selected alerts summary */}
          <div className="rounded-md border border-border bg-muted/30 p-3">
            <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">Based on alerts</p>
            <div className="flex flex-wrap gap-1">
              {alerts.map(a => (
                <span key={a.display_id} className="inline-flex items-center rounded-full bg-slate-100 dark:bg-slate-800 px-2 py-0.5 text-xs font-mono text-slate-700 dark:text-slate-300">
                  {a.display_id}
                </span>
              ))}
            </div>
          </div>

          <div className="space-y-3">
            <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Rule details</p>
            <div className="grid grid-cols-2 gap-3">
              <div className="col-span-2">
                <label className="block text-xs font-medium text-foreground mb-1">Name *</label>
                <input
                  value={name}
                  onChange={e => setName(e.target.value)}
                  placeholder="Rule name"
                  className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
                />
              </div>
              <div className="col-span-2">
                <label className="block text-xs font-medium text-foreground mb-1">Description</label>
                <input
                  value={description}
                  onChange={e => setDescription(e.target.value)}
                  placeholder="Optional description"
                  className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-foreground mb-1">Correlation key</label>
                <select
                  value={correlationKey}
                  onChange={e => setCorrelationKey(e.target.value)}
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
                  value={windowMinutes}
                  onChange={e => setWindowMinutes(e.target.value)}
                  aria-label="Window minutes"
                  className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-foreground mb-1">Incident severity</label>
                <select
                  value={severity}
                  onChange={e => setSeverity(e.target.value)}
                  aria-label="Severity"
                  className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
                >
                  {(catalog?.severities ?? SEVERITY_RANK).map(s => (
                    <option key={s} value={s}>{s.charAt(0).toUpperCase() + s.slice(1)}</option>
                  ))}
                </select>
              </div>
              <div className="flex items-end pb-1">
                <label className="flex items-center gap-2 text-sm text-foreground cursor-pointer">
                  <input
                    type="checkbox"
                    checked={enabled}
                    onChange={e => setEnabled(e.target.checked)}
                    className="rounded"
                  />
                  Enabled
                </label>
              </div>
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
            {legs.length === 0 && (
              <p className="text-xs text-muted-foreground">No legs. Add at least one leg.</p>
            )}
            {legs.map((leg, li) => (
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
              {saving ? 'Creating…' : 'Create rule'}
            </button>
          </div>
        </div>

      </div>
    </div>
  );
}
