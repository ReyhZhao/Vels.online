import { useState, useEffect } from 'react';
import api from '../lib/axios';

const PARANOIA_LEVELS = [1, 2, 3, 4];

const DEFAULT_WAF = {
  USE_MODSECURITY: 'no',
  USE_MODSECURITY_CRS: 'no',
  MODSECURITY_CRS_PARANOIA_LEVEL: '1',
};

export default function RouteSettings({ fqdn }) {
  const [waf, setWaf] = useState(DEFAULT_WAF);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(null);
  const [saving, setSaving] = useState(false);
  const [toast, setToast] = useState(null);
  const [validationError, setValidationError] = useState(null);

  useEffect(() => {
    api.get(`/api/ingress/routes/${fqdn}/settings/`)
      .then(res => {
        setWaf(prev => ({ ...prev, ...res.data }));
      })
      .catch(() => setLoadError('Failed to load settings.'))
      .finally(() => setLoading(false));
  }, [fqdn]);

  function handleToggle(key) {
    setWaf(w => ({ ...w, [key]: w[key] === 'yes' ? 'no' : 'yes' }));
  }

  function handleParanoiaChange(e) {
    const val = e.target.value;
    setValidationError(null);
    setWaf(w => ({ ...w, MODSECURITY_CRS_PARANOIA_LEVEL: val }));
  }

  async function handleSave(e) {
    e.preventDefault();
    setValidationError(null);
    setToast(null);

    const level = parseInt(waf.MODSECURITY_CRS_PARANOIA_LEVEL, 10);
    if (isNaN(level) || level < 1 || level > 4) {
      setValidationError('Paranoia level must be between 1 and 4.');
      return;
    }

    setSaving(true);
    try {
      await api.patch(`/api/ingress/routes/${fqdn}/settings/`, waf);
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
          <button
            type="button"
            role="switch"
            aria-checked={waf.USE_MODSECURITY === 'yes'}
            onClick={() => handleToggle('USE_MODSECURITY')}
            data-testid="toggle-USE_MODSECURITY"
            className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors ${
              waf.USE_MODSECURITY === 'yes' ? 'bg-primary' : 'bg-muted'
            }`}
          >
            <span
              className={`inline-block h-3 w-3 transform rounded-full bg-white transition-transform ${
                waf.USE_MODSECURITY === 'yes' ? 'translate-x-5' : 'translate-x-1'
              }`}
            />
          </button>
        </label>

        <label className="flex items-center justify-between gap-4">
          <span className="text-sm font-medium text-foreground">Enable OWASP CRS</span>
          <button
            type="button"
            role="switch"
            aria-checked={waf.USE_MODSECURITY_CRS === 'yes'}
            onClick={() => handleToggle('USE_MODSECURITY_CRS')}
            data-testid="toggle-USE_MODSECURITY_CRS"
            className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors ${
              waf.USE_MODSECURITY_CRS === 'yes' ? 'bg-primary' : 'bg-muted'
            }`}
          >
            <span
              className={`inline-block h-3 w-3 transform rounded-full bg-white transition-transform ${
                waf.USE_MODSECURITY_CRS === 'yes' ? 'translate-x-5' : 'translate-x-1'
              }`}
            />
          </button>
        </label>

        <div className="flex items-center justify-between gap-4">
          <label htmlFor="paranoia-level" className="text-sm font-medium text-foreground">
            CRS Paranoia Level
          </label>
          <select
            id="paranoia-level"
            value={waf.MODSECURITY_CRS_PARANOIA_LEVEL}
            onChange={handleParanoiaChange}
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
