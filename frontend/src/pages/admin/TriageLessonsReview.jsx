import { useState, useEffect, useMemo } from 'react';
import api from '@/lib/axios';

// Staff-only Triage Lesson review queue (ADR-0030/0031, slice #662). The proposed →
// active gate: nothing the machine learns takes effect until a staff member approves it.
// Edit-on-approve is the human scrub that makes a Global Lesson safe to go fleet-wide.

const STATUSES = ['proposed', 'active', 'suspended', 'archived', 'all'];

function TierBadge({ tier }) {
  const cls = tier === 'global'
    ? 'bg-purple-100 text-purple-800 dark:bg-purple-900/30 dark:text-purple-400'
    : 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400';
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${cls}`}>
      {tier}
    </span>
  );
}

export default function TriageLessonsReview() {
  const [lessons, setLessons] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const [statusFilter, setStatusFilter] = useState('proposed');
  const [search, setSearch] = useState('');
  const [sortOrder, setSortOrder] = useState('desc');
  const [editingId, setEditingId] = useState(null);
  const [draft, setDraft] = useState('');
  const [busyId, setBusyId] = useState(null);

  function load() {
    setLoading(true);
    api.get(`/api/incidents/triage-lessons/?status=${statusFilter}`)
      .then((r) => setLessons(r.data))
      .catch(() => setError('Failed to load triage lessons.'))
      .finally(() => setLoading(false));
  }

  useEffect(() => { load(); /* eslint-disable-next-line */ }, [statusFilter]);

  const visible = useMemo(() => {
    let rows = [...lessons];
    if (search.trim()) {
      const q = search.toLowerCase();
      rows = rows.filter((l) =>
        l.guidance.toLowerCase().includes(q) ||
        (l.subject_name || '').toLowerCase().includes(q));
    }
    rows.sort((a, b) => {
      const cmp = String(a.updated_at).localeCompare(String(b.updated_at));
      return sortOrder === 'asc' ? cmp : -cmp;
    });
    return rows;
  }, [lessons, search, sortOrder]);

  async function act(lesson, action, body) {
    setBusyId(lesson.id);
    try {
      await api.post(`/api/incidents/triage-lessons/${lesson.id}/${action}/`, body || {});
      setEditingId(null);
      load();
    } catch (e) {
      setError(e?.response?.data?.detail || `Failed to ${action} lesson.`);
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className="p-4 sm:p-6 max-w-5xl mx-auto">
      <h1 className="text-xl font-semibold mb-1">Triage Lessons</h1>
      <p className="text-sm text-gray-500 dark:text-gray-400 mb-4">
        Review what the Triage pipeline has learned. Approving a lesson activates it;
        editing on approve lets you scrub a global lesson before it goes fleet-wide.
      </p>

      <div className="flex flex-col sm:flex-row gap-2 sm:items-center mb-4">
        <input
          type="search" value={search} onChange={(e) => setSearch(e.target.value)}
          placeholder="Search guidance or subject…"
          className="flex-1 rounded border px-3 py-1.5 text-sm bg-white dark:bg-gray-800 dark:border-gray-700"
        />
        <select
          value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}
          className="rounded border px-2 py-1.5 text-sm bg-white dark:bg-gray-800 dark:border-gray-700"
        >
          {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
        <button
          onClick={() => setSortOrder((o) => (o === 'asc' ? 'desc' : 'asc'))}
          className="rounded border px-2 py-1.5 text-sm dark:border-gray-700"
        >
          Updated {sortOrder === 'asc' ? '↑' : '↓'}
        </button>
      </div>

      {error && <div className="mb-3 text-sm text-red-600">{error}</div>}
      {loading ? (
        <div className="text-sm text-gray-500">Loading…</div>
      ) : visible.length === 0 ? (
        <div className="text-sm text-gray-500">No lessons in “{statusFilter}”.</div>
      ) : (
        <ul className="space-y-3">
          {visible.map((l) => (
            <li key={l.id} className="rounded border p-3 dark:border-gray-700">
              <div className="flex flex-wrap items-center gap-2 mb-1 text-xs text-gray-500">
                <TierBadge tier={l.tier} />
                <span className="font-medium text-gray-700 dark:text-gray-300">{l.subject_name}</span>
                <span>· {l.source_kind || 'any'}</span>
                <span>· {l.provenance}</span>
                {l.contradiction_count > 0 && (
                  <span className="text-amber-600">· {l.contradiction_count} contradiction(s)</span>
                )}
              </div>

              {editingId === l.id ? (
                <textarea
                  value={draft} onChange={(e) => setDraft(e.target.value)} rows={3}
                  className="w-full rounded border px-2 py-1 text-sm bg-white dark:bg-gray-800 dark:border-gray-700"
                />
              ) : (
                <p className="text-sm">{l.guidance}</p>
              )}
              {l.selector && editingId !== l.id && (
                <p className="text-xs text-gray-500 mt-1">Applies when: {l.selector}</p>
              )}
              {l.evidence_display_ids?.length > 0 && (
                <p className="text-xs text-gray-400 mt-1">
                  Evidence (staff-only): {l.evidence_display_ids.join(', ')}
                </p>
              )}

              <div className="flex flex-wrap gap-2 mt-2">
                {(l.status === 'proposed' || l.status === 'suspended') && (
                  editingId === l.id ? (
                    <>
                      <button disabled={busyId === l.id}
                        onClick={() => act(l, 'approve', { guidance: draft })}
                        className="rounded bg-green-600 text-white px-3 py-1 text-xs disabled:opacity-50">
                        Save & approve
                      </button>
                      <button onClick={() => setEditingId(null)}
                        className="rounded border px-3 py-1 text-xs dark:border-gray-700">Cancel</button>
                    </>
                  ) : (
                    <>
                      <button disabled={busyId === l.id} onClick={() => act(l, 'approve')}
                        className="rounded bg-green-600 text-white px-3 py-1 text-xs disabled:opacity-50">
                        Approve
                      </button>
                      <button onClick={() => { setEditingId(l.id); setDraft(l.guidance); }}
                        className="rounded border px-3 py-1 text-xs dark:border-gray-700">
                        Edit & approve
                      </button>
                      {l.status === 'proposed' && (
                        <button disabled={busyId === l.id} onClick={() => act(l, 'reject')}
                          className="rounded border border-red-300 text-red-600 px-3 py-1 text-xs">
                          Reject
                        </button>
                      )}
                    </>
                  )
                )}
                {l.status === 'active' && (
                  <button disabled={busyId === l.id} onClick={() => act(l, 'suspend')}
                    className="rounded border border-amber-300 text-amber-700 px-3 py-1 text-xs">
                    Suspend
                  </button>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
