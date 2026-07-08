import { useState, useEffect, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from 'recharts';
import api from '../../lib/axios';
import ChartCard from './ChartCard';
import {
  CATEGORICAL, NEUTRAL_SERIES, NEUTRAL_SERIES_DIM,
  GRID_STROKE, AXIS_TICK, SURFACE, TOOLTIP_STYLE,
} from './palette';

function shortDate(iso) {
  const d = new Date(`${iso}T00:00:00`);
  return d.toLocaleDateString([], { day: 'numeric', month: 'short' });
}

// Colors follow the Subject's fixed sorted position, never the current filter,
// and synthetic series (Other / Unclassified) stay neutral gray.
function seriesColor(subject, realIndex) {
  if (subject.kind === 'other') return NEUTRAL_SERIES;
  if (subject.kind === 'unclassified') return NEUTRAL_SERIES_DIM;
  return CATEGORICAL[realIndex % CATEGORICAL.length];
}

/**
 * Incidents created per day, stacked by Subject. Clicking a series (bar
 * segment or legend entry) drills into the incident list filtered to that
 * Subject. Range comes from the page-level filter row.
 */
export default function IncidentTrendCard({ orgSlug, days }) {
  const navigate = useNavigate();
  const [data, setData] = useState({ buckets: [], subjects: [] });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!orgSlug) return;
    let cancelled = false;
    setLoading(true);
    // The dashboard trend reflects every incident regardless of state
    // (including closed), unlike the incident-list chart which honours the
    // active list filters and defaults to excluding closed.
    api.get('/api/incidents/trend/', { params: { org: orgSlug, days, include_closed: 1 } })
      .then(res => { if (!cancelled) setData({ buckets: res.data.buckets || [], subjects: res.data.subjects || [] }); })
      .catch(() => { if (!cancelled) setData({ buckets: [], subjects: [] }); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [orgSlug, days]);

  const chartData = useMemo(
    () => data.buckets.map(b => ({ date: b.date, ...b.counts })),
    [data.buckets],
  );

  const series = useMemo(() => {
    let realIndex = 0;
    return data.subjects.map(s => ({
      ...s,
      color: seriesColor(s, s.kind === 'real' ? realIndex++ : 0),
      filter: s.kind === 'real' ? String(s.subject_id) : s.kind === 'unclassified' ? 'none' : null,
    }));
  }, [data.subjects]);

  function drillDown(key) {
    const s = series.find(x => x.key === key);
    if (s?.filter) navigate(`/incidents?subject=${s.filter}`);
  }

  const totals = useMemo(() => {
    const t = {};
    data.buckets.forEach(b => {
      Object.entries(b.counts).forEach(([k, v]) => { t[k] = (t[k] || 0) + v; });
    });
    return t;
  }, [data.buckets]);

  const table = {
    columns: [
      { key: 'name', label: 'Subject' },
      { key: 'total', label: `Incidents (${days}d)`, align: 'right' },
    ],
    rows: series.map(s => ({ name: s.name, total: totals[s.key] || 0 })),
  };

  return (
    <ChartCard title="Incident trend" to="/incidents" table={table}>
      {loading && chartData.length === 0 ? (
        <p className="py-16 text-center text-sm text-muted-foreground" role="status">Loading trend…</p>
      ) : series.length === 0 ? (
        <p className="py-16 text-center text-sm text-muted-foreground">No incidents in this window.</p>
      ) : (
        <div className={loading ? 'opacity-50 transition-opacity' : 'transition-opacity'}>
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={chartData} margin={{ top: 4, right: 8, left: -12, bottom: 0 }}>
              <CartesianGrid stroke={GRID_STROKE} strokeWidth={1} vertical={false} />
              <XAxis dataKey="date" tickFormatter={shortDate} tick={AXIS_TICK} stroke={GRID_STROKE} minTickGap={24} tickLine={false} />
              <YAxis allowDecimals={false} tick={AXIS_TICK} stroke="transparent" tickLine={false} />
              <Tooltip
                contentStyle={TOOLTIP_STYLE}
                labelStyle={{ color: 'hsl(210 40% 98%)', fontWeight: 600 }}
                itemStyle={{ padding: '0 0 2px' }}
                cursor={{ fill: 'hsl(220 40% 18% / 0.4)' }}
                labelFormatter={shortDate}
              />
              <Legend
                wrapperStyle={{ fontSize: 12, cursor: 'pointer' }}
                iconSize={10}
                onClick={entry => drillDown(entry?.dataKey)}
              />
              {series.map((s, i) => (
                <Bar
                  key={s.key}
                  dataKey={s.key}
                  stackId="incidents"
                  name={s.name}
                  fill={s.color}
                  maxBarSize={24}
                  stroke={SURFACE}
                  strokeWidth={1}
                  radius={i === series.length - 1 ? [4, 4, 0, 0] : 0}
                  cursor={s.filter ? 'pointer' : 'default'}
                  onClick={s.filter ? () => drillDown(s.key) : undefined}
                />
              ))}
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </ChartCard>
  );
}
