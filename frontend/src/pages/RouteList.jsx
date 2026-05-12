import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import api from '../lib/axios';
import { useOrganization } from '../context/OrgContext';

const STATUS_CLASSES = {
  pending: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400',
  active:  'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400',
  error:   'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400',
};

function StatusBadge({ status }) {
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium capitalize ${STATUS_CLASSES[status] ?? 'bg-gray-100 text-gray-700'}`}>
      {status}
    </span>
  );
}

export default function RouteList() {
  const { selectedOrg } = useOrganization();
  const [routes, setRoutes] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!selectedOrg) return;
    setLoading(true);
    setError(null);
    api.get('/api/ingress/routes/', { params: { org: selectedOrg.slug } })
      .then(res => setRoutes(res.data))
      .catch(() => setError('Failed to load routes.'))
      .finally(() => setLoading(false));
  }, [selectedOrg]);

  return (
    <div className="space-y-4 p-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold text-foreground">Routes</h1>
        <Link
          to="/routes/new"
          className="rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
        >
          New Route
        </Link>
      </div>

      {loading && <p className="text-sm text-muted-foreground">Loading…</p>}
      {error && <p className="text-sm text-destructive">{error}</p>}

      {!loading && !error && routes.length === 0 && (
        <p className="text-sm text-muted-foreground">No routes yet.</p>
      )}

      {routes.length > 0 && (
        <div className="overflow-hidden rounded-lg border border-border">
          <table className="w-full text-sm">
            <thead className="bg-muted/50">
              <tr>
                <th className="px-4 py-3 text-left font-medium text-muted-foreground">FQDN / Name</th>
                <th className="px-4 py-3 text-left font-medium text-muted-foreground">Backend</th>
                <th className="px-4 py-3 text-left font-medium text-muted-foreground">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {routes.map(route => (
                <tr key={route.fqdn} className="hover:bg-muted/30 transition-colors">
                  <td className="px-4 py-3">
                    <Link
                      to={`/routes/${route.fqdn}`}
                      className="font-medium text-foreground hover:underline"
                    >
                      {route.fqdn}
                    </Link>
                    {route.name && (
                      <p className="text-xs text-muted-foreground">{route.name}</p>
                    )}
                  </td>
                  <td className="px-4 py-3 text-muted-foreground">
                    {route.backend_protocol}://{route.backend_host}:{route.backend_port}
                  </td>
                  <td className="px-4 py-3">
                    <StatusBadge status={route.status} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
