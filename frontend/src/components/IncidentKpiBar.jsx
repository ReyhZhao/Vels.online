import { useMemo } from 'react';
import { PieChart, Pie, Cell, ResponsiveContainer } from 'recharts';
import { worstSla } from '../lib/sla';

const SEVERITY_ORDER = ['critical', 'high', 'medium', 'low', 'info'];

const SEVERITY_DOT = {
  critical: 'bg-red-500',
  high:     'bg-orange-500',
  medium:   'bg-yellow-500',
  low:      'bg-blue-500',
  info:     'bg-gray-400',
};

const SEVERITY_HEX = {
  critical: '#ef4444',
  high:     '#f97316',
  medium:   '#eab308',
  low:      '#3b82f6',
  info:     '#9ca3af',
};

function StatTile({ label, value, sub, accent }) {
  return (
    <div className="flex flex-col rounded-lg border border-border bg-card p-4">
      <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{label}</span>
      <span className={`mt-2 text-3xl font-semibold leading-none tabular-nums ${accent ?? 'text-foreground'}`}>{value}</span>
      {/* Reserve the sub line's height on every tile so the numbers align across the row. */}
      <span className="mt-1 min-h-4 text-xs text-muted-foreground">{sub ?? ' '}</span>
    </div>
  );
}

// At-a-glance summary of the incidents currently in view. The counts and the
// severity breakdown are scoped to the current page of results (`count` is the
// full filtered total, shown as the "Open" figure); see IncidentList.
export default function IncidentKpiBar({ results, count }) {
  const { mix, breaches, unassigned, critHigh, donut } = useMemo(() => {
    const mix = Object.fromEntries(SEVERITY_ORDER.map(s => [s, 0]));
    results.forEach(i => { if (mix[i.severity] != null) mix[i.severity] += 1; });
    return {
      mix,
      breaches: results.filter(i => worstSla(i)?.breached).length,
      unassigned: results.filter(i => !i.assignee_username).length,
      critHigh: mix.critical + mix.high,
      donut: SEVERITY_ORDER.map(s => ({ name: s, value: mix[s] })).filter(d => d.value > 0),
    };
  }, [results]);

  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-5">
      <StatTile label="Open (page)" value={results.length} sub={`${count} total matching`} />
      <StatTile
        label="Critical + High"
        value={critHigh}
        accent={critHigh ? 'text-orange-600 dark:text-orange-400' : undefined}
      />
      <StatTile
        label="SLA breaches"
        value={breaches}
        accent={breaches ? 'text-red-600 dark:text-red-400' : 'text-green-600 dark:text-green-400'}
        sub={breaches ? 'need attention now' : 'all healthy'}
      />
      <StatTile
        label="Unassigned"
        value={unassigned}
        accent={unassigned ? 'text-amber-600 dark:text-amber-400' : undefined}
      />
      <div className="col-span-2 flex items-center gap-3 rounded-lg border border-border bg-card p-4 sm:col-span-4 lg:col-span-1">
        <div className="h-20 w-20 shrink-0">
          {donut.length > 0 ? (
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie data={donut} dataKey="value" innerRadius={22} outerRadius={38} paddingAngle={2} stroke="none">
                  {donut.map(d => <Cell key={d.name} fill={SEVERITY_HEX[d.name]} />)}
                </Pie>
              </PieChart>
            </ResponsiveContainer>
          ) : (
            <div className="h-full w-full rounded-full border-4 border-muted" />
          )}
        </div>
        <div className="flex flex-col gap-0.5 text-xs">
          {SEVERITY_ORDER.filter(s => mix[s] > 0).map(s => (
            <span key={s} className="flex items-center gap-1.5 text-muted-foreground">
              <span className={`h-2 w-2 rounded-full ${SEVERITY_DOT[s]}`} />
              <span className="capitalize">{s}</span>
              <span className="ml-auto font-medium tabular-nums text-foreground">{mix[s]}</span>
            </span>
          ))}
          {donut.length === 0 && <span className="text-muted-foreground">No incidents</span>}
        </div>
      </div>
    </div>
  );
}
