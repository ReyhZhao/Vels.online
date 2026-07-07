import { useState, useEffect } from 'react';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from 'recharts';
import api from '../../lib/axios';
import ChartCard from './ChartCard';
import {
  SEVERITY_COLORS, SEVERITY_LABELS, GRID_STROKE, AXIS_TICK, SURFACE, TOOLTIP_STYLE,
} from './palette';

const SERIES = ['critical', 'high', 'medium', 'low'];

function shortDate(iso) {
  const d = new Date(`${iso}T00:00:00`);
  return d.toLocaleDateString([], { day: 'numeric', month: 'short' });
}

/**
 * Fleet vulnerability counts over time, one 2px line per severity from the
 * daily snapshots. Range comes from the page-level filter row.
 */
export default function VulnTrendCard({ orgSlug, days }) {
  const [snapshots, setSnapshots] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!orgSlug) return;
    let cancelled = false;
    setLoading(true);
    api.get('/api/security/vulnerabilities/trend/', { params: { org: orgSlug, days } })
      .then(res => { if (!cancelled) setSnapshots(res.data.snapshots || []); })
      .catch(() => { if (!cancelled) setSnapshots([]); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [orgSlug, days]);

  const table = {
    columns: [
      { key: 'date', label: 'Date' },
      ...SERIES.map(s => ({ key: s, label: SEVERITY_LABELS[s], align: 'right' })),
    ],
    rows: snapshots.map(s => ({ ...s, date: shortDate(s.date) })),
  };

  return (
    <ChartCard title="Vulnerability trend" to="/security/vulnerabilities" table={table}>
      {loading && snapshots.length === 0 ? (
        <p className="py-16 text-center text-sm text-muted-foreground" role="status">Loading trend…</p>
      ) : snapshots.length === 0 ? (
        <p className="py-16 text-center text-sm text-muted-foreground">No snapshots in this window yet.</p>
      ) : (
        <div className={loading ? 'opacity-50 transition-opacity' : 'transition-opacity'}>
          <ResponsiveContainer width="100%" height={240}>
            <LineChart data={snapshots} margin={{ top: 4, right: 8, left: -12, bottom: 0 }}>
              <CartesianGrid stroke={GRID_STROKE} strokeWidth={1} vertical={false} />
              <XAxis dataKey="date" tickFormatter={shortDate} tick={AXIS_TICK} stroke={GRID_STROKE} minTickGap={24} tickLine={false} />
              <YAxis allowDecimals={false} tick={AXIS_TICK} stroke="transparent" tickLine={false} />
              <Tooltip
                contentStyle={TOOLTIP_STYLE}
                labelStyle={{ color: 'hsl(210 40% 98%)', fontWeight: 600 }}
                itemStyle={{ padding: '0 0 2px' }}
                labelFormatter={shortDate}
              />
              <Legend wrapperStyle={{ fontSize: 12 }} iconSize={10} />
              {SERIES.map(key => (
                <Line
                  key={key}
                  type="monotone"
                  dataKey={key}
                  name={SEVERITY_LABELS[key]}
                  stroke={SEVERITY_COLORS[key]}
                  strokeWidth={2}
                  strokeLinecap="round"
                  dot={false}
                  activeDot={{ r: 4, stroke: SURFACE, strokeWidth: 2 }}
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </ChartCard>
  );
}
