import { useState, useEffect, useCallback } from 'react';
import api from '../lib/axios';

// Rule Tests workbench (PRD #439, ADR-0010): manage and run a rule's detection-as-code
// tests. Lives off the rule list row, separate from the definition-only edit drawer.

const STATUS_BADGE = {
  pass: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400',
  fail: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400',
  error: 'bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-400',
  never: 'bg-gray-100 text-gray-500 dark:bg-gray-800 dark:text-gray-400',
};

const EMPTY_FORM = { name: '', description: '', expect_fire: true, samplesText: '[\n  \n]' };

function statusLabel(s) {
  return { pass: 'Pass', fail: 'Fail', error: 'Error', never: 'Never run' }[s] || s;
}

function TestForm({ initial, onCancel, onSave, onGenerate, saving, error }) {
  const [form, setForm] = useState(initial);
  const [generating, setGenerating] = useState(false);
  const [genWarnings, setGenWarnings] = useState(null);

  async function handleGenerate() {
    setGenerating(true);
    setGenWarnings(null);
    try {
      const data = await onGenerate(form.expect_fire);
      setForm(f => ({ ...f, samplesText: JSON.stringify(data.samples, null, 2) }));
      setGenWarnings(data.warnings || []);
    } catch {
      setGenWarnings(['Generation failed.']);
    } finally {
      setGenerating(false);
    }
  }

  return (
    <div className="rounded-md border border-border bg-background p-3 space-y-3">
      <input
        value={form.name}
        onChange={e => setForm({ ...form, name: e.target.value })}
        placeholder="Test name (e.g. fires on brute force burst)"
        aria-label="Test name"
        className="w-full rounded border border-border bg-background px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
      />
      <input
        value={form.description}
        onChange={e => setForm({ ...form, description: e.target.value })}
        placeholder="Description (optional)"
        aria-label="Test description"
        className="w-full rounded border border-border bg-background px-2 py-1 text-xs focus:outline-none focus:ring-1 focus:ring-ring"
      />
      <label className="flex items-center gap-2 text-xs text-foreground">
        <input
          type="checkbox"
          checked={form.expect_fire}
          onChange={e => setForm({ ...form, expect_fire: e.target.checked })}
          aria-label="Expect fire"
        />
        Expect the rule to fire (true-positive). Uncheck for a should-not-fire (true-negative) test.
      </label>
      <div>
        <div className="flex items-center justify-between mb-1">
          <label className="block text-xs font-medium text-muted-foreground" htmlFor="samples-json">
            Sample Documents (JSON array of partial Wazuh docs)
          </label>
          <button
            type="button"
            onClick={handleGenerate}
            disabled={generating}
            className="rounded-md border border-border px-2 py-0.5 text-xs font-medium text-foreground hover:bg-accent disabled:opacity-50 transition-colors"
          >
            {generating ? 'Generating…' : 'Generate with AI'}
          </button>
        </div>
        {genWarnings && genWarnings.length > 0 && (
          <ul className="mb-1 list-disc pl-4 text-[11px] text-amber-600">
            {genWarnings.map((w, i) => <li key={i}>{w}</li>)}
          </ul>
        )}
        <textarea
          id="samples-json"
          value={form.samplesText}
          onChange={e => setForm({ ...form, samplesText: e.target.value })}
          rows={10}
          spellCheck={false}
          aria-label="Sample documents JSON"
          className="w-full rounded border border-border bg-background px-2 py-1 font-mono text-xs focus:outline-none focus:ring-1 focus:ring-ring"
        />
      </div>
      {error && <p className="text-xs text-destructive">{error}</p>}
      <div className="flex gap-2">
        <button
          type="button"
          onClick={onCancel}
          className="rounded-md border border-border px-3 py-1 text-xs font-medium text-foreground hover:bg-accent transition-colors"
        >
          Cancel
        </button>
        <button
          type="button"
          onClick={() => onSave(form)}
          disabled={saving || !form.name.trim()}
          className="rounded-md bg-primary px-3 py-1 text-xs font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-colors"
        >
          {saving ? 'Saving…' : 'Save test'}
        </button>
      </div>
    </div>
  );
}

