import { useState, useEffect, useMemo } from 'react';
import api from '@/lib/axios';

// Staff-only Triage Lesson review queue (ADR-0030/0031, slice #662). The proposed →
// active gate: nothing the machine learns takes effect until a staff member approves it.
// Edit-on-approve is the human scrub that makes a Global Lesson safe to go fleet-wide.

const STATUSES = ['proposed', 'active', 'suspended', 'archived', 'all'];

// Human labels + styling for the closed set of per-cluster sweep decisions (#697).
const OUTCOME_META = {
  proposed: { label: 'Proposed', cls: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400' },
  skipped_insufficient_evidence: { label: 'Too few cases', cls: 'bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400' },
  skipped_covering_lesson: { label: 'Already covered', cls: 'bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400' },
  skipped_empty_guidance: { label: 'No guidance', cls: 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400' },
  distiller_error: { label: 'Distiller error', cls: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400' },
};

function fmtTs(iso) {
  if (!iso) return '—';
  return new Date(iso).toLocaleString();
}

function fmtJson(v) {
  if (typeof v === 'string') return v;
  try {
    return JSON.stringify(v, null, 2);
  } catch {
    return String(v);
  }
}

// Staff-only LLM I/O for a cluster the distiller ran on — the prompt sent, its raw
// response, and any error — so a bad or missing Lesson can be troubleshot (#697).
function ClusterIO({ cluster }) {
  const { prompt, response, error } = cluster;
  if (prompt === undefined && response === undefined && error === undefined) return null;
  return (
    <div className="mt-1">
      {error !== undefined && (
        <p className="break-words text-red-600 dark:text-red-400">Distiller error: {error}</p>
      )}
      {(prompt !== undefined || response !== undefined) && (
        <details className="mt-0.5">
          <summary className="cursor-pointer text-gray-500 hover:text-gray-700 dark:hover:text-gray-300">
            LLM input / output
          </summary>
          {prompt !== undefined && (
            <div className="mt-1">
              <p className="font-medium text-gray-500">Prompt (sent to distiller)</p>
              <pre className="mt-0.5 max-h-72 overflow-auto whitespace-pre-wrap break-words rounded bg-gray-100 p-2 text-[11px] dark:bg-gray-800">
                {fmtJson(prompt)}
              </pre>
            </div>
          )}
          {response !== undefined && (
            <div className="mt-1">
              <p className="font-medium text-gray-500">Response</p>
              <pre className="mt-0.5 max-h-72 overflow-auto whitespace-pre-wrap break-words rounded bg-gray-100 p-2 text-[11px] dark:bg-gray-800">
                {fmtJson(response)}
              </pre>
            </div>
          )}
        </details>
      )}
    </div>
  );
}

// Read-only observability into what the background distillation sweep considered on each
// run and why it did or did not propose lessons — so a zero-proposal sweep isn't invisible.
function RecentSweeps({ runs, error }) {
  const [open, setOpen] = useState(false);
  const [expanded, setExpanded] = useState(null);

  return (
    <div className="mb-5 rounded border dark:border-gray-700">
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center justify-between px-3 py-2 text-sm font-medium"
      >
        <span>Recent sweeps {runs.length > 0 && `(${runs.length})`}</span>
        <span className="text-gray-400">{open ? '▲' : '▼'}</span>
      </button>
      {open && (
        <div className="border-t px-3 py-2 dark:border-gray-700">
          {error && <div className="text-sm text-red-600">{error}</div>}
          {!error && runs.length === 0 && (
            <div className="text-sm text-gray-500">No sweeps recorded yet.</div>
          )}
          <ul className="space-y-2">
            {runs.map((run) => (
              <li key={run.id} className="rounded border p-2 text-sm dark:border-gray-700">
                <button
                  onClick={() => setExpanded((id) => (id === run.id ? null : run.id))}
                  className="flex w-full flex-wrap items-center gap-x-2 gap-y-1 text-left"
                >
                  <span className="text-gray-500">{fmtTs(run.started_at)}</span>
                  <span>·</span>
                  <span>{run.eligible_count} eligible</span>
                  <span>→ {run.cluster_count} cluster{run.cluster_count === 1 ? '' : 's'}</span>
                  <span className="font-medium">
                    → {run.proposed_count} proposed
                    {run.proposed_global_count > 0 && ` (${run.proposed_global_count} global)`}
                  </span>
                </button>
                {expanded === run.id && (
                  run.clusters.length === 0 ? (
                    <p className="mt-2 text-xs text-gray-500">No candidate clusters this run.</p>
                  ) : (
                    <ul className="mt-2 space-y-1">
                      {run.clusters.map((c, i) => {
                        const meta = OUTCOME_META[c.outcome] || { label: c.outcome, cls: 'bg-gray-100 text-gray-600' };
                        return (
                          <li key={i} className="text-xs">
                            <div className="flex flex-wrap items-center gap-2">
                              <span className={`inline-flex items-center rounded-full px-2 py-0.5 font-medium ${meta.cls}`}>
                                {meta.label}
                              </span>
                              <span className="text-gray-600 dark:text-gray-300">{c.subject}</span>
                              <span className="text-gray-400">
                                · {c.tier}{c.organization ? ` · ${c.organization}` : ''} · {c.source_kind || 'any'} · {c.evidence_count} case{c.evidence_count === 1 ? '' : 's'}
                              </span>
                            </div>
                            <ClusterIO cluster={c} />
                          </li>
                        );
                      })}
                    </ul>
                  )
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

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

  const [runs, setRuns] = useState([]);
  const [runsError, setRunsError] = useState(null);
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

  useEffect(() => {
    api.get('/api/incidents/triage-lessons/runs/')
      .then((r) => setRuns(r.data))
      .catch(() => setRunsError('Failed to load recent sweeps.'));
  }, []);

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

      <RecentSweeps runs={runs} error={runsError} />

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
