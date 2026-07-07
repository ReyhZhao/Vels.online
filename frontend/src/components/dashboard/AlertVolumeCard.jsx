import { useNavigate } from 'react-router-dom';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts';
import ChartCard from './ChartCard';
import { CATEGORICAL, GRID_STROKE, AXIS_TICK, TOOLTIP_STYLE } from './palette';

function dayLabel(iso) {
  const d = new Date(`${iso}T00:00:00`);
  return d.toLocaleDateString([], { weekday: 'short' });
}

/**
 * Alerts received per day over the last week (single series — the legend is
 * the title). Clicking a column jumps to the alert list.
 */
export default function AlertVolumeCard({ daily, loading }) {
  const navigate = useNavigate();
  const data = daily ?? [];

  const table = {
    columns: [
      { key: 'day', label: 'Day' },
      { key: 'count', label: 'Alerts', align: 'right' },
    ],
    rows: data.map(d => ({ day: dayLabel(d.date), count: d.count })),
  };

  return (
    <ChartCard title="Alert volume (7d)" to="/alerts" table={table}>
      {loading && data.length === 0 ? (
        <p className="py-10 text-center text-sm text-muted-foreground" role="status">Loading…</p>
      ) : data.length === 0 ? (
        <p className="py-10 text-center text-sm text-muted-foreground">No alert data.</p>
      ) : (
        <div className={loading ? 'opacity-50 transition-opacity' : 'transition-opacity'}>
          <ResponsiveContainer width="100%" height={150}>
            <BarChart data={data} margin={{ top: 4, right: 4, left: -4, bottom: 0 }}>
              <CartesianGrid stroke={GRID_STROKE} strokeWidth={1} vertical={false} />
              <XAxis dataKey="date" tickFormatter={dayLabel} tick={AXIS_TICK} stroke={GRID_STROKE} tickLine={false} interval={0} />
              <YAxis allowDecimals={false} tick={AXIS_TICK} stroke="transparent" tickLine={false} width={32} />
              <Tooltip
                contentStyle={TOOLTIP_STYLE}
                labelStyle={{ color: 'hsl(210 40% 98%)', fontWeight: 600 }}
                cursor={{ fill: 'hsl(220 40% 18% / 0.4)' }}
                labelFormatter={iso => new Date(`${iso}T00:00:00`).toLocaleDateString([], { day: 'numeric', month: 'short' })}
                formatter={value => [value, 'Alerts']}
              />
              <Bar
                dataKey="count"
                fill={CATEGORICAL[0]}
                maxBarSize={24}
                radius={[4, 4, 0, 0]}
                cursor="pointer"
                onClick={() => navigate('/alerts')}
              />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </ChartCard>
  );
}
