import { useState, useEffect, useMemo, useRef } from 'react';
import api from '../lib/axios';
import { useAuth } from '../context/AuthContext';
import RichTextEditor, { isBlankRichText } from './RichTextEditor';

const AUDIENCE_BADGE = {
  customer: 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400',
  internal: 'bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-400',
};

const SECTION_TITLES = {
  executive_summary: 'Executive Summary',
  incident_details: 'Incident Details',
  timeline: 'Timeline',
  iocs: 'Indicators of Compromise',
  actions_taken: 'Actions Taken',
  asset_impact: 'Asset Impact',
  recommendations: 'Recommendations',
};

// Mirror of the report stylesheet (_STYLE in backend reports.py) so the live preview
// matches the generated PDF. Keep these two in sync.
const PREVIEW_CSS = `
.rp-doc { color: #1a1a1a; font-size: 12px; }
.rp-doc h1 { font-size: 20px; margin: 8px 0 4px; }
.rp-doc h2 { font-size: 15px; color: #2b4a8b; border-bottom: 1px solid #ddd; padding-bottom: 3px; margin-top: 18px; }
.rp-doc .rp-letterhead { border-bottom: 3px solid #2b4a8b; padding-bottom: 8px; }
.rp-doc .rp-brand { font-size: 15px; font-weight: bold; color: #2b4a8b; }
.rp-doc table.details th { text-align: left; width: 140px; color: #555; padding: 2px 8px 2px 0; }
.rp-doc table.assets { border-collapse: collapse; width: 100%; }
.rp-doc table.assets th, .rp-doc table.assets td { border: 1px solid #ddd; padding: 4px 8px; }
.rp-doc ul, .rp-doc ol { padding-left: 22px; margin: 6px 0; }
.rp-doc .muted, .rp-doc .rp-muted { color: #999; font-style: italic; }
.rp-doc .richtext u, .rte u { text-decoration: underline; }
.rte-content:empty:before { content: attr(data-placeholder); color: #9ca3af; }
.rte ul, .rte ol { padding-left: 1.25rem; }
`;

