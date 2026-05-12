import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import api from '../lib/axios';
import { useOrganization } from '../context/OrgContext';

export default function RouteNew() {
  const navigate = useNavigate();
  const { selectedOrg } = useOrganization();

  const [bwIp, setBwIp] = useState('');
  const [form, setForm] = useState({
    name: '',
    fqdn: '',
    backend_host: '',
    backend_port: '',
    backend_protocol: 'http',
  });
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    api.get('/api/ingress/settings/')
      .then(res => setBwIp(res.data.bunkerweb_public_ip || ''))
      .catch(() => {});
  }, []);

  function handleChange(e) {
    const { name, value } = e.target;
    setForm(f => ({ ...f, [name]: value }));
  }

  async function handleSubmit(e) {
    e.preventDefault();
    if (!selectedOrg) return;
    setError(null);
    setSubmitting(true);
    try {
      const payload = {
        ...form,
        backend_port: Number(form.backend_port),
      };
      await api.post(`/api/ingress/routes/?org=${selectedOrg.slug}`, payload);
      navigate('/routes');
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to create route.');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="space-y-6 p-6 max-w-xl">
      <h1 className="text-2xl font-semibold text-foreground">New Route</h1>

      {bwIp && (
        <div className="rounded-md border border-blue-200 bg-blue-50 px-4 py-3 text-sm dark:border-blue-800 dark:bg-blue-950/30">
          <span className="font-medium text-blue-800 dark:text-blue-300">BunkerWeb IP: </span>
          <span className="font-mono text-blue-700 dark:text-blue-400" data-testid="bunkerweb-ip">{bwIp}</span>
          <p className="mt-1 text-xs text-blue-600 dark:text-blue-400">
            Point your DNS A record to this IP before traffic will be served.
          </p>
        </div>
      )}

      {error && (
        <p className="text-sm text-destructive">{error}</p>
      )}

      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label className="block text-sm font-medium text-foreground mb-1">
            Name <span className="text-muted-foreground font-normal">(optional)</span>
          </label>
          <input
            name="name"
            value={form.name}
            onChange={handleChange}
            placeholder="My service"
            className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-1 focus:ring-ring"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-foreground mb-1">
            Public FQDN <span className="text-destructive">*</span>
          </label>
          <input
            name="fqdn"
            value={form.fqdn}
            onChange={handleChange}
            required
            placeholder="app.example.com"
            className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-1 focus:ring-ring"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-foreground mb-1">
            Backend Host <span className="text-destructive">*</span>
          </label>
          <input
            name="backend_host"
            value={form.backend_host}
            onChange={handleChange}
            required
            placeholder="10.0.0.1"
            className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-1 focus:ring-ring"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-foreground mb-1">
            Backend Port <span className="text-destructive">*</span>
          </label>
          <input
            name="backend_port"
            type="number"
            value={form.backend_port}
            onChange={handleChange}
            required
            min="1"
            max="65535"
            placeholder="8080"
            className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-1 focus:ring-ring"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-foreground mb-1">
            Backend Protocol
          </label>
          <select
            name="backend_protocol"
            value={form.backend_protocol}
            onChange={handleChange}
            className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-1 focus:ring-ring"
          >
            <option value="http">HTTP</option>
            <option value="https">HTTPS</option>
          </select>
        </div>

        <div className="flex gap-3 pt-2">
          <button
            type="submit"
            disabled={submitting}
            className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-colors"
          >
            {submitting ? 'Creating…' : 'Create Route'}
          </button>
          <button
            type="button"
            onClick={() => navigate('/routes')}
            className="rounded-md border border-border px-4 py-2 text-sm font-medium text-foreground hover:bg-accent transition-colors"
          >
            Cancel
          </button>
        </div>
      </form>
    </div>
  );
}
