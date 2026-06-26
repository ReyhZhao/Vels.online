import { useState, useEffect, useMemo } from 'react';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from 'recharts';
import api from '../lib/axios';

// Filter params the chart forwards to /trend/. It deliberately omits `subject`
// (the chart owns the breakdown — see PRD #614) and `created_within` (the chart
// owns the time dimension), plus transient list params like page/sort/order.
const CHART_FILTER_KEYS = ['org', 'severity', 'state', 'tlp', 'closure_reason', 'q', 'tab'];

// Fixed palette assigned by sorted Subject position, so a Subject keeps its
// colour regardless of which other Subjects are present.
const SUBJECT_PALETTE = [
  '#2563eb', '#dc2626', '#16a34a', '#d97706',
  '#7c3aed', '#0891b2', '#db2777',
];
// Muted greys keep "Other" / "Unclassified" visually distinct from real Subjects.
const OTHER_COLOR = '#9ca3af';
const UNCLASSIFIED_COLOR = '#6b7280';

function colorForSubject(subject, realIndex) {
  if (subject.kind === 'other') return OTHER_COLOR;
  if (subject.kind === 'unclassified') return UNCLASSIFIED_COLOR;
  return SUBJECT_PALETTE[realIndex % SUBJECT_PALETTE.length];
}

// Short axis label (e.g. "27 May") from a YYYY-MM-DD bucket date.
function shortDate(iso) {
  const d = new Date(`${iso}T00:00:00`);
  return d.toLocaleDateString([], { day: 'numeric', month: 'short' });
}

const RANGES = [7, 30, 90];

// The drill-down value a series filters the list down to: real Subjects by id,
// "Unclassified" via the `subject=none` sentinel, "Other" is non-interactive.
function selectValue(subject) {
  if (subject.kind === 'unclassified') return 'none';
  if (subject.kind === 'real') return String(subject.subject_id);
  return null; // "Other" — no honest single filter, so non-clickable
}

export default function IncidentTrendChart({
  searchParams, collapsed = false, onToggleCollapse,
  activeSubject = null, onSelectSubject,
}) {
  const [days, setDays] = useState(30);
  const [buckets, setBuckets] = useState([]);
  const [subjects, setSubjects] = useState([]);
  const [loading, setLoading] = useState(false);

  // A stable string of only the filter params the chart cares about, so we
  // re-fetch when (and only when) those change.
  const filterKey = useMemo(() => {
    const sp = new URLSearchParams();
    CHART_FILTER_KEYS.forEach(k => {
      const v = searchParams.get(k);
      if (v) sp.set(k, v);
    });
    return sp.toString();
  }, [searchParams]);

  useEffect(() => {
    if (collapsed) return; // don't fetch while the panel is hidden
    let cancelled = false;
    setLoading(true);
    const sp = new URLSearchParams(filterKey);
    sp.set('days', String(days));
    api.get(`/api/incidents/trend/?${sp.toString()}`)
      .then(res => {
        if (cancelled) return;
        setBuckets(res.data.buckets || []);
        setSubjects(res.data.subjects || []);
      })
      .catch(() => { if (!cancelled) { setBuckets([]); setSubjects([]); } })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [filterKey, days, collapsed]);

  // Flatten each daily bucket's counts onto the row so recharts can stack them.
  const chartData = useMemo(
    () => buckets.map(b => ({ date: b.date, ...b.counts })),
    [buckets],
  );

  // Assign a colour to each series; real Subjects index into the palette. Each
  // series also carries its drill-down value and whether it is the active one.
  const colored = useMemo(() => {
    let realIndex = 0;
    return subjects.map(s => {
      const value = selectValue(s);
      return {
        ...s,
        color: colorForSubject(s, s.kind === 'real' ? realIndex++ : 0),
        value,
        clickable: value !== null,
        active: value !== null && value === activeSubject,
      };
    });
  }, [subjects, activeSubject]);

  // While a Subject is selected, dim the others so the selection reads in
  // context; the chart still shows the full breakdown (never collapses).
  const hasSelection = activeSubject != null && colored.some(s => s.active);

  function handleSelect(series) {
    if (series.clickable && onSelectSubject) onSelectSubject(series.value);
  }

  return (
    <div className="rounded-lg border border-border bg-card">
      <div className="flex items-center justify-between gap-2 px-4 py-3">
        <button
          type="button"
          onClick={onToggleCollapse}
          aria-expanded={!collapsed}
          aria-controls="incident-trend-body"
          className="flex items-center gap-2 text-sm font-medium text-foreground hover:text-foreground/80"
        >
          <span aria-hidden="true" className="text-muted-foreground">{collapsed ? '▸' : '▾'}</span>
          Incident Trend
        </button>
        {!collapsed && (
          <div className="flex gap-1">
            {RANGES.map(d => (
              <button
                key={d}
                onClick={() => setDays(d)}
                aria-pressed={days === d}
                className={`px-2 py-1 rounded text-xs font-medium transition-colors ${
                  days === d
                    ? 'bg-foreground text-background'
                    : 'text-muted-foreground hover:text-foreground hover:bg-accent'
                }`}
              >
                {d}d
              </button>
            ))}
          </div>
        )}
      </div>

      {!collapsed && (
        <div id="incident-trend-body" className="px-4 pb-4">
          {loading ? (
            <p className="py-12 text-center text-sm text-muted-foreground" role="status">
              Loading trend…
            </p>
          ) : subjects.length === 0 ? (
            <p className="py-12 text-center text-sm text-muted-foreground">
              No incidents in this window.
            </p>
          ) : (
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={chartData} margin={{ top: 4, right: 8, left: 0, bottom: 4 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
                <XAxis dataKey="date" tickFormatter={shortDate} tick={{ fontSize: 11 }} stroke="var(--muted-foreground)" minTickGap={16} />
                <YAxis allowDecimals={false} tick={{ fontSize: 11 }} stroke="var(--muted-foreground)" />
                <Tooltip
                  contentStyle={{ backgroundColor: 'var(--card)', border: '1px solid var(--border)', borderRadius: '6px' }}
                  labelStyle={{ color: 'var(--foreground)' }}
                />
                <Legend
                  wrapperStyle={{ fontSize: 12 }}
                  onClick={(entry) => {
                    const s = colored.find(c => c.key === entry?.dataKey);
                    if (s) handleSelect(s);
                  }}
                />
                {colored.map(s => (
                  <Bar
                    key={s.key}
                    dataKey={s.key}
                    stackId="incidents"
                    name={s.name}
                    fill={s.color}
                    fillOpacity={hasSelection && !s.active ? 0.25 : 1}
                    cursor={s.clickable ? 'pointer' : 'default'}
                    onClick={s.clickable ? () => handleSelect(s) : undefined}
                  />
                ))}
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>
      )}
    </div>
  );
}
