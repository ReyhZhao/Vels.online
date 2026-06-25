import { useState, useEffect, useMemo } from 'react';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from 'recharts';
import api from '../lib/axios';

// Filter params the chart forwards to /trend/. It deliberately omits `subject`
// (the chart owns the breakdown — see PRD #614) and `created_within` (the chart
// owns the time dimension), plus transient list params like page/sort/order.
const CHART_FILTER_KEYS = ['org', 'severity', 'state', 'tlp', 'q', 'tab'];

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

export default function IncidentTrendChart({ searchParams, days = 30 }) {
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
  }, [filterKey, days]);

  // Flatten each daily bucket's counts onto the row so recharts can stack them.
  const chartData = useMemo(
    () => buckets.map(b => ({ date: b.date, ...b.counts })),
    [buckets],
  );

  // Assign a colour to each series; real Subjects index into the palette.
  const colored = useMemo(() => {
    let realIndex = 0;
    return subjects.map(s => ({
      ...s,
      color: colorForSubject(s, s.kind === 'real' ? realIndex++ : 0),
    }));
  }, [subjects]);

  return (
    <div className="rounded-lg border border-border bg-card p-4">
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
            <Legend wrapperStyle={{ fontSize: 12 }} />
            {colored.map(s => (
              <Bar key={s.key} dataKey={s.key} stackId="incidents" name={s.name} fill={s.color} />
            ))}
          </BarChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}
