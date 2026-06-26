import { useState, useEffect, useRef, useMemo } from 'react';
import api from '@/lib/axios';
import RuleAuthorDrawer from '@/components/RuleAuthorDrawer';

// ── Constants ──────────────────────────────────────────────────────────────

const SEVERITY_COLORS = {
  critical: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400',
  high: 'bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-400',
  medium: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400',
  low: 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400',
  info: 'bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400',
};

const EMPTY_CONDITION = { field_kind: 'alert_field', field_name: '', operator: '', value: '' };
const EMPTY_LEG = { count: 1, display_order: 0, conditions: [{ ...EMPTY_CONDITION }] };

// ── LegBuilder ─────────────────────────────────────────────────────────────

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
        placeholder={cond.operator === 'in' ? 'Comma-separated values' : 'Value'}
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

// ── RuleDrawer ─────────────────────────────────────────────────────────────

function RuleDrawer({ rule, catalog, onClose, onSaved }) {
  const isEdit = !!(rule?.id);

  const [name, setName] = useState(rule?.name ?? '');
  const [description, setDescription] = useState(rule?.description ?? '');
  const [correlationKey, setCorrelationKey] = useState(rule?.correlation_key ?? 'none');
  const [windowMinutes, setWindowMinutes] = useState(rule?.window_minutes ?? 60);
  const [severity, setSeverity] = useState(rule?.severity ?? 'medium');
  const [enabled, setEnabled] = useState(rule?.enabled ?? true);
  // organization: PK for Org Rule, null for System Rule; undefined means not set by draft
  const [organization, setOrganization] = useState(
    'organization' in (rule ?? {}) ? rule.organization : undefined
  );
  const [legs, setLegs] = useState(
    rule?.legs?.length
      ? rule.legs.map(l => ({
          count: l.count,
          display_order: l.display_order,
          conditions: l.conditions.map(c => ({
            field_kind: c.field_kind,
            field_name: c.field_name,
            operator: c.operator,
            value: c.value,
          })),
        }))
      : [{ ...EMPTY_LEG, conditions: [{ ...EMPTY_CONDITION }] }]
  );
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  function updateLeg(legIdx, updated) {
    setLegs(prev => prev.map((l, i) => i === legIdx ? updated : l));
  }

  function removeLeg(legIdx) {
    setLegs(prev => prev.filter((_, i) => i !== legIdx));
  }

  function addLeg() {
    setLegs(prev => [
      ...prev,
      { count: 1, display_order: prev.length, conditions: [{ ...EMPTY_CONDITION }] },
    ]);
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
      ...(organization !== undefined ? { organization } : {}),
    };
    try {
      let res;
      if (isEdit) {
        res = await api.patch(`/api/correlations/rules/${rule.id}/`, payload);
      } else {
        res = await api.post('/api/correlations/rules/', payload);
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
              {isEdit ? 'Edit Rule' : 'New Correlation Rule'}
            </h2>
            <p className="mt-0.5 text-xs text-muted-foreground">
              Define legs and conditions for alert correlation
            </p>
          </div>
          <button onClick={onClose} className="text-lg text-muted-foreground hover:text-foreground transition-colors">✕</button>
        </div>

        <div className="flex-1 overflow-y-auto thin-scrollbar px-6 py-5 space-y-5">

          <div className="space-y-3">
            <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Rule details</p>

            {organization !== undefined && (
              <div className={`rounded-md px-3 py-2 text-xs font-medium ${organization ? 'bg-blue-50 text-blue-800 dark:bg-blue-900/20 dark:text-blue-300' : 'bg-purple-50 text-purple-800 dark:bg-purple-900/20 dark:text-purple-300'}`}>
                {organization ? `Org Rule (organization #${organization})` : 'System Rule — applies to all organizations'}
              </div>
            )}

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
                  {(catalog?.severities ?? []).map(s => (
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
              {saving ? 'Saving…' : isEdit ? 'Save changes' : 'Create rule'}
            </button>
          </div>
        </div>

      </div>
    </div>
  );
}

// ── Shared list helpers ────────────────────────────────────────────────────

const SORT_COLUMNS = {
  name:     { label: 'Name',     defaultOrder: 'asc' },
  severity: { label: 'Severity', defaultOrder: 'desc' },
  status:   { label: 'Status',   defaultOrder: 'asc' },
};

const SEVERITY_RANK = { critical: 4, high: 3, medium: 2, low: 1, info: 0 };

function SeverityBadge({ severity }) {
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${SEVERITY_COLORS[severity] ?? ''}`}>
      {severity}
    </span>
  );
}

function StatusBadge({ enabled }) {
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${enabled ? 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400' : 'bg-gray-100 text-gray-500 dark:bg-gray-800 dark:text-gray-500'}`}>
      {enabled ? 'Enabled' : 'Disabled'}
    </span>
  );
}

function KebabMenu({ label, children }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    if (!open) return;
    function onClick(e) { if (ref.current && !ref.current.contains(e.target)) setOpen(false); }
    document.addEventListener('mousedown', onClick);
    return () => document.removeEventListener('mousedown', onClick);
  }, [open]);

  return (
    <div ref={ref} className="relative inline-block text-left">
      <button
        type="button"
        onClick={() => setOpen(o => !o)}
        aria-haspopup="true"
        aria-expanded={open}
        aria-label={label}
        className="rounded-md px-2 py-1 text-base leading-none text-muted-foreground hover:bg-accent transition-colors"
      >
        ⋮
      </button>
      {open && (
        <div
          role="menu"
          className="absolute right-0 z-20 mt-1 w-36 rounded-md border border-border bg-card py-1 shadow-lg"
          onClick={() => setOpen(false)}
        >
          {children}
        </div>
      )}
    </div>
  );
}

