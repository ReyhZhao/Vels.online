import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import api from '../lib/axios';

// Threat Hunting console (ADR-0015): list past/in-progress Hunts + a New Hunt composer.
// Staff-only; a Hunt is its own surface, not embedded in any incident view.

const STATUS_CLASSES = {
  created: 'bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300',
  running: 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400',
  completed: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400',
  cancelled: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400',
  error: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400',
};

const LOOKBACKS = [7, 30, 90, 180];

export default function ThreatHuntingPage() {
  const navigate = useNavigate();
  const [hunts, setHunts] = useState([]);
  const [orgs, setOrgs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // composer state
  const [seedKind, setSeedKind] = useState('question');
  const [seedText, setSeedText] = useState('');
  const [seedUrl, setSeedUrl] = useState('');
  const [scopeAll, setScopeAll] = useState(true);
  const [scopeOrgIds, setScopeOrgIds] = useState([]);
  const [lookback, setLookback] = useState(30);
  const [submitting, setSubmitting] = useState(false);

  const loadHunts = useCallback(async () => {
    try {
      const { data } = await api.get('/api/hunts/');
      setHunts(data);
    } catch (e) {
      setError('Could not load hunts.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadHunts();
    api.get('/api/security/organizations/')
      .then(({ data }) => setOrgs(Array.isArray(data) ? data : (data.results || [])))
      .catch(() => {});
  }, [loadHunts]);

  async function submit(e) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const { data } = await api.post('/api/hunts/', {
        seed_kind: seedKind,
        seed_text: seedKind === 'question' ? seedText : '',
        seed_url: seedKind === 'url' ? seedUrl : '',
        scope_all_orgs: scopeAll,
        scope_org_ids: scopeAll ? [] : scopeOrgIds,
        lookback_days: lookback,
      });
      navigate(`/hunting/${data.id}`);
    } catch (e2) {
      setError(e2.response?.data?.detail || 'Could not start hunt.');
      setSubmitting(false);
    }
  }

  return (
    <div className="max-w-7xl mx-auto p-4 space-y-6">
      <h1 className="text-2xl font-semibold">Threat Hunting</h1>

      <form onSubmit={submit} className="border rounded-lg p-4 space-y-3 dark:border-gray-700">
        <h2 className="font-medium">New Hunt</h2>

        <div className="flex gap-4 text-sm">
          <label className="flex items-center gap-1">
            <input type="radio" checked={seedKind === 'question'} onChange={() => setSeedKind('question')} />
            Question
          </label>
          <label className="flex items-center gap-1">
            <input type="radio" checked={seedKind === 'url'} onChange={() => setSeedKind('url')} />
            Report URL
          </label>
        </div>

        {seedKind === 'question' ? (
          <textarea
            className="w-full border rounded p-2 text-sm min-h-[8rem] resize-y dark:bg-gray-800 dark:border-gray-700"
            rows={6} placeholder="e.g. Are we exposed to the XYZ ransomware campaign?"
            value={seedText} onChange={(e) => setSeedText(e.target.value)}
          />
        ) : (
          <input
            className="w-full border rounded p-2 text-sm dark:bg-gray-800 dark:border-gray-700"
            type="url" placeholder="https://vendor.example/threat-report"
            value={seedUrl} onChange={(e) => setSeedUrl(e.target.value)}
          />
        )}

        <div className="flex flex-wrap items-center gap-4 text-sm">
          <label className="flex items-center gap-1">
            <input type="checkbox" checked={scopeAll} onChange={(e) => setScopeAll(e.target.checked)} />
            All organisations
          </label>
          {!scopeAll && (
            <select
              multiple value={scopeOrgIds.map(String)}
              onChange={(e) => setScopeOrgIds(Array.from(e.target.selectedOptions).map((o) => Number(o.value)))}
              className="border rounded p-1 dark:bg-gray-800 dark:border-gray-700"
            >
              {orgs.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
            </select>
          )}
          <label className="flex items-center gap-1">
            Lookback
            <select value={lookback} onChange={(e) => setLookback(Number(e.target.value))}
                    className="border rounded p-1 dark:bg-gray-800 dark:border-gray-700">
              {LOOKBACKS.map((d) => <option key={d} value={d}>{d} days</option>)}
            </select>
          </label>
          <button type="submit" disabled={submitting}
                  className="ml-auto bg-blue-600 text-white rounded px-4 py-1.5 disabled:opacity-50">
            {submitting ? 'Starting…' : 'Start hunt'}
          </button>
        </div>
      </form>

      {error && <div className="text-sm text-red-600">{error}</div>}

      <div className="border rounded-lg dark:border-gray-700 overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 dark:bg-gray-800 text-left">
            <tr>
              <th className="p-2">Seed</th>
              <th className="p-2">Scope</th>
              <th className="p-2">Status</th>
              <th className="p-2">Findings</th>
              <th className="p-2">Incidents</th>
              <th className="p-2">Owner</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={6} className="p-4 text-center text-gray-500">Loading…</td></tr>
            ) : hunts.length === 0 ? (
              <tr><td colSpan={6} className="p-4 text-center text-gray-500">No hunts yet.</td></tr>
            ) : hunts.map((h) => (
              <tr key={h.id} className="border-t dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-800 cursor-pointer"
                  onClick={() => navigate(`/hunting/${h.id}`)}>
                <td className="p-2 max-w-xs truncate">{h.title}</td>
                <td className="p-2">{h.scope_all_orgs ? 'All orgs' : 'Selected'}</td>
                <td className="p-2">
                  <span className={`px-2 py-0.5 rounded text-xs ${STATUS_CLASSES[h.status] || ''}`}>{h.status}</span>
                </td>
                <td className="p-2">{h.finding_count}</td>
                <td className="p-2">{h.spawned_incident_count}</td>
                <td className="p-2">{h.owner_username || '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
