import { useState, useEffect, useCallback, useRef } from 'react';
import { EditorState } from '@codemirror/state';
import { EditorView, keymap, lineNumbers } from '@codemirror/view';
import { defaultKeymap } from '@codemirror/commands';
import { yaml } from '@codemirror/lang-yaml';
import { linter, lintGutter } from '@codemirror/lint';
import jsyaml from 'js-yaml';
import api from '@/lib/axios';

// ── constants ─────────────────────────────────────────────────────────────────

const VALID_SOURCES = [
  'assets.agent_name', 'assets.ip_address',
  'iocs.ip', 'iocs.domain', 'iocs.url',
  'incident.title', 'incident.severity',
];

const VALID_FORMATS = ['colon_separated', 'comma_separated', 'json_array'];

// ── incident_var_mappings linter ──────────────────────────────────────────────

function mappingsLinter(view) {
  const text = view.state.doc.toString();
  if (!text.trim()) return [];

  let parsed;
  try {
    parsed = jsyaml.load(text);
  } catch (e) {
    const pos = e.mark?.position ?? 0;
    const safePos = Math.min(pos, Math.max(0, text.length - 1));
    return [{ from: safePos, to: Math.min(safePos + 1, text.length), severity: 'error', message: e.reason || e.message }];
  }

  if (!Array.isArray(parsed)) {
    return [{ from: 0, to: text.length, severity: 'error', message: 'Must be a list of mapping objects.' }];
  }

  const diagnostics = [];
  parsed.forEach((entry) => {
    if (!entry || typeof entry !== 'object') return;

    if (!entry.var) {
      diagnostics.push({ from: 0, to: text.length, severity: 'error', message: 'Each mapping must have a "var" field.' });
      return;
    }

    if (!entry.source) {
      const varIdx = text.indexOf(String(entry.var));
      const from = Math.max(0, varIdx);
      diagnostics.push({ from, to: Math.min(from + String(entry.var).length, text.length), severity: 'error', message: `Mapping for "${entry.var}" is missing "source".` });
      return;
    }

    if (!VALID_SOURCES.includes(entry.source)) {
      const idx = text.indexOf(String(entry.source));
      const from = Math.max(0, idx < 0 ? 0 : idx);
      diagnostics.push({ from, to: Math.min(from + String(entry.source).length, text.length), severity: 'error', message: `Invalid source "${entry.source}". Valid: ${VALID_SOURCES.join(', ')}.` });
    }

    if (entry.format && !VALID_FORMATS.includes(entry.format)) {
      const idx = text.indexOf(String(entry.format));
      const from = Math.max(0, idx < 0 ? 0 : idx);
      diagnostics.push({ from, to: Math.min(from + String(entry.format).length, text.length), severity: 'error', message: `Invalid format "${entry.format}". Valid: ${VALID_FORMATS.join(', ')}.` });
    }
  });

  return diagnostics;
}

// ── YamlEditor component ──────────────────────────────────────────────────────

