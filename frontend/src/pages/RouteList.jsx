import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import api from '../lib/axios';
import { useOrganization } from '../context/OrgContext';
import { useAuth } from '../context/AuthContext';
import RouteNewDrawer from './RouteNewDrawer';

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

function ImportModal({ open, onClose, onImported, orgSlug }) {
  const [candidates, setCandidates] = useState([]);
  const [candidatesLoading, setCandidatesLoading] = useState(false);
  const [candidatesError, setCandidatesError] = useState(null);
  const [selected, setSelected] = useState(new Set());
  const [importing, setImporting] = useState(false);
  const [importError, setImportError] = useState(null);

  useEffect(() => {
    if (!open) return;
    setSelected(new Set());
    setImportError(null);
    setCandidatesError(null);
    setCandidatesLoading(true);
    api.get('/api/ingress/routes/import/', { params: { org: orgSlug } })
      .then(res => setCandidates(res.data.candidates))
      .catch(err => setCandidatesError(err.response?.data?.detail || 'Failed to load BunkerWeb services.'))
      .finally(() => setCandidatesLoading(false));
  }, [open, orgSlug]);

  function toggle(fqdn) {
    setSelected(prev => {
      const next = new Set(prev);
      next.has(fqdn) ? next.delete(fqdn) : next.add(fqdn);
      return next;
    });
  }

  async function submit() {
    setImporting(true);
    setImportError(null);
    try {
      const res = await api.post(
        '/api/ingress/routes/import/',
        { fqdns: [...selected] },
        { params: { org: orgSlug } },
      );
      onImported(res.data);
      onClose();
    } catch (err) {
      setImportError(err.response?.data?.detail || 'Import failed.');
    } finally {
      setImporting(false);
    }
  }

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/50 pt-12 pb-12">
      <div className="w-full max-w-lg rounded-lg border border-border bg-card p-6 shadow-lg space-y-4 mx-4">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold text-foreground">Import from BunkerWeb</h2>
          <button onClick={onClose} aria-label="Close" className="text-sm text-muted-foreground hover:text-foreground">✕</button>
        </div>
        <p className="text-sm text-muted-foreground">
          Select services already registered in BunkerWeb to import into this organisation.
        </p>

        {candidatesLoading && <p className="text-sm text-muted-foreground">Loading services…</p>}
        {candidatesError && <p className="text-sm text-destructive">{candidatesError}</p>}

        {!candidatesLoading && !candidatesError && candidates.length === 0 && (
          <p className="text-sm text-muted-foreground">No unregistered BunkerWeb services found.</p>
        )}

        {candidates.length > 0 && (
          <div className="max-h-72 overflow-y-auto divide-y divide-border rounded-md border border-border">
            {candidates.map(c => (
              <label key={c.server_name} className="flex items-center gap-3 px-4 py-3 cursor-pointer hover:bg-muted/30">
                <input
                  type="checkbox"
                  checked={selected.has(c.server_name)}
                  onChange={() => toggle(c.server_name)}
                  className="h-4 w-4 rounded border-border"
                />
                <div>
                  <p className="text-sm font-medium text-foreground">{c.server_name}</p>
                  <p className="text-xs text-muted-foreground">
                    {c.backend_protocol}://{c.backend_host}:{c.backend_port}
                  </p>
                </div>
              </label>
            ))}
          </div>
        )}

        {importError && <p className="text-sm text-destructive">{importError}</p>}

        <div className="flex justify-end gap-2 pt-2">
          <button
            onClick={onClose}
            className="rounded-md border border-border px-3 py-2 text-sm text-foreground hover:bg-muted/50 transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={submit}
            disabled={selected.size === 0 || importing}
            className="rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-50"
          >
            {importing ? 'Importing…' : `Import ${selected.size > 0 ? `(${selected.size})` : ''}`}
          </button>
        </div>
      </div>
    </div>
  );
}

export default function RouteList() {
  const { selectedOrg } = useOrganization();
  const { user } = useAuth();
  const [routes, setRoutes] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [showImport, setShowImport] = useState(false);
  const [showDrawer, setShowDrawer] = useState(false);

  useEffect(() => {
    if (!selectedOrg) return;
    setLoading(true);
    setError(null);
    api.get('/api/ingress/routes/', { params: { org: selectedOrg.slug } })
      .then(res => setRoutes(res.data))
      .catch(() => setError('Failed to load routes.'))
      .finally(() => setLoading(false));
  }, [selectedOrg]);

  function handleImported(newRoutes) {
    setRoutes(prev => [...newRoutes, ...prev]);
  }

  return (
    <div className="space-y-4 p-6">
      <ImportModal
        open={showImport}
        onClose={() => setShowImport(false)}
        onImported={handleImported}
        orgSlug={selectedOrg?.slug}
      />

      {showDrawer && (
        <RouteNewDrawer
          onClose={() => setShowDrawer(false)}
          onCreated={() => {
            setShowDrawer(false);
            if (selectedOrg) {
              setLoading(true);
              api.get('/api/ingress/routes/', { params: { org: selectedOrg.slug } })
                .then(res => setRoutes(res.data))
                .catch(() => {})
                .finally(() => setLoading(false));
            }
          }}
          orgSlug={selectedOrg?.slug}
        />
      )}

      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold text-foreground">Routes</h1>
        <div className="flex items-center gap-2">
          {user?.is_staff && (
            <button
              onClick={() => setShowImport(true)}
              className="rounded-md border border-border px-3 py-2 text-sm font-medium text-foreground hover:bg-muted/50 transition-colors"
            >
              Import from BunkerWeb
            </button>
          )}
          <button
            onClick={() => setShowDrawer(true)}
            className="rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
          >
            New Route
          </button>
        </div>
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
