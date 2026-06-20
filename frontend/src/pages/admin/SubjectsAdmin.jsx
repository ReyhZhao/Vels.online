import { useState, useEffect, useMemo } from 'react';
import api from '@/lib/axios';

const SORT_COLUMNS = {
  name:   { label: 'Name',   defaultOrder: 'asc' },
  slug:   { label: 'Slug',   defaultOrder: 'asc' },
  status: { label: 'Status', defaultOrder: 'asc' },
};

function StatusBadge({ archived }) {
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${archived ? 'bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400' : 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400'}`}>
      {archived ? 'Archived' : 'Active'}
    </span>
  );
}

export default function SubjectsAdmin() {
  const [subjects, setSubjects] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState(null);

  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [sortKey, setSortKey] = useState('name');
  const [sortOrder, setSortOrder] = useState('asc');
  const [selectedIds, setSelectedIds] = useState(new Set());
  const [bulkBusy, setBulkBusy] = useState(false);

  useEffect(() => {
    api.get('/api/subjects/')
      .then(res => setSubjects(res.data))
      .catch(() => setError('Failed to load subjects.'))
      .finally(() => setLoading(false));
  }, []);

  async function handleCreate(e) {
    e.preventDefault();
    if (!name.trim()) return;
    setSubmitting(true);
    setFormError(null);
    try {
      const res = await api.post('/api/subjects/', { name: name.trim(), description: description.trim() });
      setSubjects(prev => [...prev, res.data].sort((a, b) => a.name.localeCompare(b.name)));
      setName('');
      setDescription('');
    } catch (err) {
      setFormError(err.response?.data?.detail || 'Failed to create subject.');
    } finally {
      setSubmitting(false);
    }
  }

  async function handleArchiveToggle(subject) {
    try {
      const res = await api.patch(`/api/subjects/${subject.id}/`, { archived: !subject.archived });
      setSubjects(prev => prev.map(s => s.id === subject.id ? res.data : s));
    } catch {
      setError('Failed to update subject.');
    }
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
    let rows = subjects.filter(s => {
      if (statusFilter === 'active' && s.archived) return false;
      if (statusFilter === 'archived' && !s.archived) return false;
      if (!q) return true;
      return (
        (s.name || '').toLowerCase().includes(q) ||
        (s.slug || '').toLowerCase().includes(q) ||
        (s.description || '').toLowerCase().includes(q)
      );
    });
    const dir = sortOrder === 'asc' ? 1 : -1;
    rows = [...rows].sort((a, b) => {
      if (sortKey === 'status') return ((a.archived ? 1 : 0) - (b.archived ? 1 : 0)) * dir;
      return (a[sortKey] || '').toString().toLowerCase()
        .localeCompare((b[sortKey] || '').toString().toLowerCase()) * dir;
    });
    return rows;
  }, [subjects, search, statusFilter, sortKey, sortOrder]);

  const visibleIds = visible.map(s => s.id);
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

  async function handleBulk(archived) {
    setBulkBusy(true);
    const ids = visible.filter(s => selectedIds.has(s.id) && s.archived !== archived).map(s => s.id);
    for (const id of ids) {
      try {
        const res = await api.patch(`/api/subjects/${id}/`, { archived });
        setSubjects(prev => prev.map(s => s.id === id ? res.data : s));
      } catch {
        setError('Failed to update one or more subjects.');
      }
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

  return (
    <div className="space-y-6 p-6">
      <h1 className="text-2xl font-semibold text-foreground">Incident Subjects</h1>

      <div className="rounded-lg border border-border bg-card p-6 space-y-4">
        <h2 className="text-base font-semibold text-foreground">Add Subject</h2>
        <form onSubmit={handleCreate} className="space-y-3">
          <div className="flex flex-col gap-3 sm:flex-row">
            <input
              type="text"
              placeholder="Subject name"
              value={name}
              onChange={e => setName(e.target.value)}
              disabled={submitting}
              className="flex-1 rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring disabled:opacity-50"
            />
            <input
              type="text"
              placeholder="Description (optional)"
              value={description}
              onChange={e => setDescription(e.target.value)}
              disabled={submitting}
              className="flex-1 rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring disabled:opacity-50"
            />
            <button
              type="submit"
              disabled={submitting || !name.trim()}
              className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-colors"
            >
              {submitting ? 'Creating…' : 'Create'}
            </button>
          </div>
          {formError && <p className="text-sm text-red-600">{formError}</p>}
        </form>
      </div>

      {error && <p className="text-sm text-red-600">{error}</p>}

      <div className="flex flex-wrap gap-2 items-center">
        <input
          type="search"
          placeholder="Search subjects…"
          value={search}
          onChange={e => setSearch(e.target.value)}
          aria-label="Search subjects"
          className="rounded-md border border-border bg-background px-3 py-1.5 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring w-52"
        />
        <select
          value={statusFilter}
          onChange={e => setStatusFilter(e.target.value)}
          aria-label="Status filter"
          className="rounded-md border border-border bg-background px-2 py-1.5 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
        >
          <option value="all">All statuses</option>
          <option value="active">Active</option>
          <option value="archived">Archived</option>
        </select>
      </div>

      {selectedIds.size > 0 && (
        <div className="flex flex-wrap items-center gap-3 rounded-md border border-border bg-card px-4 py-2">
          <span className="text-sm font-medium text-foreground">{selectedIds.size} selected</span>
          <button
            onClick={() => handleBulk(true)}
            disabled={bulkBusy}
            aria-label="Archive selected"
            className="rounded-md border border-border bg-background px-3 py-1.5 text-sm font-medium text-foreground hover:bg-accent disabled:opacity-50 transition-colors"
          >
            Archive
          </button>
          <button
            onClick={() => handleBulk(false)}
            disabled={bulkBusy}
            aria-label="Unarchive selected"
            className="rounded-md border border-border bg-background px-3 py-1.5 text-sm font-medium text-foreground hover:bg-accent disabled:opacity-50 transition-colors"
          >
            Unarchive
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
          <p className="py-8 text-center text-sm text-muted-foreground">No subjects.</p>
        ) : visible.map(s => (
          <div key={s.id} className="rounded-lg border border-border bg-card px-4 py-3 space-y-2">
            <div className="flex items-start justify-between gap-2">
              <div className="flex items-start gap-2">
                <input
                  type="checkbox"
                  checked={selectedIds.has(s.id)}
                  onChange={() => toggleSelect(s.id)}
                  aria-label={`Select ${s.name}`}
                  className="mt-1 h-4 w-4 rounded border-border"
                />
                <div>
                  <p className="font-medium text-foreground leading-snug">{s.name}</p>
                  <p className="font-mono text-xs text-muted-foreground">{s.slug}</p>
                </div>
              </div>
              <StatusBadge archived={s.archived} />
            </div>
            {s.description && <p className="text-xs text-muted-foreground">{s.description}</p>}
            <button
              onClick={() => handleArchiveToggle(s)}
              className="rounded-md px-2 py-1 text-xs font-medium text-muted-foreground hover:bg-accent transition-colors"
            >
              {s.archived ? 'Unarchive' : 'Archive'}
            </button>
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
              <SortHeader field="slug" />
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">Description</th>
              <SortHeader field="status" />
              <th className="px-4 py-3" />
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={6} className="px-4 py-8 text-center text-muted-foreground">Loading…</td>
              </tr>
            ) : visible.length === 0 ? (
              <tr>
                <td colSpan={6} className="px-4 py-8 text-center text-muted-foreground">No subjects.</td>
              </tr>
            ) : (
              visible.map(s => (
                <tr key={s.id} className="border-b border-border last:border-0">
                  <td className="px-4 py-3 w-8">
                    <input
                      type="checkbox"
                      aria-label={`Select ${s.name}`}
                      checked={selectedIds.has(s.id)}
                      onChange={() => toggleSelect(s.id)}
                      className="rounded border-border"
                    />
                  </td>
                  <td className="px-4 py-3 font-medium text-foreground">{s.name}</td>
                  <td className="px-4 py-3 font-mono text-xs text-muted-foreground">{s.slug}</td>
                  <td className="px-4 py-3 text-sm text-muted-foreground max-w-xs truncate">{s.description || '—'}</td>
                  <td className="px-4 py-3"><StatusBadge archived={s.archived} /></td>
                  <td className="px-4 py-3">
                    <button
                      onClick={() => handleArchiveToggle(s)}
                      className="rounded-md px-2 py-1 text-xs font-medium text-muted-foreground hover:bg-accent transition-colors"
                    >
                      {s.archived ? 'Unarchive' : 'Archive'}
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