function YamlEditor({ value, onChange, disabled, useMappingsLinter, placeholder }) {
  const containerRef = useRef(null);
  const viewRef = useRef(null);
  const onChangeRef = useRef(onChange);
  useEffect(() => { onChangeRef.current = onChange; }, [onChange]);

  useEffect(() => {
    if (!containerRef.current) return;

    const extensions = [
      yaml(),
      lineNumbers(),
      keymap.of(defaultKeymap),
      EditorView.updateListener.of((update) => {
        if (update.docChanged) {
          onChangeRef.current(update.state.doc.toString());
        }
      }),
      EditorView.theme({
        '&': { fontSize: '12px', fontFamily: 'ui-monospace, monospace' },
        '.cm-content': { minHeight: '80px' },
        '.cm-scroller': { overflow: 'auto' },
      }),
    ];

    if (useMappingsLinter) {
      extensions.push(linter(mappingsLinter), lintGutter());
    }

    const state = EditorState.create({
      doc: value || '',
      extensions,
    });
    const view = new EditorView({ state, parent: containerRef.current });
    viewRef.current = view;

    return () => {
      view.destroy();
      viewRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [useMappingsLinter]);

  // Sync external value changes (e.g., form reset) into the editor
  useEffect(() => {
    const view = viewRef.current;
    if (!view) return;
    const current = view.state.doc.toString();
    const next = value || '';
    if (current !== next) {
      view.dispatch({ changes: { from: 0, to: current.length, insert: next } });
    }
  }, [value]);

  // Toggle read-only when disabled changes
  useEffect(() => {
    const view = viewRef.current;
    if (!view) return;
    view.dispatch({
      effects: [],
      // Re-configure editable facet
    });
    // Simpler: just set pointer-events via CSS on the container
  }, [disabled]);

  return (
    <div
      ref={containerRef}
      className={`rounded-md border border-border bg-background focus-within:ring-2 focus-within:ring-ring overflow-hidden ${disabled ? 'opacity-50 pointer-events-none' : ''}`}
      aria-label={placeholder}
    />
  );
}

// ── SemaphoreTemplateSelect ───────────────────────────────────────────────────

function SemaphoreTemplateSelect({ value, valueName, onChange, disabled }) {
  const [templates, setTemplates] = useState([]);
  const [loading, setLoading] = useState(false);
  const [fetchError, setFetchError] = useState(null);
  const [manualMode, setManualMode] = useState(false);
  const [manualName, setManualName] = useState(valueName || '');
  const [manualId, setManualId] = useState(value ? String(value) : '');

  const fetchTemplates = useCallback(async () => {
    if (templates.length > 0 || loading) return;
    setLoading(true);
    setFetchError(null);
    try {
      const res = await api.get('/api/semaphore/templates/');
      setTemplates(res.data);
    } catch {
      setFetchError('Failed to load Semaphore templates.');
      setManualMode(true);
    } finally {
      setLoading(false);
    }
  }, [templates.length, loading]);

  function handleSelectChange(e) {
    const id = Number(e.target.value);
    const tpl = templates.find(t => t.id === id);
    onChange(id || null, tpl?.name || '');
  }

  if (manualMode || fetchError) {
    return (
      <div className="space-y-1">
        {fetchError && <p className="text-xs text-red-600">{fetchError} Enter template details manually.</p>}
        <div className="flex gap-2">
          <input
            type="number"
            value={manualId}
            onChange={e => { setManualId(e.target.value); onChange(Number(e.target.value) || null, manualName); }}
            placeholder="Template ID"
            disabled={disabled}
            className="w-28 rounded-md border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring disabled:opacity-50"
          />
          <input
            value={manualName}
            onChange={e => { setManualName(e.target.value); onChange(Number(manualId) || null, e.target.value); }}
            placeholder="Template name"
            disabled={disabled}
            className="flex-1 rounded-md border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring disabled:opacity-50"
          />
          {!fetchError && (
            <button type="button" onClick={() => setManualMode(false)} className="text-xs text-muted-foreground hover:underline">
              Use dropdown
            </button>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="flex items-center gap-2">
      <select
        value={value || ''}
        onChange={handleSelectChange}
        onFocus={fetchTemplates}
        disabled={disabled || loading}
        className="flex-1 rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring disabled:opacity-50"
      >
        <option value="">{loading ? 'Loading…' : 'Select Semaphore template…'}</option>
        {templates.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
        {value && !templates.find(t => t.id === value) && (
          <option value={value}>{valueName || `Template #${value}`}</option>
        )}
      </select>
      <button type="button" onClick={() => setManualMode(true)} className="text-xs text-muted-foreground hover:underline whitespace-nowrap">
        Enter manually
      </button>
    </div>
  );
}

// ── AutomationRow ─────────────────────────────────────────────────────────────

function AutomationRow({ automation, onArchive, onUpdate }) {
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(automation.name);
  const [templateId, setTemplateId] = useState(automation.semaphore_template_id);
  const [templateName, setTemplateName] = useState(automation.semaphore_template_name || '');
  const [defaultVars, setDefaultVars] = useState(automation.default_vars || '');
  const [incidentVarMappings, setIncidentVarMappings] = useState(automation.incident_var_mappings || '');
  const [saving, setSaving] = useState(false);
  const [archiving, setArchiving] = useState(false);

  async function handleSave() {
    if (!name.trim() || !templateId) return;
    setSaving(true);
    try {
      const res = await api.patch(`/api/automations/${automation.id}/`, {
        name: name.trim(),
        semaphore_template_id: templateId,
        semaphore_template_name: templateName,
        default_vars: defaultVars.trim() || null,
        incident_var_mappings: incidentVarMappings.trim() || null,
      });
      onUpdate(res.data);
      setEditing(false);
    } finally {
      setSaving(false);
    }
  }

  async function handleArchive() {
    setArchiving(true);
    try {
      await onArchive(automation);
    } finally {
      setArchiving(false);
    }
  }

  if (editing) {
    return (
      <tr className="border-b border-border bg-accent/30">
        <td className="px-4 py-3" colSpan={4}>
          <div className="space-y-3">
            <input
              value={name}
              onChange={e => setName(e.target.value)}
              placeholder="Automation name"
              disabled={saving}
              className="w-full rounded border border-border bg-background px-2 py-1 text-sm"
            />
            <SemaphoreTemplateSelect
              value={templateId}
              valueName={templateName}
              onChange={(id, tName) => { setTemplateId(id); setTemplateName(tName); }}
              disabled={saving}
            />
            <div>
              <label className="mb-1 block text-xs font-medium text-muted-foreground">Default vars (YAML)</label>
              <YamlEditor
                value={defaultVars}
                onChange={setDefaultVars}
                disabled={saving}
                placeholder="Default vars YAML"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-muted-foreground">Incident var mappings (YAML)</label>
              <YamlEditor
                value={incidentVarMappings}
                onChange={setIncidentVarMappings}
                disabled={saving}
                useMappingsLinter
                placeholder="Incident var mappings YAML"
              />
            </div>
          </div>
        </td>
        <td className="px-4 py-3 align-top">
          <div className="flex flex-col gap-1">
            <button
              onClick={handleSave}
              disabled={saving || !name.trim() || !templateId}
              className="text-xs font-medium text-primary hover:underline disabled:opacity-50"
            >
              Save
            </button>
            <button onClick={() => setEditing(false)} className="text-xs text-muted-foreground hover:underline">
              Cancel
            </button>
          </div>
        </td>
      </tr>
    );
  }

  return (
    <tr className="border-b border-border last:border-0 hover:bg-accent/50 transition-colors">
      <td className="px-4 py-3 font-medium text-foreground">{automation.name}</td>
      <td className="px-4 py-3 text-sm text-muted-foreground">
        {automation.semaphore_template_name || `#${automation.semaphore_template_id}`}
      </td>
      <td className="px-4 py-3 text-sm text-muted-foreground">
        {automation.default_vars
          ? <code className="rounded bg-muted px-1 py-0.5 text-xs">{automation.default_vars.slice(0, 40)}{automation.default_vars.length > 40 ? '…' : ''}</code>
          : '—'}
      </td>
      <td className="px-4 py-3">
        <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${automation.archived ? 'bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400' : 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400'}`}>
          {automation.archived ? 'Archived' : 'Active'}
        </span>
      </td>
      <td className="px-4 py-3">
        <div className="flex gap-2">
          {!automation.archived && (
            <button onClick={() => setEditing(true)} className="rounded-md px-2 py-1 text-xs font-medium text-foreground hover:bg-accent transition-colors">
              Edit
            </button>
          )}
          <button
            onClick={handleArchive}
            disabled={archiving}
            className="rounded-md px-2 py-1 text-xs font-medium text-muted-foreground hover:bg-accent disabled:opacity-50 transition-colors"
          >
            {automation.archived ? 'Unarchive' : 'Archive'}
          </button>
        </div>
      </td>
    </tr>
  );
}

// ── AutomationsAdmin page ─────────────────────────────────────────────────────

export default function AutomationsAdmin() {
  const [automations, setAutomations] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const [name, setName] = useState('');
  const [templateId, setTemplateId] = useState(null);
  const [templateName, setTemplateName] = useState('');
  const [defaultVars, setDefaultVars] = useState('');
  const [incidentVarMappings, setIncidentVarMappings] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState(null);

  useEffect(() => {
    api.get('/api/automations/?include_archived=1')
      .then(res => setAutomations(res.data))
      .catch(() => setError('Failed to load automations.'))
      .finally(() => setLoading(false));
  }, []);

  async function handleCreate(e) {
    e.preventDefault();
    if (!name.trim() || !templateId) return;
    setSubmitting(true);
    setFormError(null);
    try {
      const res = await api.post('/api/automations/', {
        name: name.trim(),
        semaphore_template_id: templateId,
        semaphore_template_name: templateName,
        default_vars: defaultVars.trim() || null,
        incident_var_mappings: incidentVarMappings.trim() || null,
      });
      setAutomations(prev => [...prev, res.data]);
      setName('');
      setTemplateId(null);
      setTemplateName('');
      setDefaultVars('');
      setIncidentVarMappings('');
    } catch (err) {
      const detail = err.response?.data?.detail;
      setFormError(
        typeof detail === 'object' ? Object.values(detail).flat().join(' ') : detail || 'Failed to create automation.'
      );
    } finally {
      setSubmitting(false);
    }
  }

  async function handleArchive(automation) {
    try {
      if (automation.archived) {
        const res = await api.patch(`/api/automations/${automation.id}/`, { archived: false });
        setAutomations(prev => prev.map(a => a.id === automation.id ? { ...a, ...res.data } : a));
      } else {
        await api.delete(`/api/automations/${automation.id}/`);
        setAutomations(prev => prev.map(a => a.id === automation.id ? { ...a, archived: true } : a));
      }
    } catch {
      setError('Failed to update automation.');
    }
  }

  function handleUpdate(updated) {
    setAutomations(prev => prev.map(a => a.id === updated.id ? updated : a));
  }

  return (
    <div className="space-y-6 p-6">
      <h1 className="text-2xl font-semibold text-foreground">Automations</h1>

      <div className="rounded-lg border border-border bg-card p-6 space-y-4">
        <h2 className="text-base font-semibold text-foreground">Create Automation</h2>
        <form onSubmit={handleCreate} className="space-y-3">
          <input
            value={name}
            onChange={e => setName(e.target.value)}
            placeholder="Automation name"
            disabled={submitting}
            className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring disabled:opacity-50"
          />
          <SemaphoreTemplateSelect
            value={templateId}
            valueName={templateName}
            onChange={(id, tName) => { setTemplateId(id); setTemplateName(tName); }}
            disabled={submitting}
          />
          <div>
            <label className="mb-1 block text-xs font-medium text-muted-foreground">Default vars (optional YAML)</label>
            <YamlEditor
              value={defaultVars}
              onChange={setDefaultVars}
              disabled={submitting}
              placeholder="Default vars YAML"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-muted-foreground">Incident var mappings (optional YAML)</label>
            <YamlEditor
              value={incidentVarMappings}
              onChange={setIncidentVarMappings}
              disabled={submitting}
              useMappingsLinter
              placeholder="Incident var mappings YAML"
            />
          </div>
          <button
            type="submit"
            disabled={submitting || !name.trim() || !templateId}
            className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-colors"
          >
            {submitting ? 'Creating…' : 'Create'}
          </button>
          {formError && <p className="text-sm text-red-600">{formError}</p>}
        </form>
      </div>

      {error && <p className="text-sm text-red-600">{error}</p>}

      <div className="overflow-hidden rounded-lg border border-border bg-card">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border">
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">Name</th>
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">Semaphore Template</th>
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">Default Vars</th>
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">Status</th>
              <th className="px-4 py-3" />
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={5} className="px-4 py-8 text-center text-muted-foreground">Loading…</td></tr>
            ) : automations.length === 0 ? (
              <tr><td colSpan={5} className="px-4 py-8 text-center text-muted-foreground">No automations yet.</td></tr>
            ) : (
              automations.map(a => (
                <AutomationRow
                  key={a.id}
                  automation={a}
                  onArchive={handleArchive}
                  onUpdate={handleUpdate}
                />
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
