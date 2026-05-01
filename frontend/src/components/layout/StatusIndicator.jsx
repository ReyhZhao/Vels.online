import { Link } from 'react-router-dom';
import { useStatus } from '../../hooks/useStatus';

const CONFIG = {
  operational: { color: 'bg-green-500', label: 'All systems operational' },
  degraded:    { color: 'bg-yellow-400', label: 'Degraded performance' },
  outage:      { color: 'bg-red-500', label: 'Service disruption' },
  unknown:     { color: 'bg-gray-400', label: 'Status unknown' },
};

function StatusIndicator() {
  const { overallStatus, isLoading } = useStatus();

  const { color, label } = isLoading
    ? { color: 'bg-gray-400', label: 'Checking status…' }
    : CONFIG[overallStatus] ?? CONFIG.unknown;

  return (
    <Link
      to="/status"
      className="flex items-center gap-1.5 text-sm font-medium text-muted-foreground transition-colors hover:text-foreground"
      aria-label={`Site status: ${label}`}
    >
      <span className={`inline-block h-2 w-2 rounded-full ${color}`} aria-hidden="true" />
      <span>{label}</span>
    </Link>
  );
}

export default StatusIndicator;