function MenuItem({ onClick, children, danger }) {
  return (
    <button
      type="button"
      role="menuitem"
      onClick={onClick}
      className={`block w-full px-3 py-1.5 text-left text-xs font-medium hover:bg-accent transition-colors ${danger ? 'text-red-600' : 'text-foreground'}`}
    >
      {children}
    </button>
  );
}

// ── CorrelationRulesAdmin ──────────────────────────────────────────────────

export default function CorrelationRulesAdmin() {
  const [rules, setRules] = useState([]);
  const [catalog, setCatalog] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [drawerRule, setDrawerRule] = useState(undefined);
  const [ruleAuthorOpen, setRuleAuthorOpen] = useState(false);

  const [search, setSearch] = useState('');
  const [severityFilter, setSeverityFilter] = useState('all');
  const [statusFilter, setStatusFilter] = useState('all');
  const [sortKey, setSortKey] = useState('name');
  const [sortOrder, setSortOrder] = useState('asc');
  const [selectedIds, setSelectedIds] = useState(new Set());
  const [bulkBusy, setBulkBusy] = useState(false);

  useEffect(() => {
    Promise.all([
      api.get('/api/correlations/rules/'),
      api.get('/api/correlations/catalog/'),
    ])
      .then(([rulesRes, catalogRes]) => {
        setRules(rulesRes.data);
        setCatalog(catalogRes.data);
      })
      .catch(() => setError('Failed to load data.'))
      .finally(() => setLoading(false));
  }, []);

  function handleSaved(updated) {
    setRules(prev => {
      const idx = prev.findIndex(r => r.id === updated.id);
      if (idx >= 0) {
        return prev.map(r => r.id === updated.id ? updated : r);
      }
      return [...prev, updated];
    });
    setDrawerRule(undefined);
  }

  async function handleToggle(rule) {
    try {
      const res = await api.patch(`/api/correlations/rules/${rule.id}/`, { enabled: !rule.enabled });
      setRules(prev => prev.map(r => r.id === rule.id ? res.data : r));
    } catch {
      setError('Failed to update rule.');
    }
  }

  async function handleDelete(rule) {
    try {
      await api.delete(`/api/correlations/rules/${rule.id}/`);
      setRules(prev => prev.filter(r => r.id !== rule.id));
      setSelectedIds(prev => {
        if (!prev.has(rule.id)) return prev;
        const next = new Set(prev);
        next.delete(rule.id);
        return next;
      });
    } catch {
      setError('Failed to delete rule.');
    }
  }

  function handleRuleAuthorSaved(rule) {
    setRules(prev => [...prev, rule]);
    setRuleAuthorOpen(false);
  }

  function handleDeleteWithConfirm(rule) {
    if (!window.confirm(`Delete rule "${rule.name}"?`)) return;
    handleDelete(rule);
  }

  function setSort(key) {
    if (sortKey === key) {
      setSortOrder(o => (o === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortKey(key);
      setSortOrder(SORT_COLUMNS[key]?.defaultOrder ?? 'asc');
    }
  }

  const visible = useMemo(() => {
    const q = search.trim().toLowerCase();
    let rows = rules.filter(r => {
      if (severityFilter !== 'all' && r.severity !== severityFilter) return false;
      if (statusFilter === 'enabled' && !r.enabled) return false;
      if (statusFilter === 'disabled' && r.enabled) return false;
      if (!q) return true;
      return (r.name || '').toLowerCase().includes(q);
    });
    const dir = sortOrder === 'asc' ? 1 : -1;
    rows = [...rows].sort((a, b) => {
      if (sortKey === 'status') return ((a.enabled ? 1 : 0) - (b.enabled ? 1 : 0)) * dir;
      if (sortKey === 'severity') return ((SEVERITY_RANK[a.severity] ?? 0) - (SEVERITY_RANK[b.severity] ?? 0)) * dir;
      return (a.name || '').toLowerCase().localeCompare((b.name || '').toLowerCase()) * dir;
    });
    return rows;
  }, [rules, search, severityFilter, statusFilter, sortKey, sortOrder]);

  const visibleIds = visible.map(r => r.id);
  const allVisibleSelected = visibleIds.length > 0 && visibleIds.every(id => selectedIds.has(id));
  const someVisibleSelected = visibleIds.some(id => selectedIds.has(id));

  function toggleSelect(id) {
    setSelectedIds(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function toggleSelectAll() {
    if (allVisibleSelected) {
      setSelectedIds(prev => {
        const next = new Set(prev);
        visibleIds.forEach(id => next.delete(id));
        return next;
      });
    } else {
      setSelectedIds(prev => new Set([...prev, ...visibleIds]));
    }
  }

  async function handleBulkToggle(enabled) {
    setBulkBusy(true);
    const targets = visible.filter(r => selectedIds.has(r.id) && r.enabled !== enabled);
    for (const r of targets) {
      await handleToggle(r);
    }
    setSelectedIds(new Set());
    setBulkBusy(false);
  }

  async function handleBulkDelete() {
    const targets = visible.filter(r => selectedIds.has(r.id));
    if (targets.length === 0) return;
    if (!window.confirm(`Delete ${targets.length} rule${targets.length === 1 ? '' : 's'}?`)) return;
    setBulkBusy(true);
    for (const r of targets) {
      await handleDelete(r);
    }
    setSelectedIds(new Set());
    setBulkBusy(false);
  }

  function SortHeader({ field, className = '' }) {
    return (
      <th className={`px-4 py-3 text-left font-medium text-muted-foreground ${className}`}>
        <button
          onClick={() => setSort(field)}
          className="flex items-center gap-1 hover:text-foreground transition-colors"
          aria-label={`Sort by ${SORT_COLUMNS[field].label}`}
        >
          {SORT_COLUMNS[field].label}
          {sortKey === field && <span aria-hidden="true">{sortOrder === 'asc' ? '▲' : '▼'}</span>}
        </button>
      </th>
    );
  }

  function RowMenu({ rule }) {
    return (
      <KebabMenu label={`Actions for ${rule.name}`}>
        <MenuItem onClick={() => setDrawerRule(rule)}>Edit</MenuItem>
        <MenuItem onClick={() => handleToggle(rule)}>{rule.enabled ? 'Disable' : 'Enable'}</MenuItem>
        <MenuItem danger onClick={() => handleDeleteWithConfirm(rule)}>Delete</MenuItem>
      </KebabMenu>
    );
  }

  return (
    <div className="space-y-6 p-6">
      {ruleAuthorOpen && (
        <RuleAuthorDrawer
          onClose={() => setRuleAuthorOpen(false)}
          onSaved={handleRuleAuthorSaved}
        />
      )}

      {drawerRule !== undefined && (
        <RuleDrawer
          rule={drawerRule || null}
          catalog={catalog}
          onClose={() => setDrawerRule(undefined)}
          onSaved={handleSaved}
        />
      )}

      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold text-foreground">Correlation Rules</h1>
        <div className="flex gap-2">
          <button
            onClick={() => setRuleAuthorOpen(true)}
            className="rounded-md border border-border px-4 py-2 text-sm font-medium text-foreground hover:bg-accent transition-colors"
          >
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

      <div className="flex flex-wrap gap-2 items-center">
        <input
          type="search"
          placeholder="Search rules…"
          value={search}
          onChange={e => setSearch(e.target.value)}
          aria-label="Search rules"
          className="rounded-md border border-border bg-background px-3 py-1.5 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring w-52"
        />
        <select
          value={severityFilter}
          onChange={e => setSeverityFilter(e.target.value)}
          aria-label="Severity filter"
          className="rounded-md border border-border bg-background px-2 py-1.5 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
        >
          <option value="all">All severities</option>
          {(catalog?.severities ?? ['critical', 'high', 'medium', 'low', 'info']).map(s => (
            <option key={s} value={s}>{s.charAt(0).toUpperCase() + s.slice(1)}</option>
          ))}
        </select>
        <select
          value={statusFilter}
          onChange={e => setStatusFilter(e.target.value)}
          aria-label="Status filter"
          className="rounded-md border border-border bg-background px-2 py-1.5 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
        >
          <option value="all">All statuses</option>
          <option value="enabled">Enabled</option>
          <option value="disabled">Disabled</option>
        </select>
      </div>

      {selectedIds.size > 0 && (
        <div className="flex flex-wrap items-center gap-3 rounded-md border border-border bg-card px-4 py-2">
          <span className="text-sm font-medium text-foreground">{selectedIds.size} selected</span>
          <button
            onClick={() => handleBulkToggle(true)}
            disabled={bulkBusy}
            aria-label="Enable selected"
            className="rounded-md border border-border bg-background px-3 py-1.5 text-sm font-medium text-foreground hover:bg-accent disabled:opacity-50 transition-colors"
          >
            Enable
          </button>
          <button
            onClick={() => handleBulkToggle(false)}
            disabled={bulkBusy}
            aria-label="Disable selected"
            className="rounded-md border border-border bg-background px-3 py-1.5 text-sm font-medium text-foreground hover:bg-accent disabled:opacity-50 transition-colors"
          >
            Disable
          </button>
          <button
            onClick={handleBulkDelete}
            disabled={bulkBusy}
            aria-label="Delete selected"
            className="rounded-md border border-border bg-background px-3 py-1.5 text-sm font-medium text-red-600 hover:bg-red-50 dark:hover:bg-red-900/20 disabled:opacity-50 transition-colors"
          >
            Delete
          </button>
          <button
            onClick={() => setSelectedIds(new Set())}
            className="ml-auto text-xs text-muted-foreground hover:text-foreground"
          >
            Clear
          </button>
        </div>
      )}

      {/* Mobile card list */}
      <div className="sm:hidden space-y-2">
        {loading ? (
          <p className="py-8 text-center text-sm text-muted-foreground">Loading…</p>
        ) : visible.length === 0 ? (
          <p className="py-8 text-center text-sm text-muted-foreground">No correlation rules.</p>
        ) : visible.map(rule => (
          <div key={rule.id} className="rounded-lg border border-border bg-card px-4 py-3 space-y-2">
            <div className="flex items-start justify-between gap-2">
              <div className="flex items-start gap-2">
                <input
                  type="checkbox"
                  checked={selectedIds.has(rule.id)}
                  onChange={() => toggleSelect(rule.id)}
                  aria-label={`Select ${rule.name}`}
                  className="mt-1 h-4 w-4 rounded border-border"
                />
                <div>
                  <p className="font-medium text-foreground leading-snug">{rule.name}</p>
                  <p className="text-xs text-muted-foreground">
                    {rule.correlation_key === 'none' ? 'Org-wide' : rule.correlation_key} · {rule.window_minutes}m · {rule.legs?.length ?? 0} legs
                  </p>
                </div>
              </div>
              <RowMenu rule={rule} />
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <SeverityBadge severity={rule.severity} />
              <StatusBadge enabled={rule.enabled} />
            </div>
          </div>
        ))}
      </div>

      {/* Desktop table */}
      <div className="hidden sm:block overflow-hidden rounded-lg border border-border bg-card">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border">
              <th className="px-4 py-3 w-8">
                <input
                  type="checkbox"
                  aria-label="Select all"
                  checked={allVisibleSelected}
                  ref={el => { if (el) el.indeterminate = someVisibleSelected && !allVisibleSelected; }}
                  onChange={toggleSelectAll}
                  className="rounded border-border"
                />
              </th>
              <SortHeader field="name" />
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">Corr. key</th>
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">Window</th>
              <SortHeader field="severity" />
              <th className="px-4 py-3 text-center font-medium text-muted-foreground">Legs</th>
              <SortHeader field="status" />
              <th className="px-4 py-3" />
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={8} className="px-4 py-8 text-center text-muted-foreground">Loading…</td></tr>
            ) : visible.length === 0 ? (
              <tr><td colSpan={8} className="px-4 py-8 text-center text-muted-foreground">No correlation rules.</td></tr>
            ) : (
              visible.map(rule => (
                <tr key={rule.id} className="border-b border-border last:border-0 hover:bg-accent/50 transition-colors">
                  <td className="px-4 py-3 w-8">
                    <input
                      type="checkbox"
                      aria-label={`Select ${rule.name}`}
                      checked={selectedIds.has(rule.id)}
                      onChange={() => toggleSelect(rule.id)}
                      className="rounded border-border"
                    />
                  </td>
                  <td className="px-4 py-3 font-medium text-foreground">{rule.name}</td>
                  <td className="px-4 py-3 text-sm text-muted-foreground">
                    {rule.correlation_key === 'none' ? 'Org-wide' : rule.correlation_key}
                  </td>
                  <td className="px-4 py-3 text-sm text-muted-foreground">{rule.window_minutes}m</td>
                  <td className="px-4 py-3"><SeverityBadge severity={rule.severity} /></td>
                  <td className="px-4 py-3 text-center text-xs text-muted-foreground">{rule.legs?.length ?? 0}</td>
                  <td className="px-4 py-3"><StatusBadge enabled={rule.enabled} /></td>
                  <td className="px-4 py-3 text-right"><RowMenu rule={rule} /></td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