function Diagnostics({ diag }) {
  if (!diag) return null;
  return (
    <pre className="mt-1 max-h-40 overflow-auto rounded bg-muted/50 p-2 text-[11px] text-muted-foreground">
      {JSON.stringify(diag, null, 2)}
    </pre>
  );
}

export default function SearchRuleTestsDrawer({ rule, onClose }) {
  const [tests, setTests] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [editing, setEditing] = useState(null); // 'new' | test.id | null
  const [formError, setFormError] = useState(null);
  const [saving, setSaving] = useState(false);
  const [runResults, setRunResults] = useState({}); // { [testId]: result }
  const [runningId, setRunningId] = useState(null);

  const base = `/api/correlations/search-rules/${rule.id}/tests`;

  const load = useCallback(() => {
    setLoading(true);
    api.get(`${base}/`)
      .then(res => setTests(res.data))
      .catch(() => setError('Failed to load tests.'))
      .finally(() => setLoading(false));
  }, [base]);

  useEffect(() => { load(); }, [load]);

  function parseSamples(text) {
    let parsed;
    try {
      parsed = JSON.parse(text);
    } catch {
      throw new Error('Sample Documents must be valid JSON.');
    }
    if (!Array.isArray(parsed)) throw new Error('Sample Documents must be a JSON array.');
    if (!parsed.every(d => d && typeof d === 'object' && !Array.isArray(d))) {
      throw new Error('Each sample document must be a JSON object.');
    }
    return parsed;
  }

  async function saveTest(form) {
    setFormError(null);
    let samples;
    try {
      samples = parseSamples(form.samplesText);
    } catch (e) {
      setFormError(e.message);
      return;
    }
    const payload = {
      name: form.name.trim(),
      description: form.description,
      expect_fire: form.expect_fire,
      samples,
    };
    setSaving(true);
    try {
      if (editing === 'new') {
        await api.post(`${base}/`, payload);
      } else {
        await api.patch(`${base}/${editing}/`, payload);
      }
      setEditing(null);
      load();
    } catch {
      setFormError('Failed to save test.');
    } finally {
      setSaving(false);
    }
  }

  async function generateSamples(expectFire) {
    const res = await api.post(`${base}/generate/`, { expect_fire: expectFire });
    return res.data;
  }

  async function deleteTest(id) {
    if (!window.confirm('Delete this test?')) return;
    try {
      await api.delete(`${base}/${id}/`);
      setTests(prev => prev.filter(t => t.id !== id));
    } catch {
      setError('Failed to delete test.');
    }
  }

  async function runTest(id) {
    setRunningId(id);
    try {
      const res = await api.post(`${base}/${id}/run/`);
      setRunResults(prev => ({ ...prev, [id]: res.data }));
      setTests(prev => prev.map(t => t.id === id
        ? { ...t, last_status: res.data.status, last_run_at: new Date().toISOString() }
        : t));
    } catch {
      setRunResults(prev => ({ ...prev, [id]: { status: 'error', error: 'Run failed.' } }));
    } finally {
      setRunningId(null);
    }
  }

  function startEdit(test) {
    setFormError(null);
    setEditing(test.id);
  }

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div className="absolute inset-0 bg-black/40" onClick={onClose} />
      <div className="relative flex h-full w-full max-w-2xl flex-col border-l border-border bg-card shadow-2xl">
        <div className="flex shrink-0 items-center justify-between border-b border-border px-6 py-4">
          <div>
            <h2 className="text-lg font-semibold text-foreground">Tests — {rule.name}</h2>
            <p className="mt-0.5 text-xs text-muted-foreground">
              Run synthetic sample documents through the real matcher to prove this rule fires as intended.
            </p>
          </div>
          <button onClick={onClose} aria-label="Close drawer" className="text-lg text-muted-foreground hover:text-foreground transition-colors">✕</button>
        </div>

        <div className="flex-1 overflow-y-auto px-6 py-4 space-y-3">
          {error && <p className="text-sm text-destructive">{error}</p>}
          {loading ? (
            <p className="text-sm text-muted-foreground">Loading…</p>
          ) : (
            <>
              {tests.length === 0 && editing !== 'new' && (
                <p className="text-sm text-muted-foreground">No tests yet.</p>
              )}

              {tests.map(test => (
                <div key={test.id} className="rounded-md border border-border p-3">
                  {editing === test.id ? (
                    <TestForm
                      initial={{
                        name: test.name,
                        description: test.description || '',
                        expect_fire: test.expect_fire,
                        samplesText: JSON.stringify(test.samples, null, 2),
                      }}
                      onCancel={() => setEditing(null)}
                      onSave={saveTest}
                      onGenerate={generateSamples}
                      saving={saving}
                      error={formError}
                    />
                  ) : (
                    <>
                      <div className="flex items-center justify-between gap-2 flex-wrap">
                        <div className="flex items-center gap-2">
                          <span className="font-medium text-sm text-foreground">{test.name}</span>
                          <span className="inline-flex items-center rounded-full bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400 px-1.5 py-0.5 text-[11px] font-medium">
                            {test.expect_fire ? 'should fire' : 'should not fire'}
                          </span>
                          <span className={`inline-flex items-center rounded-full px-1.5 py-0.5 text-[11px] font-medium ${STATUS_BADGE[test.last_status] || STATUS_BADGE.never}`}>
                            {statusLabel(test.last_status)}
                          </span>
                        </div>
                        <div className="flex gap-2">
                          <button onClick={() => runTest(test.id)} disabled={runningId === test.id} className="rounded-md px-2 py-1 text-xs font-medium text-foreground hover:bg-accent disabled:opacity-50 transition-colors">
                            {runningId === test.id ? 'Running…' : 'Run'}
                          </button>
                          <button onClick={() => startEdit(test)} className="rounded-md px-2 py-1 text-xs font-medium text-muted-foreground hover:bg-accent transition-colors">Edit</button>
                          <button onClick={() => deleteTest(test.id)} className="rounded-md px-2 py-1 text-xs font-medium text-red-600 hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors">Delete</button>
                        </div>
                      </div>
                      {test.description && <p className="mt-1 text-xs text-muted-foreground">{test.description}</p>}
                      {runResults[test.id] && (
                        <div className="mt-2">
                          <p className={`text-xs font-medium ${runResults[test.id].status === 'pass' ? 'text-green-600' : runResults[test.id].status === 'fail' ? 'text-destructive' : 'text-amber-600'}`}>
                            {runResults[test.id].status === 'pass' && 'Passed — rule behaved as expected.'}
                            {runResults[test.id].status === 'fail' && `Failed — rule ${runResults[test.id].fired ? 'fired' : 'did not fire'} (expected ${runResults[test.id].expect_fire ? 'fire' : 'no fire'}).`}
                            {runResults[test.id].status === 'error' && `Error — ${runResults[test.id].error || 'run failed.'}`}
                          </p>
                          <Diagnostics diag={runResults[test.id].diagnostics} />
                        </div>
                      )}
                    </>
                  )}
                </div>
              ))}

              {editing === 'new' ? (
                <TestForm
                  initial={EMPTY_FORM}
                  onCancel={() => setEditing(null)}
                  onSave={saveTest}
                  onGenerate={generateSamples}
                  saving={saving}
                  error={formError}
                />
              ) : (
                <button
                  onClick={() => { setFormError(null); setEditing('new'); }}
                  className="rounded-md border border-border px-3 py-1.5 text-sm font-medium text-foreground hover:bg-accent transition-colors"
                >
                  + Add test
                </button>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
