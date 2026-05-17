import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { Globe, Server, ChevronRight, Search } from 'lucide-react';
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
                    {c.backend_host ? `${c.backend_protocol}://${c.backend_host}:${c.backend_port}` : '—'}
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
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');

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

  function handleCreated() {
    setShowDrawer(false);
    if (!selectedOrg) return;
    setLoading(true);
    api.get('/api/ingress/routes/', { params: { org: selectedOrg.slug } })
      .then(res => setRoutes(res.data))
      .catch(() => {})
      .finally(() => setLoading(false));
  }

  const filtered = routes.filter(r => {
    const q = search.toLowerCase();
    const matchSearch = !q || r.fqdn.includes(q) || r.name?.toLowerCase().includes(q);
    const matchStatus = statusFilter === 'all' || r.status === statusFilter;
    return matchSearch && matchStatus;
  });

  const statusButtonClass = (s) => {
    const active = statusFilter === s;
    if (!active) return 'bg-muted text-muted-foreground hover:text-foreground';
    if (s === 'active')  return 'bg-green-600 text-white';
    if (s === 'error')   return 'bg-red-600 text-white';
    if (s === 'pending') return 'bg-yellow-600 text-white';
    return 'bg-primary text-primary-foreground';
  };

  return (
    <>
      <ImportModal
        open={showImport}
        onClose={() => setShowImport(false)}
        onImported={handleImported}
        orgSlug={selectedOrg?.slug}
      />
      {showDrawer && (
        <RouteNewDrawer
          onClose={() => setShowDrawer(false)}
          onCreated={handleCreated}
          orgSlug={selectedOrg?.slug}
        />
      )}

      <div className="space-y-5 p-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-semibold text-foreground">Routes</h1>
            <p className="text-sm text-muted-foreground mt-0.5">
              {routes.length} published app{routes.length !== 1 ? 's' : ''}
            </p>
          </div>
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
              + New Route
            </button>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <div className="relative">
            <Search className="absolute left-2.5 top-2.5 h-3.5 w-3.5 text-muted-foreground" />
            <input
              type="search"
              placeholder="Search domain or name…"
              value={search}
              onChange={e => setSearch(e.target.value)}
              className="rounded-md border border-border bg-background pl-8 pr-3 py-2 text-sm w-64 focus:outline-none focus:ring-1 focus:ring-ring"
            />
          </div>
          <div className="flex items-center gap-1">
            {['all', 'active', 'pending', 'error'].map(s => (
              <button
                key={s}
                onClick={() => setStatusFilter(s)}
                className={`rounded-full px-3 py-1.5 text-xs font-medium capitalize transition-colors ${statusButtonClass(s)}`}
              >
                {s}
                {s !== 'all' && (
                  <span className="ml-1 opacity-70">
                    ({routes.filter(r => r.status === s).length})
                  </span>
                )}
              </button>
            ))}
          </div>
        </div>

        {loading && <p className="text-sm text-muted-foreground">Loading…</p>}
        {error && <p className="text-sm text-destructive">{error}</p>}

        {!loading && !error && routes.length === 0 && (
          <div className="py-20 text-center rounded-xl border border-dashed border-border">
            <Globe className="mx-auto h-8 w-8 text-muted-foreground/30 mb-3" />
            <p className="text-sm text-muted-foreground">No routes yet.</p>
            <button onClick={() => setShowDrawer(true)} className="mt-2 text-xs text-primary hover:underline">
              Create your first route →
            </button>
          </div>
        )}

        {!loading && !error && routes.length > 0 && filtered.length === 0 && (
          <div className="py-16 text-center rounded-xl border border-dashed border-border">
            <p className="text-sm text-muted-foreground">No routes match your filters.</p>
            <button
              onClick={() => { setSearch(''); setStatusFilter('all'); }}
              className="mt-2 text-xs text-primary hover:underline"
            >
              Clear filters
            </button>
          </div>
        )}

        {filtered.length > 0 && (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {filtered.map(route => (
              <Link
                key={route.fqdn}
                to={`/routes/${route.fqdn}`}
                className="group flex flex-col rounded-xl border border-border bg-card p-5 hover:border-primary/40 hover:shadow-md hover:shadow-black/20 transition-all duration-150"
              >
                <div className="flex items-start justify-between gap-2 mb-3">
                  <div className="flex-1 min-w-0">
                    <p className="font-mono text-sm font-semibold text-foreground truncate">{route.fqdn}</p>
                    {route.name && <p className="text-xs text-muted-foreground mt-0.5">{route.name}</p>}
                  </div>
                  <StatusBadge status={route.status} />
                </div>
                <div className="flex items-center gap-1.5 text-xs text-muted-foreground font-mono">
                  <Server className="h-3 w-3 flex-shrink-0" />
                  <span className="truncate">{route.backend_host ? `${route.backend_protocol}://${route.backend_host}:${route.backend_port}` : '—'}</span>
                </div>
                <div className="mt-4 flex items-center justify-end">
                  <span className="text-xs text-muted-foreground group-hover:text-primary transition-colors flex items-center gap-1">
                    Settings <ChevronRight className="h-3 w-3" />
                  </span>
                </div>
              </Link>
            ))}
          </div>
        )}
      </div>
    </>
  );
}
