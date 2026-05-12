import { useState, useEffect } from 'react';
import api from '../lib/axios';

const PARANOIA_LEVELS = [1, 2, 3, 4];

const DEFAULT_SETTINGS = {
  USE_MODSECURITY: 'no',
  USE_MODSECURITY_CRS: 'no',
  MODSECURITY_CRS_PARANOIA_LEVEL: '1',
  USE_WHITELIST: 'no',
  WHITELIST_IP: '',
  USE_LIMIT_REQ: 'no',
  LIMIT_REQ_RATE: '',
  LIMIT_REQ_BURST: '',
  BLACKLIST_COUNTRY: '',
  WHITELIST_COUNTRY: '',
};

function Toggle({ id, checked, onChange, testId }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      onClick={onChange}
      data-testid={testId}
      className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors ${
        checked ? 'bg-primary' : 'bg-muted'
      }`}
    >
      <span
        className={`inline-block h-3 w-3 transform rounded-full bg-white transition-transform ${
          checked ? 'translate-x-5' : 'translate-x-1'
        }`}
      />
    </button>
  );
}

export default function RouteSettings({ fqdn }) {
  const [settings, setSettings] = useState(DEFAULT_SETTINGS);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(null);
  const [saving, setSaving] = useState(false);
  const [toast, setToast] = useState(null);
  const [validationError, setValidationError] = useState(null);

  useEffect(() => {
    api.get(`/api/ingress/routes/${fqdn}/settings/`)
      .then(res => setSettings(prev => ({ ...prev, ...res.data })))
      .catch(() => setLoadError('Failed to load settings.'))
      .finally(() => setLoading(false));
  }, [fqdn]);

  function handleToggle(key) {
    setSettings(s => ({ ...s, [key]: s[key] === 'yes' ? 'no' : 'yes' }));
  }

  function handleChange(key, value) {
    setSettings(s => ({ ...s, [key]: value }));
  }

  async function handleSave(e) {
    e.preventDefault();
    setValidationError(null);
    setToast(null);

    const level = parseInt(settings.MODSECURITY_CRS_PARANOIA_LEVEL, 10);
    if (isNaN(level) || level < 1 || level > 4) {
      setValidationError('Paranoia level must be between 1 and 4.');
      return;
    }

    setSaving(true);
    try {
      await api.patch(`/api/ingress/routes/${fqdn}/settings/`, settings);
      setToast('Settings saved — update queued.');
    } catch (err) {
      setToast(err.response?.data?.detail || 'Failed to save settings.');
    } finally {
      setSaving(false);
    }
  }

  if (loading) return <p className="text-sm text-muted-foreground">Loading settings…</p>;
  if (loadError) return <p className="text-sm text-destructive">{loadError}</p>;

  return (
    <form onSubmit={handleSave} className="space-y-6 max-w-md">
      <section className="space-y-4">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">
          Web Application Firewall
        </h2>

        <label className="flex items-center justify-between gap-4">
          <span className="text-sm font-medium text-foreground">Enable ModSecurity WAF</span>
          <Toggle
            checked={settings.USE_MODSECURITY === 'yes'}
            onChange={() => handleToggle('USE_MODSECURITY')}
            testId="toggle-USE_MODSECURITY"
          />
        </label>

        <label className="flex items-center justify-between gap-4">
          <span className="text-sm font-medium text-foreground">Enable OWASP CRS</span>
          <Toggle
            checked={settings.USE_MODSECURITY_CRS === 'yes'}
            onChange={() => handleToggle('USE_MODSECURITY_CRS')}
            testId="toggle-USE_MODSECURITY_CRS"
          />
        </label>

        <div className="flex items-center justify-between gap-4">
          <label htmlFor="paranoia-level" className="text-sm font-medium text-foreground">
            CRS Paranoia Level
          </label>
          <select
            id="paranoia-level"
            value={settings.MODSECURITY_CRS_PARANOIA_LEVEL}
            onChange={e => { setValidationError(null); handleChange('MODSECURITY_CRS_PARANOIA_LEVEL', e.target.value); }}
            className="rounded-md border border-input bg-background px-2 py-1 text-sm shadow-sm focus:outline-none focus:ring-1 focus:ring-ring"
          >
            {PARANOIA_LEVELS.map(l => (
              <option key={l} value={String(l)}>{l}</option>
            ))}
          </select>
        </div>

        {validationError && (
          <p className="text-sm text-destructive" data-testid="validation-error">{validationError}</p>
        )}
      </section>

      <section className="space-y-4">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">
          IP Whitelist
        </h2>

        <label className="flex items-center justify-between gap-4">
          <span className="text-sm font-medium text-foreground">Enable IP Whitelist</span>
          <Toggle
            checked={settings.USE_WHITELIST === 'yes'}
            onChange={() => handleToggle('USE_WHITELIST')}
            testId="toggle-USE_WHITELIST"
          />
        </label>

        <div className="space-y-1">
          <label htmlFor="whitelist-ip" className="text-sm font-medium text-foreground">
            Allowed IPs / CIDRs
          </label>
          <textarea
            id="whitelist-ip"
            data-testid="input-WHITELIST_IP"
            value={settings.WHITELIST_IP}
            onChange={e => handleChange('WHITELIST_IP', e.target.value)}
            rows={3}
            placeholder="192.168.1.0/24 10.0.0.1"
            className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm font-mono shadow-sm placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring"
          />
          <p className="text-xs text-muted-foreground">Space-separated IPs or CIDR ranges.</p>
        </div>
      </section>

      <section className="space-y-4">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">
          Rate Limiting
        </h2>

        <label className="flex items-center justify-between gap-4">
          <span className="text-sm font-medium text-foreground">Enable Rate Limiting</span>
          <Toggle
            checked={settings.USE_LIMIT_REQ === 'yes'}
            onChange={() => handleToggle('USE_LIMIT_REQ')}
            testId="toggle-USE_LIMIT_REQ"
          />
        </label>

        <div className="flex items-center justify-between gap-4">
          <label htmlFor="limit-req-rate" className="text-sm font-medium text-foreground">
            Rate
          </label>
          <input
            id="limit-req-rate"
            data-testid="input-LIMIT_REQ_RATE"
            type="text"
            value={settings.LIMIT_REQ_RATE}
            onChange={e => handleChange('LIMIT_REQ_RATE', e.target.value)}
            placeholder="10r/s"
            className="w-32 rounded-md border border-input bg-background px-2 py-1 text-sm font-mono shadow-sm placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring"
          />
        </div>

        <div className="flex items-center justify-between gap-4">
          <label htmlFor="limit-req-burst" className="text-sm font-medium text-foreground">
            Burst
          </label>
          <input
            id="limit-req-burst"
            data-testid="input-LIMIT_REQ_BURST"
            type="text"
            value={settings.LIMIT_REQ_BURST}
            onChange={e => handleChange('LIMIT_REQ_BURST', e.target.value)}
            placeholder="20"
            className="w-32 rounded-md border border-input bg-background px-2 py-1 text-sm font-mono shadow-sm placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring"
          />
        </div>
      </section>

      <section className="space-y-4">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">
          Country Access
        </h2>

        <div className="space-y-1">
          <label htmlFor="blacklist-country" className="text-sm font-medium text-foreground">
            Blocked Countries
          </label>
          <textarea
            id="blacklist-country"
            data-testid="input-BLACKLIST_COUNTRY"
            value={settings.BLACKLIST_COUNTRY}
            onChange={e => handleChange('BLACKLIST_COUNTRY', e.target.value)}
            rows={2}
            placeholder="CN RU KP"
            className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm font-mono shadow-sm placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring"
          />
        </div>

        <div className="space-y-1">
          <label htmlFor="whitelist-country" className="text-sm font-medium text-foreground">
            Allowed Countries Only
          </label>
          <textarea
            id="whitelist-country"
            data-testid="input-WHITELIST_COUNTRY"
            value={settings.WHITELIST_COUNTRY}
            onChange={e => handleChange('WHITELIST_COUNTRY', e.target.value)}
            rows={2}
            placeholder="GB US AU"
            className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm font-mono shadow-sm placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring"
          />
          <p className="text-xs text-muted-foreground">Space-separated 2-letter ISO country codes.</p>
        </div>
      </section>

      {toast && (
        <p className="text-sm text-green-700 dark:text-green-400" data-testid="toast">{toast}</p>
      )}

      <button
        type="submit"
        disabled={saving}
        className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-colors"
      >
        {saving ? 'Saving…' : 'Save Settings'}
      </button>
    </form>
  );
}
