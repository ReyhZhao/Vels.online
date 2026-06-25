import { useState, useEffect } from 'react';
import api from '../lib/axios';
import { useAuth } from '../context/AuthContext';

const AUDIENCE_BADGE = {
  customer: 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400',
  internal: 'bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-400',
};

function formatWhen(iso) {
  if (!iso) return '';
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

export default function IncidentReports({ incidentId }) {
  const { user } = useAuth();
  const isStaff = user?.is_staff ?? false;

  const [reports, setReports] = useState([]);
  const [templates, setTemplates] = useState([]);
  const [selectedTemplate, setSelectedTemplate] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [generating, setGenerating] = useState(false);
  const [generateError, setGenerateError] = useState(null);
  const [query, setQuery] = useState('');

  async function loadReports() {
    setLoading(true);
    setError(null);
    try {
      const res = await api.get(`/api/incidents/${incidentId}/reports/`);
      setReports(res.data);
    } catch {
      setError('Failed to load reports.');
    } finally {
      setLoading(false);
    }
  }

  async function loadTemplates() {
    if (!isStaff) return;
    try {
      const res = await api.get('/api/incidents/report-templates/');
      setTemplates(res.data);
      if (res.data.length > 0) setSelectedTemplate(String(res.data[0].id));
    } catch {
      // non-fatal — staff still sees the report list
    }
  }

  useEffect(() => { loadReports(); loadTemplates(); }, [incidentId]);

  async function handleGenerate() {
    if (!selectedTemplate) return;
    setGenerating(true);
    setGenerateError(null);
    try {
      await api.post(`/api/incidents/${incidentId}/reports/`, {
        template_id: Number(selectedTemplate),
      });
      await loadReports();
    } catch (err) {
      setGenerateError(
        err?.response?.data?.detail || 'Failed to generate report.'
      );
    } finally {
      setGenerating(false);
    }
  }

  async function handleDownload(report) {
    try {
      const res = await api.get(
        `/api/incidents/${incidentId}/reports/${report.id}/download/`
      );
      window.open(res.data.url, '_blank', 'noopener,noreferrer');
    } catch {
      setError('Failed to open report.');
    }
  }

  const filtered = reports.filter((r) => {
    if (!query.trim()) return true;
    const q = query.toLowerCase();
    return (
      r.reference_id?.toLowerCase().includes(q) ||
      r.template_name?.toLowerCase().includes(q)
    );
  });

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-base font-semibold text-foreground">Reports</h2>
      </div>

      {isStaff && (
        <div className="flex flex-wrap items-center gap-2 rounded-md border border-border p-3">
          <label className="text-sm text-muted-foreground" htmlFor="report-template">
            Template
          </label>
          <select
            id="report-template"
            className="rounded border border-border bg-background px-2 py-1 text-sm"
            value={selectedTemplate}
            onChange={(e) => setSelectedTemplate(e.target.value)}
            disabled={templates.length === 0}
          >
            {templates.length === 0 ? (
              <option value="">No templates available</option>
            ) : (
              templates.map((t) => (
                <option key={t.id} value={String(t.id)}>
                  {t.name} ({t.audience})
                </option>
              ))
            )}
          </select>
          <button
            onClick={handleGenerate}
            disabled={generating || !selectedTemplate}
            className="rounded bg-primary px-3 py-1 text-sm text-primary-foreground hover:opacity-90 disabled:opacity-50"
          >
            {generating ? 'Generating…' : 'Generate report'}
          </button>
          {generateError && (
            <span className="text-sm text-destructive">{generateError}</span>
          )}
        </div>
      )}

      {reports.length > 3 && (
        <input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search reports…"
          className="w-full rounded border border-border bg-background px-2 py-1 text-sm"
          aria-label="Search reports"
        />
      )}

      {loading ? (
        <p className="text-sm text-muted-foreground">Loading reports…</p>
      ) : error ? (
        <p className="text-sm text-muted-foreground italic">{error}</p>
      ) : filtered.length === 0 ? (
        <p className="text-sm text-muted-foreground">No reports generated yet.</p>
      ) : (
        <ul className="divide-y divide-border">
          {filtered.map((r) => (
            <li key={r.id} className="flex items-center gap-3 py-2">
              <div className="flex-1 min-w-0">
                <p className="text-sm text-foreground truncate">
                  <span className="font-mono">{r.reference_id}</span>
                  <span className="ml-2 text-muted-foreground">{r.template_name}</span>
                  <span
                    className={`ml-2 rounded px-1 text-xs ${AUDIENCE_BADGE[r.audience] || ''}`}
                  >
                    {r.audience}
                  </span>
                </p>
                <p className="text-xs text-muted-foreground">
                  {formatWhen(r.generated_at)}
                  {r.generated_by_username && ` · ${r.generated_by_username}`}
                </p>
              </div>
              <button
                onClick={() => handleDownload(r)}
                className="shrink-0 text-sm text-primary hover:underline"
              >
                Download
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
