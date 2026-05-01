import { useEffect, useState } from 'react';
import { cn } from '@/lib/utils';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import api from '@/lib/axios';

function Toggle({ checked, onChange, disabled }) {
  return (
    <button
      role="switch"
      aria-checked={checked}
      onClick={() => !disabled && onChange(!checked)}
      disabled={disabled}
      className={cn(
        'relative inline-flex h-5 w-9 items-center rounded-full transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-ring',
        checked ? 'bg-primary' : 'bg-muted',
        disabled && 'opacity-50 cursor-not-allowed'
      )}
    >
      <span
        className={cn(
          'inline-block h-3 w-3 transform rounded-full bg-white transition-transform',
          checked ? 'translate-x-5' : 'translate-x-1'
        )}
      />
    </button>
  );
}

function StatusSettings() {
  const [monitors, setMonitors] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);
  const [saving, setSaving] = useState({});

  useEffect(() => {
    api
      .get('/api/status/monitors/')
      .then((res) => setMonitors(res.data))
      .catch(() => setError('Failed to load monitors.'))
      .finally(() => setIsLoading(false));
  }, []);

  function handleToggle(monitor, newValue) {
    setMonitors((prev) =>
      prev.map((m) => (m.monitor_id === monitor.monitor_id ? { ...m, is_visible: newValue } : m))
    );
    setSaving((prev) => ({ ...prev, [monitor.monitor_id]: true }));

    api
      .patch(`/api/status/monitors/${monitor.monitor_id}/`, {
        name: monitor.name,
        is_visible: newValue,
      })
      .catch(() => {
        setMonitors((prev) =>
          prev.map((m) =>
            m.monitor_id === monitor.monitor_id ? { ...m, is_visible: !newValue } : m
          )
        );
      })
      .finally(() =>
        setSaving((prev) => ({ ...prev, [monitor.monitor_id]: false }))
      );
  }

  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-foreground">Status Page Settings</h1>
        <p className="text-sm text-muted-foreground">
          Toggle which monitors appear on the public status page.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Monitors</CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading && <p className="text-sm text-muted-foreground">Loading monitors…</p>}
          {error && <p className="text-sm text-destructive">{error}</p>}
          {!isLoading && !error && monitors.length === 0 && (
            <p className="text-sm text-muted-foreground">No monitors found. Check your UptimeRobot API key.</p>
          )}
          {!isLoading && !error && monitors.length > 0 && (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-muted-foreground">
                  <th className="pb-2 font-medium">Monitor</th>
                  <th className="pb-2 font-medium text-right">Visible on status page</th>
                </tr>
              </thead>
              <tbody>
                {monitors.map((monitor) => (
                  <tr key={monitor.monitor_id} className="border-b last:border-0">
                    <td className="py-3 font-medium text-foreground">{monitor.name}</td>
                    <td className="py-3 text-right">
                      <Toggle
                        checked={monitor.is_visible}
                        onChange={(val) => handleToggle(monitor, val)}
                        disabled={!!saving[monitor.monitor_id]}
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

export default StatusSettings;
