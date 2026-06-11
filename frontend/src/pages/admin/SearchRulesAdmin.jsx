import { useState, useEffect } from 'react';
import { Play, Sparkles, Bug, FlaskConical, Copy } from 'lucide-react';
import api from '@/lib/axios';
import SearchRuleAuthorDrawer from '@/components/SearchRuleAuthorDrawer';
import SearchRuleTestsDrawer from '@/components/SearchRuleTestsDrawer';

const SEVERITY_COLORS = {
  critical: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400',
  high: 'bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-400',
  medium: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400',
  low: 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400',
  info: 'bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400',
};

const EMPTY_CONDITION = { field_name: '', operator: 'equals', value: '' };
const EMPTY_LEG = { count: 1, display_order: 0, distinct_field: '', min_distinct: 2, conditions: [{ ...EMPTY_CONDITION }] };

// ── ConditionRow ───────────────────────────────────────────────────────────

function ConditionRow({ cond, index, operators, onChange, onRemove }) {
  return (
    <div className="flex gap-2 items-start flex-wrap">
      <input
        value={cond.field_name}
        onChange={e => onChange(index, { ...cond, field_name: e.target.value })}
        placeholder="Wazuh field (e.g. rule.level)"
        aria-label="Field name"
        className="flex-1 min-w-32 rounded border border-border bg-background px-2 py-1 text-xs focus:outline-none focus:ring-1 focus:ring-ring"
      />
      <select
        value={cond.operator}
        onChange={e => onChange(index, { ...cond, operator: e.target.value })}
        aria-label="Operator"
        className="rounded border border-border bg-background px-2 py-1 text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
      >
        {(operators ?? []).map(op => (
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

// ── LegEditor ─────────────────────────────────────────────────────────────

function LegEditor({ leg, legIndex, operators, correlationKey, onChange, onRemove, showRemove }) {
  const hasDiversity = !!(leg.distinct_field && leg.distinct_field.trim());
  const diversityNeedsKey = hasDiversity && correlationKey === 'none';
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
            matching docs
          </label>
        </div>
        {showRemove && (
          <button
            type="button"
            onClick={() => onRemove(legIndex)}
            className="text-xs text-muted-foreground hover:text-red-600"
          >
            Remove leg
          </button>
        )}
      </div>

      <div className="space-y-1.5">
        {leg.conditions.map((cond, ci) => (
          <ConditionRow
            key={ci}
            cond={cond}
            index={ci}
            operators={operators}
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

      {/* Diversity Constraint (ADR-0009): fire only when matches span N distinct values */}
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
        {hasDiversity && (
          <p className="text-xs text-muted-foreground">
            This leg fires only when its matches span ≥ {leg.min_distinct ?? 2} distinct values of{' '}
            <code>{leg.distinct_field}</code> for the same correlation key.
          </p>
        )}
        {diversityNeedsKey && (
          <p className="text-xs text-destructive">
            A diversity constraint requires a correlation key (not “None”) to group by.
          </p>
        )}
      </div>
    </div>
  );
}

// ── RuleDrawer ─────────────────────────────────────────────────────────────

function RuleDrawer({ rule, catalog, orgs, onClose, onSaved }) {
  const isEdit = !!(rule?.id);

  const [name, setName] = useState(rule?.name ?? '');
  const [description, setDescription] = useState(rule?.description ?? '');
  const [severity, setSeverity] = useState(rule?.severity ?? 'medium');
  const [correlationKey, setCorrelationKey] = useState(rule?.correlation_key ?? 'none');
  const [windowMinutes, setWindowMinutes] = useState(rule?.window_minutes ?? 60);
  const [intervalMinutes, setIntervalMinutes] = useState(rule?.interval_minutes ?? 60);
  const [maxFindings, setMaxFindings] = useState(rule?.max_findings_per_run ?? 50);
  const [enabled, setEnabled] = useState(rule?.enabled ?? true);
  const [includeAgentless, setIncludeAgentless] = useState(rule?.include_agentless ?? false);
  // Time-of-day window (#440). Times kept as "HH:MM" for <input type=time>; days are ISO 1=Mon…7=Sun.
  const [twStart, setTwStart] = useState((rule?.time_window_start ?? '').slice(0, 5));
  const [twEnd, setTwEnd] = useState((rule?.time_window_end ?? '').slice(0, 5));
  const [twDays, setTwDays] = useState(rule?.time_window_days ?? []);
  const [twMode, setTwMode] = useState(rule?.time_window_mode ?? 'inside');
  const [orgId, setOrgId] = useState(rule === undefined || rule === null ? (orgs[0]?.id ?? '') : (rule?.organization ?? ''));
  const [legs, setLegs] = useState(
    rule?.legs?.length
      ? rule.legs.map(l => ({
          count: l.count ?? 1,
          display_order: l.display_order,
          distinct_field: l.distinct_field ?? '',
          min_distinct: l.min_distinct ?? 2,
          conditions: l.conditions.map(c => ({
            field_name: c.field_name,
            operator: c.operator,
            value: c.value,
          })),
        }))
      : [{ ...EMPTY_LEG, conditions: [{ ...EMPTY_CONDITION }] }]
  );
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  // Test / Debug run (#437): dry-run the current unsaved form values against an org.
  const [debugOrgSlug, setDebugOrgSlug] = useState(
    (orgId !== '' ? orgs.find(o => o.id === orgId)?.slug : null) ?? orgs[0]?.slug ?? ''
  );
  const [debugRunning, setDebugRunning] = useState(false);
  const [debugResult, setDebugResult] = useState(null);
  const [debugError, setDebugError] = useState(null);

  const operators = catalog?.search_operators ?? [];
  const correlationKeys = catalog?.correlation_keys ?? [];
  const severities = catalog?.severities ?? ['critical', 'high', 'medium', 'low', 'info'];

  function updateLeg(legIdx, updated) {
    setLegs(prev => prev.map((l, i) => i === legIdx ? updated : l));
  }

  function removeLeg(legIdx) {
    setLegs(prev => prev.filter((_, i) => i !== legIdx));
  }

  function addLeg() {
    setLegs(prev => [
      ...prev,
      { count: 1, display_order: prev.length, distinct_field: '', min_distinct: 2, conditions: [{ ...EMPTY_CONDITION }] },
    ]);
  }

  function buildPayload() {
    // A time window is active only when start, end, and at least one day are set;
    // otherwise send cleared (null/empty) values so the rule has no constraint.
    const windowActive = twStart && twEnd && twDays.length > 0;
    return {
      name: name.trim(),
      description: description.trim(),
      severity,
      correlation_key: correlationKey,
      window_minutes: Number(windowMinutes),
      interval_minutes: Number(intervalMinutes),
      max_findings_per_run: Number(maxFindings),
      include_agentless: includeAgentless,
      enabled,
      organization: orgId === '' ? null : orgId,
      time_window_start: windowActive ? `${twStart}:00` : null,
      time_window_end: windowActive ? `${twEnd}:00` : null,
      time_window_days: windowActive ? twDays : [],
      time_window_mode: twMode,
      legs: legs.map((l, i) => ({ ...l, display_order: i })),
    };
  }

  function toggleDay(d) {
    setTwDays(prev => prev.includes(d) ? prev.filter(x => x !== d) : [...prev, d].sort((a, b) => a - b));
  }

  function clearTimeWindow() {
    setTwStart('');
    setTwEnd('');
    setTwDays([]);
    setTwMode('inside');
  }

  async function handleDebug() {
    if (!debugOrgSlug) return;
    setDebugError(null);
    setDebugResult(null);
    setDebugRunning(true);
    try {
      const res = await api.post('/api/correlations/search-rules/debug/', {
        ...buildPayload(),
        org_slug: debugOrgSlug,
      });
      setDebugResult(res.data);
    } catch (err) {
      const data = err.response?.data;
      if (typeof data === 'object' && data !== null) {
        setDebugError(
          Object.entries(data)
            .map(([k, v]) => `${k}: ${Array.isArray(v) ? v.join(', ') : v}`)
            .join('; ')
        );
      } else {
        setDebugError('Debug run failed.');
      }
    } finally {
      setDebugRunning(false);
    }
  }

  async function handleSave() {
    setError(null);
    setSaving(true);
    const payload = buildPayload();
    try {
      let res;
      if (isEdit) {
        res = await api.patch(`/api/correlations/search-rules/${rule.id}/`, payload);
      } else {
        res = await api.post('/api/correlations/search-rules/', payload);
      }
      onSaved(res.data);
    } catch (err) {
      const data = err.response?.data;
      if (typeof data === 'object' && data !== null) {
        const msgs = Object.entries(data)
          .map(([k, v]) => `${k}: ${Array.isArray(v) ? v.join(', ') : v}`)
          .join('; ');
        setError(msgs);
      } else {
        setError('Failed to save rule.');
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
            <h2 className="text-lg font-semibold text-foreground">
              {isEdit ? 'Edit Search Rule' : 'New Scheduled Search Rule'}
            </h2>
            <p className="mt-0.5 text-xs text-muted-foreground">
              Periodically query OpenSearch and raise incidents on matching documents
            </p>
          </div>
          <button onClick={onClose} className="text-lg text-muted-foreground hover:text-foreground transition-colors">✕</button>
        </div>

        <div className="flex-1 overflow-y-auto thin-scrollbar px-6 py-5 space-y-5">

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
              <div className="col-span-2">
                <label className="block text-xs font-medium text-foreground mb-1">Organization</label>
                <select
                  value={orgId}
                  onChange={e => setOrgId(e.target.value === '' ? '' : Number(e.target.value))}
                  aria-label="Organization"
                  className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
                >
                  <option value="">System rule (all orgs)</option>
                  {orgs.map(o => (
                    <option key={o.id} value={o.id}>{o.name}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-xs font-medium text-foreground mb-1">Correlation key</label>
                <select
                  value={correlationKey}
                  onChange={e => setCorrelationKey(e.target.value)}
                  aria-label="Correlation key"
                  className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
                >
                  {correlationKeys.map(ck => (
                    <option key={ck.value} value={ck.value}>{ck.label}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-xs font-medium text-foreground mb-1">Incident severity</label>
                <select
                  value={severity}
                  onChange={e => setSeverity(e.target.value)}
                  aria-label="Severity"
                  className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
                >
                  {severities.map(s => (
                    <option key={s} value={s}>{s.charAt(0).toUpperCase() + s.slice(1)}</option>
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
                <label className="block text-xs font-medium text-foreground mb-1">Interval (minutes)</label>
                <input
                  type="number"
                  min={5}
                  value={intervalMinutes}
                  onChange={e => setIntervalMinutes(e.target.value)}
                  aria-label="Interval minutes"
                  className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-foreground mb-1">Max findings / run</label>
                <input
                  type="number"
                  min={1}
                  value={maxFindings}
                  onChange={e => setMaxFindings(e.target.value)}
                  aria-label="Max findings per run"
                  className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
                />
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
              <div className="col-span-2">
                <label className="flex items-center gap-2 text-sm text-foreground cursor-pointer">
                  <input
                    type="checkbox"
                    checked={includeAgentless}
                    onChange={e => setIncludeAgentless(e.target.checked)}
                    className="rounded"
                  />
                  Include agentless events
                </label>
                <p className="mt-1 text-xs text-muted-foreground">
                  Match events from infrastructure components (e.g. reverse proxy, firewalls) that are not linked to a registered Wazuh agent.
                </p>
              </div>
            </div>

            {correlationKey !== 'none' && legs.length > 1 && (
              <div className="rounded-md bg-blue-50 dark:bg-blue-900/20 px-3 py-2 text-xs text-blue-800 dark:text-blue-300">
                Multi-leg co-occurrence: an incident fires only when all legs have ≥ their count for the same <strong>{correlationKey}</strong> value.
              </div>
            )}
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
                operators={operators}
                correlationKey={correlationKey}
                onChange={updateLeg}
                onRemove={removeLeg}
                showRemove={legs.length > 1}
              />
            ))}
          </div>

          {/* Time-of-day window (#440): optional rule-level working-hours constraint */}
          <div className="space-y-3 border-t border-border pt-4">
            <div className="flex items-center justify-between">
              <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Time-of-day window (optional)</p>
              {(twStart || twEnd || twDays.length > 0) && (
                <button type="button" onClick={clearTimeWindow} className="text-xs text-muted-foreground hover:text-red-600">
                  Clear
                </button>
              )}
            </div>
            <p className="text-xs text-muted-foreground">
              Restrict matches to (or away from) hours of the day, evaluated in the organization's timezone.
              Leave empty for no constraint.
            </p>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs font-medium text-foreground mb-1">Start</label>
                <input
                  type="time"
                  value={twStart}
                  onChange={e => setTwStart(e.target.value)}
                  aria-label="Time window start"
                  className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-foreground mb-1">End</label>
                <input
                  type="time"
                  value={twEnd}
                  onChange={e => setTwEnd(e.target.value)}
                  aria-label="Time window end"
                  className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
                />
              </div>
            </div>
            <div>
              <label className="block text-xs font-medium text-foreground mb-1">Days</label>
              <div className="flex gap-1 flex-wrap">
                {[[1, 'Mon'], [2, 'Tue'], [3, 'Wed'], [4, 'Thu'], [5, 'Fri'], [6, 'Sat'], [7, 'Sun']].map(([d, label]) => (
                  <button
                    key={d}
                    type="button"
                    onClick={() => toggleDay(d)}
                    aria-pressed={twDays.includes(d)}
                    className={`rounded-md px-2 py-1 text-xs font-medium border transition-colors ${twDays.includes(d) ? 'bg-primary text-primary-foreground border-primary' : 'bg-background text-muted-foreground border-border hover:bg-accent'}`}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>
            <div>
              <label className="block text-xs font-medium text-foreground mb-1">Mode</label>
              <select
                value={twMode}
                onChange={e => setTwMode(e.target.value)}
                aria-label="Time window mode"
                className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
              >
                <option value="inside">Inside window (only during these hours)</option>
                <option value="outside">Outside window (only outside these hours)</option>
              </select>
            </div>
            {twStart && twEnd && twDays.length === 0 && (
              <p className="text-xs text-destructive">Select at least one day, or clear the window.</p>
            )}
          </div>

          {/* Test / Debug run (#437): dry-run the current unsaved values against an org */}
          <div className="space-y-3 border-t border-border pt-4">
            <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Test / Debug run</p>
            <p className="text-xs text-muted-foreground">
              Dry-run the current (unsaved) rule against an organization. Shows the compiled
              OpenSearch queries and responses — creates no alerts, findings, or incidents.
            </p>
            <div className="flex items-end gap-3">
              <div className="flex-1">
                <label className="block text-xs font-medium text-foreground mb-1">Organization</label>
                <select
                  value={debugOrgSlug}
                  onChange={e => setDebugOrgSlug(e.target.value)}
                  aria-label="Debug organization"
                  className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
                >
                  {orgs.map(o => (
                    <option key={o.slug} value={o.slug}>{o.name}</option>
                  ))}
                </select>
              </div>
              <button
                type="button"
                onClick={handleDebug}
                disabled={debugRunning || !debugOrgSlug || !canSave}
                className="inline-flex items-center gap-1.5 rounded-md border border-border px-4 py-2 text-sm font-medium text-foreground hover:bg-accent disabled:opacity-50 transition-colors"
              >
                <Bug className="h-4 w-4" />
                {debugRunning ? 'Running…' : 'Test / Debug run'}
              </button>
            </div>
            {debugError && (
              <div className="rounded-md bg-red-50 dark:bg-red-900/20 px-4 py-3 text-sm text-red-700 dark:text-red-400">{debugError}</div>
            )}
            {debugResult && (
              <div className="space-y-4 rounded-md border border-border bg-muted/20 p-3">
                <DebugResultView result={debugResult} />
              </div>
            )}
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
              {saving ? 'Saving…' : isEdit ? 'Save changes' : 'Create rule'}
            </button>
          </div>
        </div>

      </div>
    </div>
  );
}

// ── DebugModal ─────────────────────────────────────────────────────────────

function DebugSummary({ result }) {
  if (!result || result.error || !result.legs?.length) return null;

  const isSingle = result.mode === 'single';

  const legSummaries = result.legs.map((leg, i) => {
    const needed = leg.count ?? 1;
    if (isSingle) {
      if (leg.hit_error) return { index: i, fulfilled: false, reason: `Query error: ${leg.hit_error}`, needed };
      const total = leg.hit_response?.hits?.total?.value ?? 0;
      return { index: i, fulfilled: total >= needed, total, needed };
    } else {
      if (leg.agg_error) return { index: i, fulfilled: false, reason: `Aggregation error: ${leg.agg_error}`, needed, passing: [], all: [] };
      const buckets = leg.agg_response?.aggregations?.key_agg?.buckets ?? [];
      const passing = buckets.filter(b => b.doc_count >= needed);
      return { index: i, fulfilled: passing.length > 0, needed, passing, all: buckets };
    }
  });

  let overallFires = legSummaries.every(s => s.fulfilled);
  let firingKeys = null;
  if (!isSingle && overallFires && legSummaries.length > 1) {
    const sets = legSummaries.map(s => new Set((s.passing ?? []).map(b => b.key)));
    firingKeys = [...sets[0]].filter(k => sets.slice(1).every(s => s.has(k)));
    overallFires = firingKeys.length > 0;
  }

  return (
    <div className={`rounded-md border px-4 py-3 space-y-3 ${overallFires ? 'border-green-500/40 bg-green-50 dark:bg-green-900/15' : 'border-red-500/40 bg-red-50 dark:bg-red-900/15'}`}>
      <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Evaluation Summary</p>

      <div className="space-y-2">
        {legSummaries.map((s) => (
          <div key={s.index} className="space-y-1">
            <div className="flex items-center gap-2 text-sm">
              <span className={`inline-flex items-center rounded px-1.5 py-0.5 text-xs font-medium ${s.fulfilled ? 'bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-300' : 'bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300'}`}>
                {s.fulfilled ? '✓' : '✗'} Leg {s.index + 1}
              </span>
              {isSingle ? (
                <span className="text-xs text-muted-foreground">
                  {s.reason ?? (
                    s.fulfilled
                      ? <span className="text-green-700 dark:text-green-400">{s.total} hit{s.total !== 1 ? 's' : ''} — threshold met (≥ {s.needed})</span>
                      : <span className="text-red-700 dark:text-red-400">{s.total} hit{s.total !== 1 ? 's' : ''} — below threshold (≥ {s.needed} required)</span>
                  )}
                </span>
              ) : (
                <span className="text-xs text-muted-foreground">
                  {s.reason ?? (
                    s.fulfilled
                      ? <span className="text-green-700 dark:text-green-400">{s.passing.length} key value{s.passing.length !== 1 ? 's' : ''} met threshold (≥ {s.needed} hits each)</span>
                      : s.all.length === 0
                        ? <span className="text-red-700 dark:text-red-400">No events matched — threshold is ≥ {s.needed} hits per key value</span>
                        : <span className="text-red-700 dark:text-red-400">No key value reached ≥ {s.needed} hits (best: {Math.max(...s.all.map(b => b.doc_count))})</span>
                  )}
                </span>
              )}
            </div>
            {!isSingle && !s.reason && s.passing.length > 0 && (
              <div className="ml-16 flex flex-wrap gap-1">
                {s.passing.map(b => (
                  <span key={b.key} className="rounded bg-green-100 dark:bg-green-900/30 px-1.5 py-0.5 text-xs text-green-800 dark:text-green-300">
                    {b.key} ({b.doc_count})
                  </span>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>

      <div className={`flex items-center gap-2 pt-1 border-t ${overallFires ? 'border-green-500/30' : 'border-red-500/30'}`}>
        <span className={`text-sm font-medium ${overallFires ? 'text-green-700 dark:text-green-400' : 'text-red-700 dark:text-red-400'}`}>
          {overallFires
            ? isSingle
              ? '✓ Rule would fire — all legs met their thresholds'
              : `✓ Rule would fire for ${firingKeys?.length ?? 1} key value${(firingKeys?.length ?? 1) !== 1 ? 's' : ''}: ${firingKeys?.join(', ')}`
            : isSingle
              ? `✗ Rule would NOT fire — ${legSummaries.filter(s => !s.fulfilled).length} leg${legSummaries.filter(s => !s.fulfilled).length !== 1 ? 's' : ''} did not meet threshold`
              : '✗ Rule would NOT fire — no key value satisfied all legs'
          }
        </span>
      </div>
    </div>
  );
}

function DebugResultView({ result }) {
  if (!result) return null;
  return (
    <>
      <div className="flex gap-4 text-xs text-muted-foreground flex-wrap">
        <span>Mode: <strong className="text-foreground">{result.mode}</strong></span>
        <span>Agents: <strong className="text-foreground">{result.agent_count}</strong></span>
        <span>Window: <strong className="text-foreground">{result.window_start?.slice(0, 19).replace('T', ' ')} → {result.window_end?.slice(0, 19).replace('T', ' ')}</strong></span>
      </div>

      {result.error && (
        <div className="rounded-md bg-red-50 dark:bg-red-900/20 px-4 py-3 text-sm text-red-700 dark:text-red-400">{result.error}</div>
      )}

      <DebugSummary result={result} />

      {result.legs?.map((leg, i) => (
        <div key={i} className="space-y-3">
          <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            Leg {i + 1} {result.mode === 'multi' ? '(co-occurrence)' : ''}
          </p>

          {leg.agg_query && (
            <div className="space-y-1">
              <p className="text-xs font-medium text-foreground">Aggregation query</p>
              <pre className="rounded-md bg-muted px-3 py-2 text-xs overflow-x-auto whitespace-pre-wrap break-all">
                {JSON.stringify(leg.agg_query, null, 2)}
              </pre>
            </div>
          )}
          {leg.agg_error && (
            <p className="text-xs text-red-600">Agg error: {leg.agg_error}</p>
          )}
          {leg.agg_response && (
            <div className="space-y-1">
              <p className="text-xs font-medium text-foreground">
                Aggregation response
                {leg.agg_response?.aggregations?.key_agg?.buckets && (
                  <span className="ml-2 text-muted-foreground">({leg.agg_response.aggregations.key_agg.buckets.length} bucket(s))</span>
                )}
              </p>
              <pre className="rounded-md bg-muted px-3 py-2 text-xs overflow-x-auto whitespace-pre-wrap break-all">
                {JSON.stringify(leg.agg_response, null, 2)}
              </pre>
            </div>
          )}

          <div className="space-y-1">
            <p className="text-xs font-medium text-foreground">Hit query</p>
            <pre className="rounded-md bg-muted px-3 py-2 text-xs overflow-x-auto whitespace-pre-wrap break-all">
              {JSON.stringify(leg.hit_query, null, 2)}
            </pre>
          </div>
          {leg.hit_error && (
            <p className="text-xs text-red-600">Hit error: {leg.hit_error}</p>
          )}
          {leg.hit_response && (
            <div className="space-y-1">
              <p className="text-xs font-medium text-foreground">
                Hit response
                <span className="ml-2 text-muted-foreground">
                  ({leg.hit_response?.hits?.total?.value ?? 0} total, {leg.hit_response?.hits?.hits?.length ?? 0} returned)
                </span>
              </p>
              <pre className="rounded-md bg-muted px-3 py-2 text-xs overflow-x-auto whitespace-pre-wrap break-all">
                {JSON.stringify(leg.hit_response, null, 2)}
              </pre>
            </div>
          )}
        </div>
      ))}
    </>
  );
}

function DebugModal({ rule, orgs, onClose }) {
  const [orgSlug, setOrgSlug] = useState(orgs[0]?.slug ?? '');
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  async function runDebug() {
    if (!orgSlug) return;
    setRunning(true);
    setError(null);
    setResult(null);
    try {
      const res = await api.post(`/api/correlations/search-rules/${rule.id}/debug/`, { org_slug: orgSlug });
      setResult(res.data);
    } catch (err) {
      setError(err.response?.data?.detail || 'Debug run failed.');
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="w-full max-w-3xl max-h-[90vh] flex flex-col rounded-lg border border-border bg-card shadow-2xl">
        <div className="flex shrink-0 items-center justify-between border-b border-border px-6 py-4">
          <div>
            <h2 className="text-lg font-semibold text-foreground">Debug Run: {rule.name}</h2>
            <p className="mt-0.5 text-xs text-muted-foreground">
              Executes queries against OpenSearch without creating alerts or incidents.
            </p>
          </div>
          <button onClick={onClose} className="text-lg text-muted-foreground hover:text-foreground">✕</button>
        </div>

        <div className="shrink-0 flex items-end gap-3 px-6 py-4 border-b border-border">
          <div className="flex-1">
            <label className="block text-xs font-medium text-foreground mb-1">Organization</label>
            <select
              value={orgSlug}
              onChange={e => setOrgSlug(e.target.value)}
              className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
            >
              {orgs.map(o => (
                <option key={o.slug} value={o.slug}>{o.name}</option>
              ))}
            </select>
          </div>
          <button
            onClick={runDebug}
            disabled={running || !orgSlug}
            className="inline-flex items-center gap-1.5 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-colors"
          >
            <Bug className="h-4 w-4" />
            {running ? 'Running…' : 'Run debug'}
          </button>
        </div>

        <div className="flex-1 overflow-y-auto thin-scrollbar px-6 py-4 space-y-4">
          {error && (
            <div className="rounded-md bg-red-50 dark:bg-red-900/20 px-4 py-3 text-sm text-red-700 dark:text-red-400">{error}</div>
          )}

          <DebugResultView result={result} />

          {!result && !error && !running && (
            <p className="text-sm text-muted-foreground">Select an organization and click Run debug to see the OpenSearch queries and responses.</p>
          )}
        </div>
      </div>
    </div>
  );
}

// ── RuleRow ────────────────────────────────────────────────────────────────

function TestHealthBadge({ summary }) {
  if (!summary || summary.total === 0) {
    return <span className="inline-flex items-center rounded-full bg-gray-100 text-gray-500 dark:bg-gray-800 dark:text-gray-400 px-2 py-0.5 text-xs font-medium" title="No tests">No tests</span>;
  }
  const { total, passing, failing, error, never } = summary;
  let cls;
  if (never === total) cls = 'bg-gray-100 text-gray-500 dark:bg-gray-800 dark:text-gray-400';
  else if (failing > 0 || error > 0) cls = 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400';
  else if (passing === total) cls = 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400';
  else cls = 'bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-400';
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${cls}`} title={`${passing} passing, ${failing} failing, ${error} error, ${never} never run`}>
      Tests {passing}/{total}
    </span>
  );
}

function relativeTime(iso) {
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return '';
  const secs = Math.round((Date.now() - then) / 1000);
  if (secs < 60) return 'just now';
  const mins = Math.round(secs / 60);
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.round(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.round(hrs / 24);
  if (days < 30) return `${days}d ago`;
  const months = Math.round(days / 30);
  if (months < 12) return `${months}mo ago`;
  return `${Math.round(months / 12)}y ago`;
}

function FiringBadge({ summary }) {
  if (!summary || !summary.last_fired_at) {
    return (
      <span className="inline-flex items-center rounded-full bg-gray-100 text-gray-500 dark:bg-gray-800 dark:text-gray-400 px-2 py-0.5 text-xs font-medium" title="This rule has never fired">
        Never fired
      </span>
    );
  }
  return (
    <span
      className="inline-flex items-center rounded-full bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400 px-2 py-0.5 text-xs font-medium"
      title={`${summary.count} firing${summary.count === 1 ? '' : 's'}; last fired ${new Date(summary.last_fired_at).toLocaleString()}`}
    >
      {relativeTime(summary.last_fired_at)} · {summary.count}×
    </span>
  );
}

function RuleRow({ rule, orgs, onEdit, onClone, onToggle, onDelete, onRunNow, onDebug, onTests, onRunTests }) {
  const [toggling, setToggling] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [running, setRunning] = useState(false);
  const [runFeedback, setRunFeedback] = useState(null);
  const [runningTests, setRunningTests] = useState(false);

  async function handleRunTests() {
    setRunningTests(true);
    try { await onRunTests(rule); } finally { setRunningTests(false); }
  }

  const isSystem = rule.organization === null;
  const orgName = isSystem ? 'All orgs (system)' : (orgs.find(o => o.id === rule.organization)?.name ?? `#${rule.organization}`);

  async function handleToggle() {
    setToggling(true);
    try { await onToggle(rule); } finally { setToggling(false); }
  }

  async function handleDelete() {
    if (!window.confirm(`Delete rule "${rule.name}"?`)) return;
    setDeleting(true);
    try { await onDelete(rule); } finally { setDeleting(false); }
  }

  async function handleRunNow() {
    setRunning(true);
    setRunFeedback(null);
    try {
      const res = await onRunNow(rule);
      setRunFeedback(`Queued: ${res.task_id.slice(0, 8)}…`);
    } catch {
      setRunFeedback('Failed.');
    } finally {
      setRunning(false);
    }
  }

  return (
    <tr className="border-b border-border last:border-0 hover:bg-accent/50 transition-colors">
      <td className="px-4 py-3 font-medium text-foreground">
        {rule.name}
        {isSystem && (
          <span className="ml-2 inline-flex items-center rounded-full bg-purple-100 text-purple-800 dark:bg-purple-900/30 dark:text-purple-400 px-1.5 py-0.5 text-xs font-medium">system</span>
        )}
      </td>
      <td className="px-4 py-3 text-xs text-muted-foreground">{orgName}</td>
      <td className="px-4 py-3 text-xs text-muted-foreground">
        {rule.correlation_key === 'none' ? 'None' : rule.correlation_key}
      </td>
      <td className="px-4 py-3 text-xs text-muted-foreground">{rule.window_minutes}m / {rule.interval_minutes}m</td>
      <td className="px-4 py-3">
        <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${SEVERITY_COLORS[rule.severity] ?? ''}`}>
          {rule.severity}
        </span>
      </td>
      <td className="px-4 py-3 text-center text-xs text-muted-foreground">{rule.legs?.length ?? 0}</td>
      <td className="px-4 py-3"><TestHealthBadge summary={rule.test_summary} /></td>
      <td className="px-4 py-3"><FiringBadge summary={rule.firing_summary} /></td>
      <td className="px-4 py-3">
        <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${rule.enabled ? 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400' : 'bg-gray-100 text-gray-500'}`}>
          {rule.enabled ? 'Enabled' : 'Disabled'}
        </span>
      </td>
      <td className="px-4 py-3">
        <div className="flex gap-2 flex-wrap items-center">
          <button onClick={() => onEdit(rule)} className="rounded-md px-2 py-1 text-xs font-medium text-foreground hover:bg-accent transition-colors">Edit</button>
          <button
            onClick={() => onClone(rule)}
            className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium text-foreground hover:bg-accent transition-colors"
            title="Clone this rule — opens the builder pre-filled as a new rule"
          >
            <Copy className="h-3 w-3" />
            Clone
          </button>
          <button onClick={handleToggle} disabled={toggling} className="rounded-md px-2 py-1 text-xs font-medium text-muted-foreground hover:bg-accent disabled:opacity-50 transition-colors">
            {rule.enabled ? 'Disable' : 'Enable'}
          </button>
          <button
            onClick={handleRunNow}
            disabled={running}
            className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium text-foreground hover:bg-accent disabled:opacity-50 transition-colors"
          >
            <Play className="h-3 w-3" />
            {running ? 'Queuing…' : 'Run now'}
          </button>
          <button
            onClick={() => onDebug(rule)}
            className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium text-foreground hover:bg-accent transition-colors"
            title="Debug run — shows queries and OpenSearch responses without creating alerts"
          >
            <Bug className="h-3 w-3" />
            Debug
          </button>
          <button
            onClick={() => onTests(rule)}
            className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium text-foreground hover:bg-accent transition-colors"
            title="Manage and run detection tests for this rule"
          >
            <FlaskConical className="h-3 w-3" />
            Tests
          </button>
          <button
            onClick={handleRunTests}
            disabled={runningTests}
            className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium text-foreground hover:bg-accent disabled:opacity-50 transition-colors"
            title="Run all detection tests for this rule"
          >
            {runningTests ? 'Testing…' : 'Run tests'}
          </button>
          <button onClick={handleDelete} disabled={deleting} className="rounded-md px-2 py-1 text-xs font-medium text-red-600 hover:bg-red-50 dark:hover:bg-red-900/20 disabled:opacity-50 transition-colors">Delete</button>
          {runFeedback && (
            <span className={`text-xs ${runFeedback.startsWith('Queued') ? 'text-green-600' : 'text-destructive'}`}>{runFeedback}</span>
          )}
        </div>
      </td>
    </tr>
  );
}

// ── SearchRulesAdmin ───────────────────────────────────────────────────────

export default function SearchRulesAdmin() {
  const [rules, setRules] = useState([]);
  const [catalog, setCatalog] = useState(null);
  const [orgs, setOrgs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [drawerRule, setDrawerRule] = useState(undefined);
  const [showAiDrawer, setShowAiDrawer] = useState(false);
  const [debugRule, setDebugRule] = useState(null);
  const [testsRule, setTestsRule] = useState(null);

  useEffect(() => {
    Promise.all([
      api.get('/api/correlations/search-rules/'),
      api.get('/api/correlations/catalog/'),
      api.get('/api/security/organizations/'),
    ])
      .then(([rulesRes, catalogRes, orgsRes]) => {
        setRules(rulesRes.data);
        setCatalog(catalogRes.data);
        setOrgs(orgsRes.data);
      })
      .catch(() => setError('Failed to load data.'))
      .finally(() => setLoading(false));
  }, []);

  function handleSaved(updated) {
    setRules(prev => {
      const idx = prev.findIndex(r => r.id === updated.id);
      return idx >= 0 ? prev.map(r => r.id === updated.id ? updated : r) : [...prev, updated];
    });
    setDrawerRule(undefined);
  }

  function handleClone(rule) {
    // Seed the builder from an existing rule but strip the id so the drawer
    // treats it as a create (POST), leaving the source rule untouched. The
    // drawer's state initializer deep-copies legs/conditions, so edits to the
    // clone never mutate the original.
    const { id, ...rest } = rule;
    setDrawerRule({ ...rest, name: `Copy of ${rule.name}` });
  }

  async function handleToggle(rule) {
    try {
      const res = await api.patch(`/api/correlations/search-rules/${rule.id}/`, { enabled: !rule.enabled });
      setRules(prev => prev.map(r => r.id === rule.id ? res.data : r));
    } catch {
      setError('Failed to update rule.');
    }
  }

  async function handleDelete(rule) {
    try {
      await api.delete(`/api/correlations/search-rules/${rule.id}/`);
      setRules(prev => prev.filter(r => r.id !== rule.id));
    } catch {
      setError('Failed to delete rule.');
    }
  }

  async function handleRunNow(rule) {
    const res = await api.post(`/api/correlations/search-rules/${rule.id}/run/`);
    return res.data;
  }

  async function handleRunTests(rule) {
    try {
      const res = await api.post(`/api/correlations/search-rules/${rule.id}/tests/run-all/`);
      setRules(prev => prev.map(r => r.id === rule.id ? { ...r, test_summary: res.data.summary } : r));
    } catch {
      setError('Failed to run tests.');
    }
  }

  return (
    <div className="space-y-6 p-6">
      {drawerRule !== undefined && (
        <RuleDrawer
          rule={drawerRule || null}
          catalog={catalog}
          orgs={orgs}
          onClose={() => setDrawerRule(undefined)}
          onSaved={handleSaved}
        />
      )}
      {showAiDrawer && (
        <SearchRuleAuthorDrawer
          onClose={() => setShowAiDrawer(false)}
          onSaved={rule => {
            handleSaved(rule);
            setShowAiDrawer(false);
          }}
        />
      )}
      {debugRule && (
        <DebugModal rule={debugRule} orgs={orgs} onClose={() => setDebugRule(null)} />
      )}
      {testsRule && (
        <SearchRuleTestsDrawer rule={testsRule} onClose={() => setTestsRule(null)} />
      )}

      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-foreground">Scheduled Search Rules</h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            Periodically query OpenSearch for matching events and raise incidents.
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => setShowAiDrawer(true)}
            className="inline-flex items-center gap-1.5 rounded-md border border-border px-4 py-2 text-sm font-medium text-foreground hover:bg-accent transition-colors"
          >
            <Sparkles className="h-4 w-4" />
            Draft with AI
          </button>
          <button
            onClick={() => setDrawerRule(null)}
            className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
          >
            New rule
          </button>
        </div>
      </div>

      {error && <p className="text-sm text-red-600">{error}</p>}

      <div className="overflow-hidden rounded-lg border border-border bg-card">
        <div className="overflow-x-auto">
          <table className="w-full text-sm min-w-max">
            <thead>
              <tr className="border-b border-border">
                <th className="px-4 py-3 text-left font-medium text-muted-foreground">Name</th>
                <th className="px-4 py-3 text-left font-medium text-muted-foreground">Org</th>
                <th className="px-4 py-3 text-left font-medium text-muted-foreground">Corr. key</th>
                <th className="px-4 py-3 text-left font-medium text-muted-foreground">Window / Interval</th>
                <th className="px-4 py-3 text-left font-medium text-muted-foreground">Severity</th>
                <th className="px-4 py-3 text-center font-medium text-muted-foreground">Legs</th>
                <th className="px-4 py-3 text-left font-medium text-muted-foreground">Tests</th>
                <th className="px-4 py-3 text-left font-medium text-muted-foreground">Firings</th>
                <th className="px-4 py-3 text-left font-medium text-muted-foreground">Status</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={10} className="px-4 py-8 text-center text-muted-foreground">Loading…</td></tr>
              ) : rules.length === 0 ? (
                <tr><td colSpan={10} className="px-4 py-8 text-center text-muted-foreground">No scheduled search rules.</td></tr>
              ) : (
                rules.map(rule => (
                  <RuleRow
                    key={rule.id}
                    rule={rule}
                    orgs={orgs}
                    onEdit={setDrawerRule}
                    onClone={handleClone}
                    onToggle={handleToggle}
                    onDelete={handleDelete}
                    onRunNow={handleRunNow}
                    onDebug={setDebugRule}
                    onTests={setTestsRule}
                    onRunTests={handleRunTests}
                  />
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