function formatWhen(iso) {
  if (!iso) return '';
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

function ReportsList({ reports, onDownload, query, setQuery }) {
  const filtered = reports.filter((r) => {
    if (!query.trim()) return true;
    const q = query.toLowerCase();
    return (
      r.reference_id?.toLowerCase().includes(q) ||
      r.template_name?.toLowerCase().includes(q)
    );
  });
  if (reports.length === 0) {
    return <p className="text-sm text-muted-foreground">No reports generated yet.</p>;
  }
  return (
    <>
      {reports.length > 3 && (
        <input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search reports…"
          className="mb-2 w-full rounded border border-border bg-background px-2 py-1 text-sm"
          aria-label="Search reports"
        />
      )}
      <ul className="divide-y divide-border">
        {filtered.map((r) => (
          <li key={r.id} className="flex items-center gap-3 py-2">
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm text-foreground">
                <span className="font-mono">{r.reference_id}</span>
                <span className="ml-2 text-muted-foreground">{r.template_name}</span>
                <span className={`ml-2 rounded px-1 text-xs ${AUDIENCE_BADGE[r.audience] || ''}`}>
                  {r.audience}
                </span>
              </p>
              <p className="text-xs text-muted-foreground">
                {formatWhen(r.generated_at)}
                {r.generated_by_username && ` · ${r.generated_by_username}`}
              </p>
            </div>
            <button onClick={() => onDownload(r)} className="shrink-0 text-sm text-primary hover:underline">
              Download
            </button>
          </li>
        ))}
      </ul>
    </>
  );
}

export default function IncidentReports({ incidentId }) {
  const { user } = useAuth();
  const isStaff = user?.is_staff ?? false;

  const [reports, setReports] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [query, setQuery] = useState('');

  // Staff Editor+Preview state.
  const [templates, setTemplates] = useState([]);
  const [selectedTemplate, setSelectedTemplate] = useState('');
  const [scaffold, setScaffold] = useState(null);
  const [scaffoldLoading, setScaffoldLoading] = useState(false);
  const [blocks, setBlocks] = useState({});
  const [defaults, setDefaults] = useState({});
  const [summaryState, setSummaryState] = useState('empty'); // empty|generating|ready
  const [active, setActive] = useState(null);
  const [mobilePane, setMobilePane] = useState('edit');
  const [generating, setGenerating] = useState(false);
  const [generateError, setGenerateError] = useState(null);
  const [pastOpen, setPastOpen] = useState(false);

  const previewRefs = useRef({});

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

  useEffect(() => {
    loadReports();
    loadTemplates();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [incidentId]);

  async function loadPreview(templateId) {
    if (!templateId) return;
    setScaffoldLoading(true);
    setGenerateError(null);
    try {
      const res = await api.get(
        `/api/incidents/${incidentId}/reports/preview/?template_id=${templateId}`
      );
      setScaffold(res.data);
      const ed = res.data.editable || {};
      setDefaults(ed);
      setBlocks(ed);
      setSummaryState('empty');
      setActive(null);
    } catch {
      setScaffold(null);
      setGenerateError('Failed to load preview.');
    } finally {
      setScaffoldLoading(false);
    }
  }

  useEffect(() => {
    if (isStaff && selectedTemplate) loadPreview(selectedTemplate);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isStaff, selectedTemplate]);

  const dirty = useMemo(
    () => JSON.stringify(blocks) !== JSON.stringify(defaults),
    [blocks, defaults]
  );

  function changeTemplate(id) {
    if (id === selectedTemplate) return;
    if (dirty && !window.confirm('Discard your in-progress edits and load the new template?')) {
      return;
    }
    setSelectedTemplate(id);
  }

  function editBlock(kind, value) {
    setBlocks((b) => ({ ...b, [kind]: value }));
  }

  function revert(kind) {
    setBlocks((b) => ({ ...b, [kind]: defaults[kind] ?? '' }));
    if (kind === 'executive_summary') setSummaryState('empty');
  }

  async function generateSummary() {
    setSummaryState('generating');
    try {
      const res = await api.post(
        `/api/incidents/${incidentId}/reports/preview/summary/`,
        { template_id: Number(selectedTemplate) }
      );
      setBlocks((b) => ({ ...b, executive_summary: res.data.executive_summary || '' }));
      setSummaryState('ready');
    } catch {
      setSummaryState('empty');
      setGenerateError('Failed to generate summary.');
    }
  }

  async function handleGenerate() {
    if (!selectedTemplate) return;
    setGenerating(true);
    setGenerateError(null);
    const norm = (v) => (isBlankRichText(v) ? '' : v);
    const payload = {
      template_id: Number(selectedTemplate),
      intro_text: norm(blocks.intro_text),
      outro_text: norm(blocks.outro_text),
      recommendations_text: norm(blocks.recommendations_text),
    };
    // Only send a summary the analyst actually generated/edited — otherwise let the
    // server write it at report time (PRD #632 WYSIWYG reuse).
    if (summaryState === 'ready') payload.executive_summary = norm(blocks.executive_summary);
    try {
      await api.post(`/api/incidents/${incidentId}/reports/`, payload);
      await loadReports();
      setPastOpen(true);
    } catch (err) {
      setGenerateError(err?.response?.data?.detail || 'Failed to generate report.');
    } finally {
      setGenerating(false);
    }
  }

  async function handleDownload(report) {
    try {
      const res = await api.get(`/api/incidents/${incidentId}/reports/${report.id}/download/`);
      window.open(res.data.url, '_blank', 'noopener,noreferrer');
    } catch {
      setError('Failed to open report.');
    }
  }

  // ── Non-staff (org member): the simple read-only list, no preview. ──
  if (!isStaff) {
    return (
      <div className="space-y-3">
        <h2 className="text-base font-semibold text-foreground">Reports</h2>
        {loading ? (
          <p className="text-sm text-muted-foreground">Loading reports…</p>
        ) : error ? (
          <p className="text-sm italic text-muted-foreground">{error}</p>
        ) : (
          <ReportsList reports={reports} onDownload={handleDownload} query={query} setQuery={setQuery} />
        )}
      </div>
    );
  }

  const refused = scaffold?.refused;
  const audience = scaffold?.audience;
  const sectionKinds = (scaffold?.sections || []).map((s) => s.kind);
  const hasSummary = sectionKinds.includes('executive_summary');
  const hasRecommendations = sectionKinds.includes('recommendations');

  const editBlocksList = [
    { kind: 'intro_text', title: 'Intro' },
    ...(hasSummary ? [{ kind: 'executive_summary', title: 'Executive Summary', llm: true }] : []),
    ...(hasRecommendations ? [{ kind: 'recommendations_text', title: 'Recommendations' }] : []),
    { kind: 'outro_text', title: 'Outro' },
  ];

  return (
    <div className="space-y-3">
      <style>{PREVIEW_CSS}</style>
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-base font-semibold text-foreground">Reports</h2>
      </div>

      {/* ── Control bar ── */}
      <div className="flex flex-wrap items-center gap-2 rounded-md border border-border bg-muted/30 p-3">
        <label className="text-sm text-muted-foreground" htmlFor="report-template">Template</label>
        <select
          id="report-template"
          className="rounded border border-border bg-background px-2 py-1 text-sm"
          value={selectedTemplate}
          onChange={(e) => changeTemplate(e.target.value)}
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
        {audience && (
          <span
            className={`inline-flex items-center rounded px-2 py-0.5 text-xs ${AUDIENCE_BADGE[audience] || ''}`}
            title="The preview applies the same Audience floor as Generate"
          >
            {audience === 'customer' ? 'Customer audience floor' : 'Internal audience'}
          </span>
        )}
        {dirty && (
          <span className="inline-flex items-center gap-1 text-xs text-amber-600 dark:text-amber-400">
            <span className="h-1.5 w-1.5 rounded-full bg-amber-500" /> Unsaved edits
          </span>
        )}
        <button
          onClick={handleGenerate}
          disabled={generating || !selectedTemplate || refused}
          className="ml-auto rounded bg-primary px-3 py-1 text-sm text-primary-foreground hover:opacity-90 disabled:opacity-50"
          title={refused ? 'A customer report cannot be generated for a TLP:RED incident' : undefined}
        >
          {generating ? 'Generating…' : 'Generate report'}
        </button>
        {generateError && <span className="w-full text-sm text-destructive">{generateError}</span>}
      </div>

      {scaffoldLoading ? (
        <p className="text-sm text-muted-foreground">Loading preview…</p>
      ) : refused ? (
        <div className="rounded-md border border-destructive/40 bg-destructive/10 p-4 text-sm">
          <p className="font-medium text-destructive">Customer report unavailable at TLP:RED</p>
          <p className="mt-1 text-muted-foreground">
            This incident is marked TLP:RED. A customer-facing report can’t be previewed or
            generated until the TLP is lowered. Switch to an internal template to preview now.
          </p>
        </div>
      ) : scaffold ? (
        <>
          {/* Mobile pane toggle (side-by-side on lg+). */}
          <div className="flex gap-1 rounded-md border border-border p-1 text-sm lg:hidden">
            {['edit', 'preview'].map((p) => (
              <button
                key={p}
                onClick={() => setMobilePane(p)}
                className={`flex-1 rounded px-2 py-1 capitalize ${
                  mobilePane === p ? 'bg-primary text-primary-foreground' : 'text-muted-foreground'
                }`}
              >
                {p}
              </button>
            ))}
          </div>

          <div className="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(300px,380px)_1fr]">
            {/* ── LEFT: editable blocks ── */}
            <div className={`space-y-3 ${mobilePane === 'edit' ? '' : 'hidden'} lg:block`}>
              <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                Editable blocks
              </p>
              {editBlocksList.map((f) => (
                <EditorBlock
                  key={f.kind}
                  field={f}
                  value={blocks[f.kind] || ''}
                  isDefault={(blocks[f.kind] || '') === (defaults[f.kind] || '')}
                  active={active === f.kind}
                  summaryState={summaryState}
                  onFocus={() => {
                    setActive(f.kind);
                    previewRefs.current[f.kind]?.scrollIntoView({ block: 'center', behavior: 'smooth' });
                  }}
                  onChange={(v) => editBlock(f.kind, v)}
                  onRevert={() => revert(f.kind)}
                  onGenerate={generateSummary}
                />
              ))}
            </div>

            {/* ── RIGHT: live read-only document ── */}
            <div
              className={`rp-doc max-h-[72vh] overflow-auto rounded-md border border-border bg-white p-6 shadow-sm ${
                mobilePane === 'preview' ? '' : 'hidden'
              } lg:block`}
            >
              <div className="rp-letterhead"><span className="rp-brand">Polaris Security · Security Operations Centre</span></div>
              <h1 className="mt-2">Report preview</h1>

              <PreviewEditable
                value={blocks.intro_text} active={active === 'intro_text'} placeholder="Intro text"
                onClick={() => setActive('intro_text')} regionRef={(el) => (previewRefs.current.intro_text = el)}
              />

              {(scaffold.sections || []).map((s) => {
                if (s.kind === 'executive_summary') {
                  return (
                    <section key={s.kind}>
                      <h2>{SECTION_TITLES.executive_summary}</h2>
                      <PreviewEditable
                        value={blocks.executive_summary} active={active === 'executive_summary'}
                        placeholder={summaryState === 'generating' ? 'Generating…' : 'No summary generated yet'}
                        onClick={() => setActive('executive_summary')}
                        regionRef={(el) => (previewRefs.current.executive_summary = el)}
                      />
                    </section>
                  );
                }
                if (s.kind === 'recommendations') {
                  return (
                    <section key={s.kind}>
                      <h2>{SECTION_TITLES.recommendations}</h2>
                      <PreviewEditable
                        value={blocks.recommendations_text} active={active === 'recommendations_text'}
                        placeholder="No recommendations" onClick={() => setActive('recommendations_text')}
                        regionRef={(el) => (previewRefs.current.recommendations_text = el)}
                      />
                    </section>
                  );
                }
                return <div key={s.kind} dangerouslySetInnerHTML={{ __html: s.html || '' }} />;
              })}

              <PreviewEditable
                value={blocks.outro_text} active={active === 'outro_text'} placeholder="Outro text"
                onClick={() => setActive('outro_text')} regionRef={(el) => (previewRefs.current.outro_text = el)}
              />
            </div>
          </div>
        </>
      ) : null}

      {/* ── Demoted: previously generated reports ── */}
      <div className="rounded-md border border-border">
        <button
          onClick={() => setPastOpen((o) => !o)}
          className="flex w-full items-center justify-between px-3 py-2 text-sm font-medium"
        >
          <span>Previously generated ({reports.length})</span>
          <span className="text-muted-foreground">{pastOpen ? '▾' : '▸'}</span>
        </button>
        {pastOpen && (
          <div className="border-t border-border px-3 py-2">
            {loading ? (
              <p className="text-sm text-muted-foreground">Loading reports…</p>
            ) : error ? (
              <p className="text-sm italic text-muted-foreground">{error}</p>
            ) : (
              <ReportsList reports={reports} onDownload={handleDownload} query={query} setQuery={setQuery} />
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function EditorBlock({ field, value, isDefault, active, summaryState, onFocus, onChange, onRevert, onGenerate }) {
  const isSummary = field.kind === 'executive_summary';
  return (
    <div className={`rounded-md border p-2 transition-colors ${active ? 'border-blue-400 ring-1 ring-blue-300' : 'border-border'}`}>
      <div className="flex items-center gap-2">
        <label className="text-xs font-medium text-foreground">{field.title}</label>
        {field.llm && (
          <span className="rounded bg-violet-100 px-1 text-[10px] text-violet-700 dark:bg-violet-900/30 dark:text-violet-300">
            AI-assisted
          </span>
        )}
        {!isDefault && (
          <button onClick={onRevert} className="ml-auto text-[11px] text-muted-foreground hover:text-foreground hover:underline">
            Revert to default
          </button>
        )}
      </div>

      {isSummary && summaryState !== 'ready' ? (
        <div className="mt-1 rounded border border-dashed border-border bg-muted/40 p-2 text-xs">
          <p className="text-muted-foreground">
            Written by the assistant on demand from this report’s audience-filtered grounding,
            then editable. Frozen verbatim when you generate the report.
          </p>
          <button
            onClick={onGenerate}
            disabled={summaryState === 'generating'}
            className="mt-2 rounded bg-primary px-3 py-1 text-primary-foreground hover:opacity-90 disabled:opacity-50"
          >
            {summaryState === 'generating' ? 'Generating…' : 'Generate summary'}
          </button>
        </div>
      ) : (
        <div className="mt-1">
          <RichTextEditor
            value={value}
            placeholder={`${field.title}…`}
            minHeight={isSummary || field.kind === 'recommendations_text' ? 110 : 70}
            onFocus={onFocus}
            onChange={onChange}
          />
          {isSummary && summaryState === 'ready' && (
            <button onClick={onGenerate} className="mt-1 text-[11px] text-primary hover:underline">
              ↻ Regenerate
            </button>
          )}
        </div>
      )}
    </div>
  );
}

function PreviewEditable({ value, placeholder, active, onClick, regionRef }) {
  const blank = isBlankRichText(value);
  return (
    <div
      ref={regionRef}
      onClick={onClick}
      title="Editable block — click to focus its editor"
      className={`group my-2 cursor-pointer rounded px-2 py-1 transition-colors ${
        active ? 'bg-blue-100/70 ring-1 ring-blue-400' : 'bg-blue-50/40 hover:bg-blue-100/50'
      }`}
    >
      {blank ? (
        <span className="rp-muted">{placeholder}</span>
      ) : (
        <span className="richtext" dangerouslySetInnerHTML={{ __html: value }} />
      )}
    </div>
  );
}
