import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import api from '../lib/axios';
import RouteSettings from './RouteSettings';
import RouteReports from './RouteReports';

const STATUS_CLASSES = {
  pending: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400',
  active:  'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400',
  error:   'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400',
};

const TABS = [
  { key: 'settings', label: 'Settings' },
  { key: 'reports',  label: 'Reports' },
];

export default function RouteDetail() {
  const { fqdn } = useParams();
  const navigate = useNavigate();

  const [route, setRoute] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [activeTab, setActiveTab] = useState('settings');
  const [reportsOpened, setReportsOpened] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState(null);
  const [bwTarget, setBwTarget] = useState(null);

  useEffect(() => {
    api.get(`/api/ingress/routes/${fqdn}/`)
      .then(res => {
        setRoute(res.data);
        if (res.data.dns_ok === false) {
          api.get('/api/ingress/settings/')
            .then(s => setBwTarget(s.data.bunkerweb_public_fqdn || s.data.bunkerweb_public_ip || null))
            .catch(() => {});
        }
      })
      .catch(() => setError('Route not found.'))
      .finally(() => setLoading(false));
  }, [fqdn]);

  async function handleDelete() {
    if (!window.confirm(`Delete route ${fqdn}?`)) return;
    setDeleting(true);
    setDeleteError(null);
    try {
      await api.delete(`/api/ingress/routes/${fqdn}/`);
      navigate('/routes');
    } catch (err) {
      setDeleteError(err.response?.data?.detail || 'Failed to delete route.');
      setDeleting(false);
    }
  }

  if (loading) return <p className="p-6 text-sm text-muted-foreground">Loading…</p>;
  if (error) return <p className="p-6 text-sm text-destructive">{error}</p>;

  return (
    <div className="space-y-6 p-6">
      {route.dns_ok === false && (
        <div role="alert" className="rounded-md border border-yellow-300 bg-yellow-50 px-4 py-3 text-sm dark:border-yellow-700 dark:bg-yellow-950/30">
          <span className="font-medium text-yellow-800 dark:text-yellow-300">DNS not yet pointing to BunkerWeb</span>
          {' — '}
          <span className="text-yellow-700 dark:text-yellow-400">
            {bwTarget
              ? <>set your DNS record to point to <code className="font-mono bg-yellow-100 dark:bg-yellow-900/50 px-1 rounded">{bwTarget}</code></>
              : 'ensure your FQDN resolves to the BunkerWeb public IP.'
            }
          </span>
        </div>
      )}

      {route.dns_ok === null && (
        <p className="text-xs text-muted-foreground" data-testid="dns-pending">DNS check pending…</p>
      )}

      <div className="flex items-start justify-between gap-4">
        <div className="space-y-1">
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-semibold text-foreground font-mono">{route.fqdn}</h1>
            <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium capitalize ${STATUS_CLASSES[route.status] ?? 'bg-gray-100 text-gray-700'}`}>
              {route.status}
            </span>
          </div>
          {route.name && <p className="text-sm text-muted-foreground">{route.name}</p>}
          <p className="text-sm text-muted-foreground">
            {route.backend_host ? `${route.backend_protocol}://${route.backend_host}:${route.backend_port}` : '—'}
          </p>
        </div>

        <button
          onClick={handleDelete}
          disabled={deleting}
          className="rounded-md border border-destructive px-3 py-2 text-sm font-medium text-destructive hover:bg-destructive/10 disabled:opacity-50 transition-colors"
        >
          {deleting ? 'Deleting…' : 'Delete'}
        </button>
      </div>

      {deleteError && <p className="text-sm text-destructive">{deleteError}</p>}

      <div className="border-b border-border">
        <nav className="flex gap-4" aria-label="Route tabs">
          {TABS.map(tab => (
            <button
              key={tab.key}
              onClick={() => {
                setActiveTab(tab.key);
                if (tab.key === 'reports') setReportsOpened(true);
              }}
              className={`pb-2 text-sm font-medium border-b-2 transition-colors ${
                activeTab === tab.key
                  ? 'border-primary text-foreground'
                  : 'border-transparent text-muted-foreground hover:text-foreground'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </nav>
      </div>

      <div>
        {activeTab === 'settings' && <RouteSettings fqdn={route.fqdn} />}
        {reportsOpened && (
          <div className={activeTab !== 'reports' ? 'hidden' : ''}>
            <RouteReports fqdn={route.fqdn} />
          </div>
        )}
      </div>
    </div>
  );
}
