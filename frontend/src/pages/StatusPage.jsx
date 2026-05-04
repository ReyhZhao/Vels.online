import { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { useAuth } from '../context/AuthContext';
import { useStatus } from '../hooks/useStatus';

export function formatDuration(seconds) {
  if (seconds < 60) return `${seconds}s`;
  if (seconds < 3600) return `${+(seconds / 60).toFixed(1)}m`;
  return `${+(seconds / 3600).toFixed(1)}h`;
}

const SEVEN_DAYS_MS = 7 * 24 * 60 * 60 * 1000;

const BANNER = {
  operational: { bg: 'bg-green-50 border-green-200', text: 'text-green-800', label: 'All systems operational' },
  degraded:    { bg: 'bg-yellow-50 border-yellow-200', text: 'text-yellow-800', label: 'Degraded performance' },
  outage:      { bg: 'bg-red-50 border-red-200', text: 'text-red-800', label: 'Service disruption' },
  unknown:     { bg: 'bg-gray-50 border-gray-200', text: 'text-gray-600', label: 'Status unknown' },
};

const STATUS_BADGE = {
  up:          { variant: 'default', className: 'bg-green-500 hover:bg-green-500', label: 'Operational' },
  down:        { variant: 'destructive', className: '', label: 'Down' },
  seems_down:  { variant: 'default', className: 'bg-yellow-400 hover:bg-yellow-400 text-yellow-900', label: 'Degraded' },
  paused:      { variant: 'secondary', className: '', label: 'Paused' },
  not_checked: { variant: 'secondary', className: '', label: 'Pending' },
};

const LOG_TYPE_LABEL = {
  down:    'Down',
  up:      'Recovery',
  started: 'Started',
  paused:  'Paused',
};

function StatusBadge({ status }) {
  const cfg = STATUS_BADGE[status] ?? { variant: 'secondary', className: '', label: 'Unknown' };
  return (
    <Badge variant={cfg.variant} className={cfg.className}>
      {cfg.label}
    </Badge>
  );
}

function SummaryBanner({ overallStatus, isLoading }) {
  const key = isLoading ? 'unknown' : (overallStatus in BANNER ? overallStatus : 'unknown');
  const { bg, text, label } = BANNER[key];
  return (
    <div className={`rounded-lg border px-6 py-4 ${bg}`}>
      <p className={`text-lg font-semibold ${text}`}>
        {isLoading ? 'Checking status…' : label}
      </p>
    </div>
  );
}

function IncidentLogTable({ logs }) {
  const [showAll, setShowAll] = useState(false);

  if (!logs || logs.length === 0) {
    return <p className="mt-3 text-xs text-muted-foreground">No incidents recorded.</p>;
  }

  const cutoff = new Date(Date.now() - SEVEN_DAYS_MS);
  const recent = logs.filter((log) => new Date(log.datetime) >= cutoff);
  const hasOlder = logs.some((log) => new Date(log.datetime) < cutoff);
  const visible = showAll ? logs : recent;

  return (
    <div className="mt-3 overflow-x-auto">
      <table className="w-full text-xs">
        <thead>
          <tr className="border-b text-left text-muted-foreground">
            <th className="pb-1 pr-4 font-medium">Timestamp</th>
            <th className="pb-1 pr-4 font-medium">Type</th>
            <th className="pb-1 font-medium">Duration</th>
          </tr>
        </thead>
        <tbody>
          {visible.map((log, i) => (
            <tr key={i} className="border-b last:border-0">
              <td className="py-1 pr-4 text-foreground">
                {new Date(log.datetime).toLocaleString()}
              </td>
              <td className="py-1 pr-4">
                <span className={log.type === 'down' ? 'text-red-600' : 'text-muted-foreground'}>
                  {LOG_TYPE_LABEL[log.type] ?? log.type}
                </span>
              </td>
              <td className="py-1 text-muted-foreground">
                {log.duration_seconds != null ? formatDuration(log.duration_seconds) : '—'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {!showAll && hasOlder && (
        <button
          onClick={() => setShowAll(true)}
          className="mt-2 text-xs text-muted-foreground hover:text-foreground transition-colors"
        >
          Load older incidents
        </button>
      )}
    </div>
  );
}

function MonitorCard({ monitor, isAdmin }) {
  const uptime = monitor.uptime_ratio ? `${parseFloat(monitor.uptime_ratio).toFixed(2)}%` : '—';
  const responseTime = monitor.response_time ? `${Math.round(monitor.response_time)} ms` : '—';

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-base font-medium">{monitor.name}</CardTitle>
        <StatusBadge status={monitor.status} />
      </CardHeader>
      <CardContent>
        <div className="flex gap-6 text-sm text-muted-foreground">
          <span>7-day uptime: <span className="font-medium text-foreground">{uptime}</span></span>
          <span>Response time: <span className="font-medium text-foreground">{responseTime}</span></span>
        </div>
        {isAdmin && <IncidentLogTable logs={monitor.logs} />}
      </CardContent>
    </Card>
  );
}

function StatusPage() {
  const { user } = useAuth() ?? {};
  const isAdmin = !!user?.is_staff;
  const { monitors, overallStatus, isLoading, isRefreshing, error, forceRefresh } = useStatus();

  return (
    <div className="container mx-auto px-4 py-12">
      <div className="mb-8 flex items-start justify-between">
        <div>
          <h1 className="text-4xl font-bold tracking-tight text-foreground">System Status</h1>
          <p className="mt-2 text-muted-foreground">Live health of all services. Refreshes every 60 seconds.</p>
        </div>
        {isAdmin && (
          <Button
            variant="outline"
            size="sm"
            onClick={forceRefresh}
            disabled={isRefreshing}
          >
            {isRefreshing ? 'Refreshing…' : 'Force Refresh'}
          </Button>
        )}
      </div>

      <div className="mb-8">
        <SummaryBanner overallStatus={overallStatus} isLoading={isLoading} />
      </div>

      {error && !isLoading && (
        <p className="mb-6 text-sm text-destructive">
          Could not reach the status API. Showing last known data.
        </p>
      )}

      {!isLoading && monitors.length === 0 && !error && (
        <p className="text-muted-foreground">No monitors configured yet.</p>
      )}

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {monitors.map((monitor) => (
          <MonitorCard key={monitor.name} monitor={monitor} isAdmin={isAdmin} />
        ))}
      </div>
    </div>
  );
}

export default StatusPage;
