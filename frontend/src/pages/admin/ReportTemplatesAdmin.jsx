import { useState, useEffect, useMemo } from 'react';
import api from '@/lib/axios';

const AUDIENCES = [
  { value: 'customer', label: 'Customer' },
  { value: 'internal', label: 'Internal' },
];

const SORT_COLUMNS = {
  name:     { label: 'Name',     defaultOrder: 'asc' },
  audience: { label: 'Audience', defaultOrder: 'asc' },
};

function AudienceBadge({ audience }) {
  const cls = audience === 'internal'
    ? 'bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-400'
    : 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400';
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${cls}`}>
      {audience}
    </span>
  );
}

const EMPTY_FORM = {
  id: null,
  name: '',
  audience: 'customer',
  sections: [],
  intro_text: '',
  outro_text: '',
  recommendations_text: '',
};

export default function ReportTemplatesAdmin() {
  const [templates, setTemplates] = useState([]);
  const [catalog, setCatalog] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const [search, setSearch] = useState('');
  const [audienceFilter, setAudienceFilter] = useState('all');
  const [sortKey, setSortKey] = useState('name');
  const [sortOrder, setSortOrder] = useState('asc');
  const [selectedIds, setSelectedIds] = useState(new Set());
  const [bulkBusy, setBulkBusy] = useState(false);

  const [editing, setEditing] = useState(null); // form object or null
  const [formError, setFormError] = useState(null);
  const [saving, setSaving] = useState(false);

  function load() {
    setLoading(true);
    Promise.all([
      api.get('/api/incidents/report-templates/'),
      api.get('/api/incidents/report-sections/'),
    ])
      .then(([t, c]) => { setTemplates(t.data); setCatalog(c.data); })
      .catch(() => setError('Failed to load report templates.'))
      .finally(() => setLoading(false));
  }

  useEffect(() => { load(); }, []);

  const titleFor = (kind) =>
    catalog.find((c) => c.kind === kind)?.title || kind;

  const visible = useMemo(() => {
    let rows = [...templates];
    if (search.trim()) {
      const q = search.toLowerCase();
      rows = rows.filter((t) => t.name.toLowerCase().includes(q));
    }
    if (audienceFilter !== 'all') {
      rows = rows.filter((t) => t.audience === audienceFilter);
    }
    rows.sort((a, b) => {
      const av = String(a[sortKey] ?? '');
      const bv = String(b[sortKey] ?? '');
      const cmp = av.localeCompare(bv);
      return sortOrder === 'asc' ? cmp : -cmp;
    });
    return rows;
  }, [templates, search, audienceFilter, sortKey, sortOrder]);

  function toggleSort(key) {
    if (sortKey === key) {
      setSortOrder((o) => (o === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortKey(key);
      setSortOrder(SORT_COLUMNS[key].defaultOrder);
    }
  }

  function toggleSelect(id) {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }

  function toggleSelectAll() {
    setSelectedIds((prev) =>
      prev.size === visible.length ? new Set() : new Set(visible.map((t) => t.id))
    );
  }

  async function handleBulkDelete() {
    if (selectedIds.size === 0) return;
    if (!window.confirm(`Delete ${selectedIds.size} template(s)?`)) return;
    setBulkBusy(true);
    try {
      await Promise.all(
        [...selectedIds].map((id) => api.delete(`/api/incidents/report-templates/${id}/`))
      );
      setTemplates((prev) => prev.filter((t) => !selectedIds.has(t.id)));
      setSelectedIds(new Set());
    } catch {
      setError('Bulk delete failed.');
    } finally {
      setBulkBusy(false);
    }
  }

  function startCreate() {
    setFormError(null);
    setEditing({ ...EMPTY_FORM });
  }

  function startEdit(t) {
    setFormError(null);
    setEditing({
      id: t.id,
      name: t.name,
      audience: t.audience,
      sections: [...(t.sections || [])],
      intro_text: t.intro_text || '',
      outro_text: t.outro_text || '',
      recommendations_text: t.recommendations_text || '',
    });
  }

  async function handleDelete(t) {
    if (!window.confirm(`Delete "${t.name}"?`)) return;
    try {
      await api.delete(`/api/incidents/report-templates/${t.id}/`);
      setTemplates((prev) => prev.filter((x) => x.id !== t.id));
    } catch {
      setError('Delete failed.');
    }
  }

  function toggleSection(kind) {
    setEditing((f) => {
      const has = f.sections.includes(kind);
      return {
        ...f,
        sections: has ? f.sections.filter((k) => k !== kind) : [...f.sections, kind],
      };
    });
  }

  function moveSection(idx, dir) {
    setEditing((f) => {
      const next = [...f.sections];
      const j = idx + dir;
      if (j < 0 || j >= next.length) return f;
      [next[idx], next[j]] = [next[j], next[idx]];
      return { ...f, sections: next };
    });
  }

  async function handleSave(e) {
    e.preventDefault();
    if (!editing.name.trim()) {
      setFormError('Name is required.');
      return;
    }
    setSaving(true);
    setFormError(null);
    const payload = {
      name: editing.name.trim(),
      audience: editing.audience,
      sections: editing.sections,
      intro_text: editing.intro_text,
      outro_text: editing.outro_text,
      recommendations_text: editing.recommendations_text,
    };
    try {
      if (editing.id) {
        const res = await api.patch(`/api/incidents/report-templates/${editing.id}/`, payload);
        setTemplates((prev) => prev.map((t) => (t.id === editing.id ? res.data : t)));
      } else {
        const res = await api.post('/api/incidents/report-templates/', payload);
        setTemplates((prev) => [...prev, res.data]);
      }
      setEditing(null);
    } catch (err) {
      setFormError(err.response?.data?.detail || 'Failed to save template.');
    } finally {
      setSaving(false);
    }
  }

  const unselectedCatalog = editing
    ? catalog.filter((c) => !editing.sections.includes(c.kind))
    : [];

  return (
    <div className="space-y-4 p-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-foreground">Report Templates</h1>
        <button
          onClick={startCreate}
          className="rounded bg-primary px-3 py-1.5 text-sm text-primary-foreground hover:opacity-90"
        >
          + New template
        </button>
      </div>
      <p className="text-sm text-muted-foreground">
        Global, SOC-authored report templates. Audience fixes the report's visibility
        floor once, at authoring time.
      </p>

      <div className="flex flex-wrap items-center gap-2">
        <input
          type="search"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search templates…"
          className="rounded border border-border bg-background px-2 py-1 text-sm"
          aria-label="Search templates"
        />
        <select
          value={audienceFilter}
          onChange={(e) => setAudienceFilter(e.target.value)}
          className="rounded border border-border bg-background px-2 py-1 text-sm"
          aria-label="Filter by audience"
        >
          <option value="all">All audiences</option>
          {AUDIENCES.map((a) => (
            <option key={a.value} value={a.value}>{a.label}</option>
          ))}
        </select>
        {selectedIds.size > 0 && (
          <button
            onClick={handleBulkDelete}
            disabled={bulkBusy}
            className="rounded bg-destructive px-3 py-1 text-sm text-white hover:opacity-90 disabled:opacity-50"
          >
            Delete selected ({selectedIds.size})
          </button>
        )}
      </div>

      {error && <p className="text-sm text-destructive">{error}</p>}

      {loading ? (
        <p className="text-sm text-muted-foreground">Loading…</p>
      ) : visible.length === 0 ? (
        <p className="text-sm text-muted-foreground">No report templates.</p>
      ) : (
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-left text-muted-foreground">
              <th className="py-2 pr-2">
                <input
                  type="checkbox"
                  checked={selectedIds.size === visible.length && visible.length > 0}
                  onChange={toggleSelectAll}
                  aria-label="Select all"
                />
              </th>
              {Object.entries(SORT_COLUMNS).map(([key, col]) => (
                <th key={key} className="py-2 pr-2">
                  <button onClick={() => toggleSort(key)} className="hover:underline">
                    {col.label}
                    {sortKey === key ? (sortOrder === 'asc' ? ' ▲' : ' ▼') : ''}
                  </button>
                </th>
              ))}
              <th className="py-2 pr-2">Sections</th>
              <th className="py-2 pr-2" />
            </tr>
          </thead>
          <tbody>
            {visible.map((t) => (
              <tr key={t.id} className="border-b border-border">
                <td className="py-2 pr-2">
                  <input
                    type="checkbox"
                    checked={selectedIds.has(t.id)}
                    onChange={() => toggleSelect(t.id)}
                    aria-label={`Select ${t.name}`}
                  />
                </td>
                <td className="py-2 pr-2 text-foreground">{t.name}</td>
                <td className="py-2 pr-2"><AudienceBadge audience={t.audience} /></td>
                <td className="py-2 pr-2 text-muted-foreground">{(t.sections || []).length}</td>
                <td className="py-2 pr-2 text-right whitespace-nowrap">
                  <button onClick={() => startEdit(t)} className="text-primary hover:underline">
                    Edit
                  </button>
                  <button
                    onClick={() => handleDelete(t)}
                    className="ml-3 text-destructive hover:underline"
                  >
                    Delete
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {editing && (
        <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/40 p-4">
          <form
            onSubmit={handleSave}
            className="max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-lg bg-background p-5 shadow-lg space-y-4"
          >
            <h2 className="text-lg font-semibold text-foreground">
              {editing.id ? 'Edit template' : 'New template'}
            </h2>

            <div className="space-y-1">
              <label className="text-sm text-muted-foreground" htmlFor="tpl-name">Name</label>
              <input
                id="tpl-name"
                value={editing.name}
                onChange={(e) => setEditing((f) => ({ ...f, name: e.target.value }))}
                className="w-full rounded border border-border bg-background px-2 py-1 text-sm"
              />
            </div>

            <div className="space-y-1">
              <label className="text-sm text-muted-foreground" htmlFor="tpl-audience">Audience</label>
              <select
                id="tpl-audience"
                value={editing.audience}
                onChange={(e) => setEditing((f) => ({ ...f, audience: e.target.value }))}
                className="w-full rounded border border-border bg-background px-2 py-1 text-sm"
              >
                {AUDIENCES.map((a) => (
                  <option key={a.value} value={a.value}>{a.label}</option>
                ))}
              </select>
            </div>

            <div className="space-y-2">
              <span className="text-sm font-medium text-foreground">Sections (in order)</span>
              {editing.sections.length === 0 ? (
                <p className="text-sm text-muted-foreground">No sections selected yet.</p>
              ) : (
                <ol className="space-y-1">
                  {editing.sections.map((kind, idx) => (
                    <li key={kind} className="flex items-center gap-2 rounded border border-border px-2 py-1">
                      <span className="flex-1 text-sm text-foreground">{idx + 1}. {titleFor(kind)}</span>
                      <button type="button" onClick={() => moveSection(idx, -1)} aria-label={`Move ${titleFor(kind)} up`} className="text-muted-foreground hover:text-foreground">▲</button>
                      <button type="button" onClick={() => moveSection(idx, 1)} aria-label={`Move ${titleFor(kind)} down`} className="text-muted-foreground hover:text-foreground">▼</button>
                      <button type="button" onClick={() => toggleSection(kind)} aria-label={`Remove ${titleFor(kind)}`} className="text-destructive hover:underline text-sm">Remove</button>
                    </li>
                  ))}
                </ol>
              )}
              {unselectedCatalog.length > 0 && (
                <div className="flex flex-wrap gap-2 pt-1">
                  {unselectedCatalog.map((c) => (
                    <button
                      key={c.kind}
                      type="button"
                      onClick={() => toggleSection(c.kind)}
                      className="rounded border border-border px-2 py-0.5 text-xs text-foreground hover:bg-muted"
                    >
                      + {c.title}
                    </button>
                  ))}
                </div>
              )}
            </div>

            <div className="space-y-1">
              <label className="text-sm text-muted-foreground" htmlFor="tpl-intro">Intro (free text)</label>
              <textarea id="tpl-intro" rows={2} value={editing.intro_text}
                onChange={(e) => setEditing((f) => ({ ...f, intro_text: e.target.value }))}
                className="w-full rounded border border-border bg-background px-2 py-1 text-sm" />
            </div>
            <div className="space-y-1">
              <label className="text-sm text-muted-foreground" htmlFor="tpl-recs">Recommendations (free text)</label>
              <textarea id="tpl-recs" rows={2} value={editing.recommendations_text}
                onChange={(e) => setEditing((f) => ({ ...f, recommendations_text: e.target.value }))}
                className="w-full rounded border border-border bg-background px-2 py-1 text-sm" />
            </div>
            <div className="space-y-1">
              <label className="text-sm text-muted-foreground" htmlFor="tpl-outro">Outro (free text)</label>
              <textarea id="tpl-outro" rows={2} value={editing.outro_text}
                onChange={(e) => setEditing((f) => ({ ...f, outro_text: e.target.value }))}
                className="w-full rounded border border-border bg-background px-2 py-1 text-sm" />
            </div>

            {formError && <p className="text-sm text-destructive">{formError}</p>}

            <div className="flex justify-end gap-2">
              <button type="button" onClick={() => setEditing(null)}
                className="rounded border border-border px-3 py-1.5 text-sm hover:bg-muted">
                Cancel
              </button>
              <button type="submit" disabled={saving}
                className="rounded bg-primary px-3 py-1.5 text-sm text-primary-foreground hover:opacity-90 disabled:opacity-50">
                {saving ? 'Saving…' : 'Save'}
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}
