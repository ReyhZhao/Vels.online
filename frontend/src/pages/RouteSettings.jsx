import { useState, useEffect, useRef, useCallback } from 'react';
import api from '../lib/axios';
import { COUNTRIES } from '../lib/countries';

// ── Shared UI helpers ────────────────────────────────────────────────────────

function Toggle({ checked, onChange, testId, disabled }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      onClick={onChange}
      disabled={disabled}
      data-testid={testId}
      className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors disabled:opacity-50 ${
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

function TabSaveButton({ saving }) {
  return (
    <button
      type="submit"
      disabled={saving}
      className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-colors"
    >
      {saving ? 'Saving…' : 'Save'}
    </button>
  );
}

function TabToast({ toast }) {
  if (!toast) return null;
  return (
    <p
      data-testid="toast"
      className={`text-sm ${toast.ok ? 'text-green-700 dark:text-green-400' : 'text-destructive'}`}
    >
      {toast.msg}
    </p>
  );
}

function SectionHeading({ children }) {
  return (
    <h3 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">
      {children}
    </h3>
  );
}

// ── IP/CIDR validation ────────────────────────────────────────────────────────

function isValidIpOrCidr(value) {
  const trimmed = value.trim();
  const ipv4Re = /^(\d{1,3}\.){3}\d{1,3}(\/\d{1,2})?$/;
  if (ipv4Re.test(trimmed)) {
    const ip = trimmed.split('/')[0];
    return ip.split('.').every(p => parseInt(p, 10) <= 255);
  }
  const ipv6Re = /^[0-9a-fA-F:]+\/?\d*$/;
  return ipv6Re.test(trimmed) && trimmed.includes(':');
}

// ── GeneralTab ────────────────────────────────────────────────────────────────

function GeneralTab({ fqdn, routeData, onDirtyChange }) {
  const [saved, setSaved] = useState(null);
  const [local, setLocal] = useState(null);
  const [saving, setSaving] = useState(false);
  const [toast, setToast] = useState(null);

  useEffect(() => {
    if (!routeData) return;
    const s = {
      name: routeData.name ?? '',
      backend_host: routeData.backend_host ?? '',
      backend_port: String(routeData.backend_port ?? ''),
      backend_protocol: routeData.backend_protocol ?? 'http',
    };
    setSaved(s);
    setLocal(s);
  }, [routeData]);

  const isDirty = local && saved ? JSON.stringify(local) !== JSON.stringify(saved) : false;

  useEffect(() => {
    onDirtyChange?.(isDirty);
  }, [isDirty]); // eslint-disable-line react-hooks/exhaustive-deps

  function handleChange(key, value) {
    setLocal(prev => ({ ...prev, [key]: value }));
  }

  async function handleSave(e) {
    e.preventDefault();
    setSaving(true);
    setToast(null);
    try {
      const payload = {
        ...local,
        backend_port: parseInt(local.backend_port, 10),
      };
      await api.patch(`/api/ingress/routes/${fqdn}/`, payload);
      setSaved({ ...local });
      setToast({ ok: true, msg: 'Route saved.' });
    } catch (err) {
      setToast({ ok: false, msg: err.response?.data?.detail || 'Failed to save route.' });
    } finally {
      setSaving(false);
    }
  }

  if (!local) return null;

  return (
    <form onSubmit={handleSave} className="space-y-6 max-w-md">
      <div className="space-y-1">
        <label className="text-sm font-medium text-foreground">FQDN</label>
        <p
          data-testid="fqdn-display"
          className="rounded-md border border-input bg-muted px-3 py-2 text-sm font-mono text-muted-foreground"
        >
          {fqdn}
        </p>
      </div>

      <div className="space-y-1">
        <label htmlFor="route-name" className="text-sm font-medium text-foreground">
          Name
        </label>
        <input
          id="route-name"
          data-testid="input-name"
          type="text"
          value={local.name}
          onChange={e => handleChange('name', e.target.value)}
          placeholder="My App"
          className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring"
        />
      </div>

      <div className="space-y-1">
        <label htmlFor="backend-host" className="text-sm font-medium text-foreground">
          Backend Host
        </label>
        <input
          id="backend-host"
          data-testid="input-backend_host"
          type="text"
          value={local.backend_host}
          onChange={e => handleChange('backend_host', e.target.value)}
          placeholder="10.0.0.1"
          className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm font-mono shadow-sm placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring"
        />
      </div>

      <div className="space-y-1">
        <label htmlFor="backend-port" className="text-sm font-medium text-foreground">
          Backend Port
        </label>
        <input
          id="backend-port"
          data-testid="input-backend_port"
          type="number"
          min="1"
          max="65535"
          value={local.backend_port}
          onChange={e => handleChange('backend_port', e.target.value)}
          className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-1 focus:ring-ring"
        />
      </div>

      <div className="space-y-1">
        <label htmlFor="backend-protocol" className="text-sm font-medium text-foreground">
          Backend Protocol
        </label>
        <select
          id="backend-protocol"
          data-testid="select-backend_protocol"
          value={local.backend_protocol}
          onChange={e => handleChange('backend_protocol', e.target.value)}
          className="w-full rounded-md border border-input bg-background px-2 py-2 text-sm shadow-sm focus:outline-none focus:ring-1 focus:ring-ring"
        >
          <option value="http">http</option>
          <option value="https">https</option>
        </select>
      </div>

      <TabToast toast={toast} />
      <TabSaveButton saving={saving} />
    </form>
  );
}

// ── WafTab ────────────────────────────────────────────────────────────────────

const PARANOIA_LABELS = [
  { level: '1', desc: 'Permissive (minimal false positives)' },
  { level: '2', desc: 'Moderate' },
  { level: '3', desc: 'Strict (may block some legitimate traffic)' },
  { level: '4', desc: 'Paranoid (expect false positives)' },
];

const WAF_KEYS = [
  'USE_REDIRECT_HTTP_TO_HTTPS',
  'USE_MODSECURITY',
  'USE_MODSECURITY_CRS',
  'MODSECURITY_CRS_PARANOIA_LEVEL',
];

const WAF_DEFAULTS = {
  USE_REDIRECT_HTTP_TO_HTTPS: 'no',
  USE_MODSECURITY: 'no',
  USE_MODSECURITY_CRS: 'no',
  MODSECURITY_CRS_PARANOIA_LEVEL: '1',
};

function WafTab({ fqdn, initialData, onDirtyChange }) {
  const init = useCallback(() =>
    Object.fromEntries(WAF_KEYS.map(k => [k, initialData?.[k] ?? WAF_DEFAULTS[k]])),
    [initialData]);

  const [saved, setSaved] = useState(init);
  const [local, setLocal] = useState(saved);
  const [saving, setSaving] = useState(false);
  const [toast, setToast] = useState(null);

  const isDirty = JSON.stringify(local) !== JSON.stringify(saved);

  useEffect(() => { onDirtyChange?.(isDirty); }, [isDirty]); // eslint-disable-line

  function handleToggle(key) {
    setLocal(prev => ({ ...prev, [key]: prev[key] === 'yes' ? 'no' : 'yes' }));
  }

  async function handleSave(e) {
    e.preventDefault();
    setSaving(true);
    setToast(null);
    try {
      await api.patch(`/api/ingress/routes/${fqdn}/settings/`, local);
      setSaved({ ...local });
      setToast({ ok: true, msg: 'Settings saved — update queued.' });
    } catch (err) {
      setToast({ ok: false, msg: err.response?.data?.detail || 'Failed to save settings.' });
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={handleSave} className="space-y-6 max-w-md">
      <section className="space-y-4">
        <SectionHeading>HTTPS Redirect</SectionHeading>
        <label className="flex items-center justify-between gap-4">
          <span className="text-sm font-medium text-foreground">Redirect HTTP → HTTPS</span>
          <Toggle
            checked={local.USE_REDIRECT_HTTP_TO_HTTPS === 'yes'}
            onChange={() => handleToggle('USE_REDIRECT_HTTP_TO_HTTPS')}
            testId="toggle-USE_REDIRECT_HTTP_TO_HTTPS"
          />
        </label>
      </section>

      <section className="space-y-4">
        <SectionHeading>Web Application Firewall</SectionHeading>
        <label className="flex items-center justify-between gap-4">
          <span className="text-sm font-medium text-foreground">Enable ModSecurity WAF</span>
          <Toggle
            checked={local.USE_MODSECURITY === 'yes'}
            onChange={() => handleToggle('USE_MODSECURITY')}
            testId="toggle-USE_MODSECURITY"
          />
        </label>
        <label className="flex items-center justify-between gap-4">
          <span className="text-sm font-medium text-foreground">Enable OWASP CRS</span>
          <Toggle
            checked={local.USE_MODSECURITY_CRS === 'yes'}
            onChange={() => handleToggle('USE_MODSECURITY_CRS')}
            testId="toggle-USE_MODSECURITY_CRS"
          />
        </label>

        <div className="space-y-2">
          <label className="text-sm font-medium text-foreground">CRS Paranoia Level</label>
          <div
            className="flex rounded-md border border-input overflow-hidden"
            data-testid="paranoia-segmented"
            role="group"
            aria-label="CRS Paranoia Level"
          >
            {PARANOIA_LABELS.map(({ level, desc }) => (
              <button
                key={level}
                type="button"
                data-testid={`paranoia-level-${level}`}
                aria-pressed={local.MODSECURITY_CRS_PARANOIA_LEVEL === level}
                onClick={() => setLocal(prev => ({ ...prev, MODSECURITY_CRS_PARANOIA_LEVEL: level }))}
                className={`flex-1 px-2 py-2 text-xs transition-colors border-r last:border-r-0 border-input ${
                  local.MODSECURITY_CRS_PARANOIA_LEVEL === level
                    ? 'bg-primary text-primary-foreground font-semibold'
                    : 'bg-background text-muted-foreground hover:text-foreground'
                }`}
              >
                <div className="font-bold">{level}</div>
                <div className="hidden sm:block mt-0.5">{desc}</div>
              </button>
            ))}
          </div>
        </div>
      </section>

      <TabToast toast={toast} />
      <TabSaveButton saving={saving} />
    </form>
  );
}

// ── IpWhitelistTab ────────────────────────────────────────────────────────────

const IP_CAP = 10;

function IpWhitelistTab({ fqdn, initialData, onDirtyChange }) {
  const initChips = useCallback(() =>
    (initialData?.WHITELIST_IP || '').split(/\s+/).filter(Boolean), [initialData]);

  const [savedToggle, setSavedToggle] = useState(initialData?.USE_WHITELIST ?? 'no');
  const [toggle, setToggle] = useState(savedToggle);
  const [savedChips, setSavedChips] = useState(initChips);
  const [chips, setChips] = useState(initChips);
  const [addInput, setAddInput] = useState('');
  const [inputError, setInputError] = useState(null);
  const [saving, setSaving] = useState(false);
  const [toast, setToast] = useState(null);

  const isDirty =
    toggle !== savedToggle ||
    JSON.stringify(chips) !== JSON.stringify(savedChips);

  useEffect(() => { onDirtyChange?.(isDirty); }, [isDirty]); // eslint-disable-line

  function handleAdd() {
    const val = addInput.trim();
    if (!val) return;
    if (!isValidIpOrCidr(val)) {
      setInputError(`Invalid IP or CIDR: ${val}`);
      return;
    }
    if (chips.length >= IP_CAP) return;
    setInputError(null);
    setChips(prev => [...prev, val]);
    setAddInput('');
  }

  function handleRemove(idx) {
    setChips(prev => prev.filter((_, i) => i !== idx));
  }

  async function handleSave(e) {
    e.preventDefault();
    setSaving(true);
    setToast(null);
    try {
      const payload = { USE_WHITELIST: toggle, WHITELIST_IP: chips.join(' ') };
      await api.patch(`/api/ingress/routes/${fqdn}/settings/`, payload);
      setSavedToggle(toggle);
      setSavedChips([...chips]);
      setToast({ ok: true, msg: 'Settings saved — update queued.' });
    } catch (err) {
      setToast({ ok: false, msg: err.response?.data?.detail || 'Failed to save settings.' });
    } finally {
      setSaving(false);
    }
  }

  const atCap = chips.length >= IP_CAP;

  return (
    <form onSubmit={handleSave} className="space-y-6 max-w-md">
      <section className="space-y-4">
        <SectionHeading>IP Whitelist</SectionHeading>
        <label className="flex items-center justify-between gap-4">
          <span className="text-sm font-medium text-foreground">Enable IP Whitelist</span>
          <Toggle
            checked={toggle === 'yes'}
            onChange={() => setToggle(t => t === 'yes' ? 'no' : 'yes')}
            testId="toggle-USE_WHITELIST"
          />
        </label>

        <div className="space-y-2">
          <label className="text-sm font-medium text-foreground">Allowed IPs / CIDRs</label>
          <div className="flex flex-wrap gap-2" data-testid="ip-chip-list">
            {chips.map((chip, idx) => (
              <span
                key={idx}
                className="inline-flex items-center gap-1 rounded-full bg-muted px-3 py-1 text-xs font-mono"
                data-testid={`ip-chip-${idx}`}
              >
                {chip}
                <button
                  type="button"
                  aria-label={`Remove ${chip}`}
                  onClick={() => handleRemove(idx)}
                  className="ml-1 text-muted-foreground hover:text-foreground"
                >
                  ×
                </button>
              </span>
            ))}
          </div>

          {atCap ? (
            <p className="text-xs text-amber-600" data-testid="ip-cap-message">
              Maximum {IP_CAP} entries reached
            </p>
          ) : (
            <div className="flex gap-2">
              <input
                type="text"
                data-testid="ip-add-input"
                value={addInput}
                onChange={e => { setAddInput(e.target.value); setInputError(null); }}
                onKeyDown={e => e.key === 'Enter' && (e.preventDefault(), handleAdd())}
                placeholder="192.168.1.0/24"
                className="flex-1 rounded-md border border-input bg-background px-3 py-1.5 text-sm font-mono shadow-sm focus:outline-none focus:ring-1 focus:ring-ring"
              />
              <button
                type="button"
                data-testid="ip-add-button"
                onClick={handleAdd}
                className="rounded-md border border-input px-3 py-1.5 text-sm hover:bg-muted transition-colors"
              >
                Add
              </button>
            </div>
          )}

          {inputError && (
            <p className="text-xs text-destructive" data-testid="ip-input-error">{inputError}</p>
          )}
        </div>
      </section>

      <TabToast toast={toast} />
      <TabSaveButton saving={saving} />
    </form>
  );
}

// ── RateLimitingTab ───────────────────────────────────────────────────────────

const RATE_UNITS = ['r/s', 'r/m', 'r/h'];

function parseRate(value) {
  if (!value) return { num: '', unit: 'r/s' };
  const m = value.match(/^(\d+)(r\/[smh])$/);
  return m ? { num: m[1], unit: m[2] } : { num: '', unit: 'r/s' };
}

function RateLimitingTab({ fqdn, initialData, onDirtyChange }) {
  const parsed = parseRate(initialData?.LIMIT_REQ_RATE);
  const [savedToggle, setSavedToggle] = useState(initialData?.USE_LIMIT_REQ ?? 'no');
  const [toggle, setToggle] = useState(savedToggle);
  const [savedRate, setSavedRate] = useState(initialData?.LIMIT_REQ_RATE ?? '');
  const [savedBurst, setSavedBurst] = useState(initialData?.LIMIT_REQ_BURST ?? '');
  const [rateNum, setRateNum] = useState(parsed.num);
  const [rateUnit, setRateUnit] = useState(parsed.unit);
  const [burst, setBurst] = useState(initialData?.LIMIT_REQ_BURST ?? '');
  const [rateError, setRateError] = useState(null);
  const [saving, setSaving] = useState(false);
  const [toast, setToast] = useState(null);

  const combinedRate = rateNum ? `${rateNum}${rateUnit}` : '';
  const isDirty =
    toggle !== savedToggle ||
    combinedRate !== savedRate ||
    burst !== savedBurst;

  useEffect(() => { onDirtyChange?.(isDirty); }, [isDirty]); // eslint-disable-line

  async function handleSave(e) {
    e.preventDefault();
    if (toggle === 'yes' && !rateNum) {
      setRateError('Rate is required when rate limiting is enabled.');
      return;
    }
    setRateError(null);
    setSaving(true);
    setToast(null);
    try {
      const payload = {
        USE_LIMIT_REQ: toggle,
        LIMIT_REQ_RATE: combinedRate,
        LIMIT_REQ_BURST: burst,
      };
      await api.patch(`/api/ingress/routes/${fqdn}/settings/`, payload);
      setSavedToggle(toggle);
      setSavedRate(combinedRate);
      setSavedBurst(burst);
      setToast({ ok: true, msg: 'Settings saved — update queued.' });
    } catch (err) {
      setToast({ ok: false, msg: err.response?.data?.detail || 'Failed to save settings.' });
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={handleSave} className="space-y-6 max-w-md">
      <section className="space-y-4">
        <SectionHeading>Rate Limiting</SectionHeading>
        <label className="flex items-center justify-between gap-4">
          <span className="text-sm font-medium text-foreground">Enable Rate Limiting</span>
          <Toggle
            checked={toggle === 'yes'}
            onChange={() => setToggle(t => t === 'yes' ? 'no' : 'yes')}
            testId="toggle-USE_LIMIT_REQ"
          />
        </label>

        <div className="space-y-1">
          <label className="text-sm font-medium text-foreground">Rate</label>
          <div className="flex gap-2 items-center">
            <input
              type="number"
              data-testid="input-LIMIT_REQ_RATE_NUM"
              min="1"
              value={rateNum}
              onChange={e => { setRateNum(e.target.value); setRateError(null); }}
              placeholder="10"
              className="w-24 rounded-md border border-input bg-background px-2 py-1.5 text-sm shadow-sm focus:outline-none focus:ring-1 focus:ring-ring"
            />
            <select
              data-testid="select-LIMIT_REQ_RATE_UNIT"
              value={rateUnit}
              onChange={e => setRateUnit(e.target.value)}
              className="rounded-md border border-input bg-background px-2 py-1.5 text-sm shadow-sm focus:outline-none focus:ring-1 focus:ring-ring"
            >
              {RATE_UNITS.map(u => <option key={u} value={u}>{u}</option>)}
            </select>
          </div>
          {rateError && (
            <p className="text-xs text-destructive" data-testid="rate-error">{rateError}</p>
          )}
        </div>

        <div className="space-y-1">
          <label htmlFor="limit-req-burst" className="text-sm font-medium text-foreground">
            Burst
          </label>
          <input
            id="limit-req-burst"
            data-testid="input-LIMIT_REQ_BURST"
            type="number"
            min="0"
            value={burst}
            onChange={e => setBurst(e.target.value)}
            placeholder="20"
            className="w-32 rounded-md border border-input bg-background px-2 py-1.5 text-sm shadow-sm focus:outline-none focus:ring-1 focus:ring-ring"
          />
        </div>
      </section>

      <TabToast toast={toast} />
      <TabSaveButton saving={saving} />
    </form>
  );
}

// ── CountryTab ────────────────────────────────────────────────────────────────

function CountryChipList({ label, chips, onChange, testIdPrefix }) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const containerRef = useRef(null);

  useEffect(() => {
    if (!open) return;
    function handleClick(e) {
      if (!containerRef.current?.contains(e.target)) setOpen(false);
    }
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, [open]);

  const filtered = COUNTRIES.filter(
    c =>
      !chips.includes(c.code) &&
      (c.code.toLowerCase().includes(query.toLowerCase()) ||
        c.name.toLowerCase().includes(query.toLowerCase()))
  );

  function addChip(code) {
    onChange([...chips, code]);
  }

  function removeChip(code) {
    onChange(chips.filter(c => c !== code));
  }

  return (
    <div className="space-y-2" ref={containerRef}>
      <label className="text-sm font-medium text-foreground">{label}</label>
      <div className="flex flex-wrap gap-2" data-testid={`${testIdPrefix}-chips`}>
        {chips.map(code => (
          <span
            key={code}
            className="inline-flex items-center gap-1 rounded-full bg-muted px-3 py-1 text-xs font-mono"
            data-testid={`${testIdPrefix}-chip-${code}`}
          >
            {code}
            <button
              type="button"
              aria-label={`Remove ${code}`}
              onClick={() => removeChip(code)}
              className="ml-1 text-muted-foreground hover:text-foreground"
            >
              ×
            </button>
          </span>
        ))}
      </div>

      <div className="relative inline-block">
        <button
          type="button"
          data-testid={`${testIdPrefix}-add-btn`}
          onClick={() => { setOpen(o => !o); setQuery(''); }}
          className="rounded-md border border-input px-3 py-1.5 text-sm hover:bg-muted transition-colors"
        >
          Add country
        </button>

        {open && (
          <div
            data-testid={`${testIdPrefix}-popover`}
            className="absolute left-0 top-full mt-1 z-50 w-64 rounded-md border border-border bg-background shadow-lg"
          >
            <div className="p-2 border-b border-border">
              <input
                type="text"
                autoFocus
                data-testid={`${testIdPrefix}-search`}
                value={query}
                onChange={e => setQuery(e.target.value)}
                placeholder="Search country…"
                className="w-full rounded-md border border-input bg-background px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
              />
            </div>
            <ul className="max-h-48 overflow-y-auto py-1">
              {filtered.length === 0 ? (
                <li className="px-3 py-2 text-xs text-muted-foreground">No results</li>
              ) : (
                filtered.map(c => (
                  <li key={c.code}>
                    <button
                      type="button"
                      data-testid={`${testIdPrefix}-option-${c.code}`}
                      onClick={() => { addChip(c.code); setOpen(false); setQuery(''); }}
                      className="w-full px-3 py-1.5 text-left text-sm hover:bg-muted transition-colors"
                    >
                      <span className="font-mono font-semibold">{c.code}</span>
                      <span className="ml-2 text-muted-foreground">{c.name}</span>
                    </button>
                  </li>
                ))
              )}
            </ul>
          </div>
        )}
      </div>
    </div>
  );
}

function CountryTab({ fqdn, initialData, onDirtyChange }) {
  const initBlacklist = useCallback(() =>
    (initialData?.BLACKLIST_COUNTRY || '').split(/\s+/).filter(Boolean), [initialData]);
  const initWhitelist = useCallback(() =>
    (initialData?.WHITELIST_COUNTRY || '').split(/\s+/).filter(Boolean), [initialData]);

  const [savedBlacklist, setSavedBlacklist] = useState(initBlacklist);
  const [savedWhitelist, setSavedWhitelist] = useState(initWhitelist);
  const [blacklist, setBlacklist] = useState(initBlacklist);
  const [whitelist, setWhitelist] = useState(initWhitelist);
  const [saving, setSaving] = useState(false);
  const [toast, setToast] = useState(null);

  const isDirty =
    JSON.stringify(blacklist) !== JSON.stringify(savedBlacklist) ||
    JSON.stringify(whitelist) !== JSON.stringify(savedWhitelist);

  useEffect(() => { onDirtyChange?.(isDirty); }, [isDirty]); // eslint-disable-line

  async function handleSave(e) {
    e.preventDefault();
    setSaving(true);
    setToast(null);
    try {
      const payload = {
        BLACKLIST_COUNTRY: blacklist.join(' '),
        WHITELIST_COUNTRY: whitelist.join(' '),
      };
      await api.patch(`/api/ingress/routes/${fqdn}/settings/`, payload);
      setSavedBlacklist([...blacklist]);
      setSavedWhitelist([...whitelist]);
      setToast({ ok: true, msg: 'Settings saved — update queued.' });
    } catch (err) {
      setToast({ ok: false, msg: err.response?.data?.detail || 'Failed to save settings.' });
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={handleSave} className="space-y-6 max-w-md">
      <section className="space-y-4">
        <SectionHeading>Country Access</SectionHeading>
        <CountryChipList
          label="Blocked Countries"
          chips={blacklist}
          onChange={setBlacklist}
          testIdPrefix="blacklist"
        />
        <CountryChipList
          label="Allowed Countries Only"
          chips={whitelist}
          onChange={setWhitelist}
          testIdPrefix="whitelist"
        />
      </section>

      <TabToast toast={toast} />
      <TabSaveButton saving={saving} />
    </form>
  );
}

// ── BotProtectionTab ──────────────────────────────────────────────────────────

const BOT_KEYS = [
  'USE_ANTIBOT', 'ANTIBOT_TYPE', 'ANTIBOT_RECAPTCHA_SCORE',
  'ANTIBOT_RECAPTCHA_SITEKEY', 'ANTIBOT_RECAPTCHA_SECRET',
  'ANTIBOT_HCAPTCHA_SITEKEY', 'ANTIBOT_HCAPTCHA_SECRET',
  'ANTIBOT_TURNSTILE_SITEKEY', 'ANTIBOT_TURNSTILE_SECRET',
];

const BOT_DEFAULTS = {
  USE_ANTIBOT: 'no',
  ANTIBOT_TYPE: 'cookie',
  ANTIBOT_RECAPTCHA_SCORE: '',
  ANTIBOT_RECAPTCHA_SITEKEY: '',
  ANTIBOT_RECAPTCHA_SECRET: '',
  ANTIBOT_HCAPTCHA_SITEKEY: '',
  ANTIBOT_HCAPTCHA_SECRET: '',
  ANTIBOT_TURNSTILE_SITEKEY: '',
  ANTIBOT_TURNSTILE_SECRET: '',
};

const ANTIBOT_TYPE_OPTIONS = [
  { value: 'cookie', label: 'Cookie (silent)' },
  { value: 'javascript', label: 'JavaScript' },
  { value: 'recaptcha', label: 'reCAPTCHA v3' },
  { value: 'hcaptcha', label: 'hCaptcha' },
  { value: 'turnstile', label: 'Turnstile' },
];

function BotProtectionTab({ fqdn, initialData, onDirtyChange }) {
  const init = useCallback(() =>
    Object.fromEntries(BOT_KEYS.map(k => [k, initialData?.[k] ?? BOT_DEFAULTS[k]])),
    [initialData]);

  const [saved, setSaved] = useState(init);
  const [local, setLocal] = useState(saved);
  const [saving, setSaving] = useState(false);
  const [toast, setToast] = useState(null);

  const isDirty = JSON.stringify(local) !== JSON.stringify(saved);
  useEffect(() => { onDirtyChange?.(isDirty); }, [isDirty]); // eslint-disable-line

  function handleChange(key, value) {
    setLocal(prev => ({ ...prev, [key]: value }));
  }

  async function handleSave(e) {
    e.preventDefault();
    setSaving(true);
    setToast(null);
    try {
      await api.patch(`/api/ingress/routes/${fqdn}/settings/`, local);
      setSaved({ ...local });
      setToast({ ok: true, msg: 'Settings saved — update queued.' });
    } catch (err) {
      setToast({ ok: false, msg: err.response?.data?.detail || 'Failed to save settings.' });
    } finally {
      setSaving(false);
    }
  }

  const type = local.ANTIBOT_TYPE;

  return (
    <form onSubmit={handleSave} className="space-y-6 max-w-md">
      <section className="space-y-4">
        <SectionHeading>Bot Protection</SectionHeading>

        <label className="flex items-center justify-between gap-4">
          <span className="text-sm font-medium text-foreground">Enable Bot Protection</span>
          <Toggle
            checked={local.USE_ANTIBOT === 'yes'}
            onChange={() => handleChange('USE_ANTIBOT', local.USE_ANTIBOT === 'yes' ? 'no' : 'yes')}
            testId="toggle-USE_ANTIBOT"
          />
        </label>

        <div className="space-y-1">
          <label htmlFor="antibot-type" className="text-sm font-medium text-foreground">
            Challenge Type
          </label>
          <select
            id="antibot-type"
            data-testid="select-ANTIBOT_TYPE"
            value={type}
            onChange={e => handleChange('ANTIBOT_TYPE', e.target.value)}
            className="w-full rounded-md border border-input bg-background px-2 py-2 text-sm shadow-sm focus:outline-none focus:ring-1 focus:ring-ring"
          >
            {ANTIBOT_TYPE_OPTIONS.map(o => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>
        </div>

        {type === 'recaptcha' && (
          <div className="space-y-3" data-testid="recaptcha-fields">
            <CredentialField label="Site Key" value={local.ANTIBOT_RECAPTCHA_SITEKEY}
              onChange={v => handleChange('ANTIBOT_RECAPTCHA_SITEKEY', v)} testId="input-ANTIBOT_RECAPTCHA_SITEKEY" />
            <CredentialField label="Secret Key" value={local.ANTIBOT_RECAPTCHA_SECRET}
              onChange={v => handleChange('ANTIBOT_RECAPTCHA_SECRET', v)} testId="input-ANTIBOT_RECAPTCHA_SECRET" />
            <div className="space-y-1">
              <label className="text-sm font-medium text-foreground">Score Threshold</label>
              <input type="number" step="0.1" min="0" max="1"
                data-testid="input-ANTIBOT_RECAPTCHA_SCORE"
                value={local.ANTIBOT_RECAPTCHA_SCORE}
                onChange={e => handleChange('ANTIBOT_RECAPTCHA_SCORE', e.target.value)}
                placeholder="0.5"
                className="w-32 rounded-md border border-input bg-background px-2 py-1.5 text-sm shadow-sm focus:outline-none focus:ring-1 focus:ring-ring"
              />
            </div>
          </div>
        )}

        {type === 'hcaptcha' && (
          <div className="space-y-3" data-testid="hcaptcha-fields">
            <CredentialField label="Site Key" value={local.ANTIBOT_HCAPTCHA_SITEKEY}
              onChange={v => handleChange('ANTIBOT_HCAPTCHA_SITEKEY', v)} testId="input-ANTIBOT_HCAPTCHA_SITEKEY" />
            <CredentialField label="Secret Key" value={local.ANTIBOT_HCAPTCHA_SECRET}
              onChange={v => handleChange('ANTIBOT_HCAPTCHA_SECRET', v)} testId="input-ANTIBOT_HCAPTCHA_SECRET" />
          </div>
        )}

        {type === 'turnstile' && (
          <div className="space-y-3" data-testid="turnstile-fields">
            <CredentialField label="Site Key" value={local.ANTIBOT_TURNSTILE_SITEKEY}
              onChange={v => handleChange('ANTIBOT_TURNSTILE_SITEKEY', v)} testId="input-ANTIBOT_TURNSTILE_SITEKEY" />
            <CredentialField label="Secret Key" value={local.ANTIBOT_TURNSTILE_SECRET}
              onChange={v => handleChange('ANTIBOT_TURNSTILE_SECRET', v)} testId="input-ANTIBOT_TURNSTILE_SECRET" />
          </div>
        )}
      </section>

      <TabToast toast={toast} />
      <TabSaveButton saving={saving} />
    </form>
  );
}

function CredentialField({ label, value, onChange, testId }) {
  return (
    <div className="space-y-1">
      <label className="text-sm font-medium text-foreground">{label}</label>
      <input type="text" data-testid={testId} value={value}
        onChange={e => onChange(e.target.value)}
        className="w-full rounded-md border border-input bg-background px-3 py-1.5 text-sm font-mono shadow-sm focus:outline-none focus:ring-1 focus:ring-ring"
      />
    </div>
  );
}

// ── AdvancedTab ───────────────────────────────────────────────────────────────

const HTTP_VERBS = ['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD', 'OPTIONS', 'CONNECT', 'TRACE'];
const CLIENT_SIZE_UNITS = ['k', 'm', 'g'];

function parseMaxClientSize(value) {
  if (!value || value === '0') return { val: value || '', unit: 'm' };
  const m = String(value).match(/^(\d+)([kmgKMG])$/);
  return m ? { val: m[1], unit: m[2].toLowerCase() } : { val: '', unit: 'm' };
}

const ADV_SIMPLE_KEYS = [
  'REVERSE_PROXY_CONNECT_TIMEOUT', 'REVERSE_PROXY_READ_TIMEOUT', 'REVERSE_PROXY_SEND_TIMEOUT',
  'USE_REVERSE_PROXY_WS', 'USE_REVERSE_PROXY_BUFFERING',
  'REVERSE_PROXY_BUFFER_SIZE', 'REVERSE_PROXY_BUFFERS', 'REVERSE_PROXY_MAX_TEMP_FILE_SIZE',
  'USE_REAL_IP', 'REAL_IP_RECURSIVE', 'REAL_IP_HEADER',
  'USE_CORS', 'CORS_ALLOW_ORIGIN', 'CORS_ALLOW_HEADERS', 'CORS_ALLOW_METHODS',
  'CORS_EXPOSE_HEADERS', 'CORS_MAX_AGE', 'CORS_ALLOW_CREDENTIALS',
];

const ADV_DEFAULTS = Object.fromEntries(ADV_SIMPLE_KEYS.map(k => [k, '']));
Object.assign(ADV_DEFAULTS, {
  USE_REVERSE_PROXY_WS: 'no', USE_REVERSE_PROXY_BUFFERING: 'no',
  USE_REAL_IP: 'no', REAL_IP_RECURSIVE: 'no',
  USE_CORS: 'no', CORS_ALLOW_CREDENTIALS: 'no',
});

function AdvancedTab({ fqdn, initialData, onDirtyChange }) {
  const initSimple = useCallback(() =>
    Object.fromEntries(ADV_SIMPLE_KEYS.map(k => [k, initialData?.[k] ?? ADV_DEFAULTS[k]])),
    [initialData]);

  const initMethods = useCallback(() => {
    const raw = initialData?.ALLOWED_METHODS || '';
    return raw ? raw.split('|').filter(v => HTTP_VERBS.includes(v)) : [];
  }, [initialData]);

  const { val: initSizeVal, unit: initSizeUnit } = parseMaxClientSize(initialData?.MAX_CLIENT_SIZE || '');

  const [savedSimple, setSavedSimple] = useState(initSimple);
  const [local, setLocal] = useState(savedSimple);
  const [savedMethods, setSavedMethods] = useState(initMethods);
  const [methods, setMethods] = useState(initMethods);
  const [savedSizeVal, setSavedSizeVal] = useState(initSizeVal);
  const [savedSizeUnit, setSavedSizeUnit] = useState(initSizeUnit);
  const [sizeVal, setSizeVal] = useState(initSizeVal);
  const [sizeUnit, setSizeUnit] = useState(initSizeUnit);
  const [saving, setSaving] = useState(false);
  const [toast, setToast] = useState(null);

  const combinedSize = sizeVal === '0' ? '0' : sizeVal ? `${sizeVal}${sizeUnit}` : '';
  const savedCombinedSize = savedSizeVal === '0' ? '0' : savedSizeVal ? `${savedSizeVal}${savedSizeUnit}` : '';

  const isDirty =
    JSON.stringify(local) !== JSON.stringify(savedSimple) ||
    JSON.stringify(methods) !== JSON.stringify(savedMethods) ||
    combinedSize !== savedCombinedSize;

  useEffect(() => { onDirtyChange?.(isDirty); }, [isDirty]); // eslint-disable-line

  function handleChange(key, value) {
    setLocal(prev => ({ ...prev, [key]: value }));
  }

  function handleToggle(key) {
    setLocal(prev => ({ ...prev, [key]: prev[key] === 'yes' ? 'no' : 'yes' }));
  }

  function toggleMethod(verb) {
    setMethods(prev =>
      prev.includes(verb) ? prev.filter(v => v !== verb) : [...prev, verb]
    );
  }

  async function handleSave(e) {
    e.preventDefault();
    setSaving(true);
    setToast(null);
    try {
      const payload = {
        ...local,
        ALLOWED_METHODS: methods.join('|'),
        MAX_CLIENT_SIZE: combinedSize,
      };
      await api.patch(`/api/ingress/routes/${fqdn}/settings/`, payload);
      setSavedSimple({ ...local });
      setSavedMethods([...methods]);
      setSavedSizeVal(sizeVal);
      setSavedSizeUnit(sizeUnit);
      setToast({ ok: true, msg: 'Settings saved — update queued.' });
    } catch (err) {
      setToast({ ok: false, msg: err.response?.data?.detail || 'Failed to save settings.' });
    } finally {
      setSaving(false);
    }
  }

  const inputCls = 'rounded-md border border-input bg-background px-2 py-1.5 text-sm shadow-sm focus:outline-none focus:ring-1 focus:ring-ring';

  return (
    <form onSubmit={handleSave} className="space-y-8 max-w-lg">
      <section className="space-y-4">
        <SectionHeading>Proxy</SectionHeading>
        {['REVERSE_PROXY_CONNECT_TIMEOUT', 'REVERSE_PROXY_READ_TIMEOUT', 'REVERSE_PROXY_SEND_TIMEOUT'].map(key => {
          const labelMap = {
            REVERSE_PROXY_CONNECT_TIMEOUT: 'Connect timeout (s)',
            REVERSE_PROXY_READ_TIMEOUT: 'Read timeout (s)',
            REVERSE_PROXY_SEND_TIMEOUT: 'Send timeout (s)',
          };
          return (
            <div key={key} className="flex items-center justify-between gap-4">
              <label className="text-sm font-medium text-foreground">{labelMap[key]}</label>
              <input type="number" min="1" data-testid={`input-${key}`}
                value={local[key]} onChange={e => handleChange(key, e.target.value)}
                className={`w-24 ${inputCls}`} />
            </div>
          );
        })}
        <label className="flex items-center justify-between gap-4">
          <span className="text-sm font-medium text-foreground">WebSocket proxying</span>
          <Toggle checked={local.USE_REVERSE_PROXY_WS === 'yes'}
            onChange={() => handleToggle('USE_REVERSE_PROXY_WS')}
            testId="toggle-USE_REVERSE_PROXY_WS" />
        </label>
        <label className="flex items-center justify-between gap-4">
          <span className="text-sm font-medium text-foreground">Proxy buffering</span>
          <Toggle checked={local.USE_REVERSE_PROXY_BUFFERING === 'yes'}
            onChange={() => handleToggle('USE_REVERSE_PROXY_BUFFERING')}
            testId="toggle-USE_REVERSE_PROXY_BUFFERING" />
        </label>
        {['REVERSE_PROXY_BUFFER_SIZE', 'REVERSE_PROXY_BUFFERS', 'REVERSE_PROXY_MAX_TEMP_FILE_SIZE'].map(key => (
          <div key={key} className="space-y-1">
            <label className="text-sm font-medium text-foreground">{key.replace(/_/g, ' ').toLowerCase().replace(/^\w/, c => c.toUpperCase())}</label>
            <input type="text" data-testid={`input-${key}`} value={local[key]}
              onChange={e => handleChange(key, e.target.value)}
              className={`w-full font-mono ${inputCls}`} />
          </div>
        ))}
      </section>

      <section className="space-y-4">
        <SectionHeading>Request</SectionHeading>
        <div className="space-y-2">
          <label className="text-sm font-medium text-foreground">Allowed HTTP Methods</label>
          <div className="flex flex-wrap gap-2" data-testid="allowed-methods-checkboxes">
            {HTTP_VERBS.map(verb => (
              <label key={verb} className="flex items-center gap-1.5 text-sm cursor-pointer">
                <input type="checkbox" data-testid={`method-${verb}`}
                  checked={methods.includes(verb)}
                  onChange={() => toggleMethod(verb)}
                  className="rounded border-input" />
                {verb}
              </label>
            ))}
          </div>
        </div>
        <div className="space-y-1">
          <label className="text-sm font-medium text-foreground">Max Request Body Size</label>
          <div className="flex gap-2 items-center">
            <input type="number" min="0" data-testid="input-MAX_CLIENT_SIZE_VAL"
              value={sizeVal}
              onChange={e => setSizeVal(e.target.value)}
              placeholder="10"
              className={`w-24 ${inputCls}`} />
            <select data-testid="select-MAX_CLIENT_SIZE_UNIT"
              value={sizeUnit}
              disabled={sizeVal === '0'}
              onChange={e => setSizeUnit(e.target.value)}
              className={`${inputCls} disabled:opacity-50`}>
              {CLIENT_SIZE_UNITS.map(u => <option key={u} value={u}>{u}</option>)}
            </select>
            {sizeVal === '0' && (
              <span className="text-xs text-muted-foreground">(unlimited)</span>
            )}
          </div>
        </div>
      </section>

      <section className="space-y-4">
        <SectionHeading>Real IP</SectionHeading>
        <label className="flex items-center justify-between gap-4">
          <span className="text-sm font-medium text-foreground">Enable real IP extraction</span>
          <Toggle checked={local.USE_REAL_IP === 'yes'}
            onChange={() => handleToggle('USE_REAL_IP')}
            testId="toggle-USE_REAL_IP" />
        </label>
        <label className="flex items-center justify-between gap-4">
          <span className="text-sm font-medium text-foreground">Recursive lookup</span>
          <Toggle checked={local.REAL_IP_RECURSIVE === 'yes'}
            onChange={() => handleToggle('REAL_IP_RECURSIVE')}
            testId="toggle-REAL_IP_RECURSIVE" />
        </label>
        <div className="space-y-1">
          <label className="text-sm font-medium text-foreground">IP Header</label>
          <input type="text" data-testid="input-REAL_IP_HEADER"
            value={local.REAL_IP_HEADER}
            onChange={e => handleChange('REAL_IP_HEADER', e.target.value)}
            placeholder="X-Forwarded-For"
            className={`w-full ${inputCls}`} />
        </div>
      </section>

      <section className="space-y-4">
        <SectionHeading>CORS</SectionHeading>
        <label className="flex items-center justify-between gap-4">
          <span className="text-sm font-medium text-foreground">Enable CORS</span>
          <Toggle checked={local.USE_CORS === 'yes'}
            onChange={() => handleToggle('USE_CORS')}
            testId="toggle-USE_CORS" />
        </label>
        {['CORS_ALLOW_ORIGIN', 'CORS_ALLOW_HEADERS', 'CORS_ALLOW_METHODS', 'CORS_EXPOSE_HEADERS'].map(key => (
          <div key={key} className="space-y-1">
            <label className="text-sm font-medium text-foreground">{key.replace(/_/g, ' ').toLowerCase().replace(/^\w/, c => c.toUpperCase())}</label>
            <input type="text" data-testid={`input-${key}`} value={local[key]}
              onChange={e => handleChange(key, e.target.value)}
              className={`w-full ${inputCls}`} />
          </div>
        ))}
        <div className="space-y-1">
          <label className="text-sm font-medium text-foreground">Max Age (seconds)</label>
          <input type="number" min="0" data-testid="input-CORS_MAX_AGE"
            value={local.CORS_MAX_AGE}
            onChange={e => handleChange('CORS_MAX_AGE', e.target.value)}
            className={`w-32 ${inputCls}`} />
        </div>
        <label className="flex items-center justify-between gap-4">
          <span className="text-sm font-medium text-foreground">Allow Credentials</span>
          <Toggle checked={local.CORS_ALLOW_CREDENTIALS === 'yes'}
            onChange={() => handleToggle('CORS_ALLOW_CREDENTIALS')}
            testId="toggle-CORS_ALLOW_CREDENTIALS" />
        </label>
      </section>

      <TabToast toast={toast} />
      <TabSaveButton saving={saving} />
    </form>
  );
}

// ── Main shell ────────────────────────────────────────────────────────────────

const SUB_TABS = [
  { key: 'general',       label: 'General' },
  { key: 'waf',           label: 'WAF' },
  { key: 'ip-whitelist',  label: 'IP Whitelist' },
  { key: 'rate-limiting', label: 'Rate Limiting' },
  { key: 'country',       label: 'Country' },
  { key: 'bot-protection',label: 'Bot Protection' },
  { key: 'advanced',      label: 'Advanced' },
];

export default function RouteSettings({ fqdn }) {
  const [activeTab, setActiveTab] = useState('general');
  const [mountedTabs, setMountedTabs] = useState(() => new Set(['general']));
  const [dirtyTabs, setDirtyTabs] = useState({});
  const [bwSettings, setBwSettings] = useState({});
  const [routeData, setRouteData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(null);
  const [syncWarning, setSyncWarning] = useState(false);

  useEffect(() => {
    Promise.all([
      api.get(`/api/ingress/routes/${fqdn}/settings/`),
      api.get(`/api/ingress/routes/${fqdn}/`),
    ])
      .then(([settingsRes, routeRes]) => {
        const data = settingsRes.data ?? {};
        setBwSettings(data);
        if (Object.keys(data).length === 0) setSyncWarning(true);
        setRouteData(routeRes.data);
      })
      .catch(() => setLoadError('Failed to load settings.'))
      .finally(() => setLoading(false));
  }, [fqdn]);

  function handleTabClick(key) {
    setActiveTab(key);
    setMountedTabs(prev => new Set([...prev, key]));
  }

  function makeOnDirtyChange(key) {
    return isDirty => setDirtyTabs(prev => ({ ...prev, [key]: isDirty }));
  }

  if (loading) return <p className="text-sm text-muted-foreground">Loading settings…</p>;
  if (loadError) return <p className="text-sm text-destructive">{loadError}</p>;

  return (
    <div className="space-y-4">
      {syncWarning && (
        <div
          className="rounded-md border border-amber-400 bg-amber-50 px-4 py-3 text-sm text-amber-800 dark:border-amber-600 dark:bg-amber-900/20 dark:text-amber-300"
          data-testid="sync-warning"
        >
          Current settings could not be loaded from BunkerWeb. Showing defaults — saving will apply these values.
        </div>
      )}

      <div className="border-b border-border">
        <nav className="flex gap-1 overflow-x-auto" aria-label="Settings sub-tabs">
          {SUB_TABS.map(tab => (
            <button
              key={tab.key}
              data-testid={`subtab-${tab.key}`}
              onClick={() => handleTabClick(tab.key)}
              className={`relative whitespace-nowrap pb-2 px-3 text-sm font-medium border-b-2 transition-colors ${
                activeTab === tab.key
                  ? 'border-primary text-foreground'
                  : 'border-transparent text-muted-foreground hover:text-foreground'
              }`}
            >
              {tab.label}
              {dirtyTabs[tab.key] && (
                <span
                  data-testid={`dirty-dot-${tab.key}`}
                  className="absolute top-1 right-1 h-1.5 w-1.5 rounded-full bg-primary"
                  aria-label="unsaved changes"
                />
              )}
            </button>
          ))}
        </nav>
      </div>

      <div>
        {SUB_TABS.map(tab => {
          if (!mountedTabs.has(tab.key)) return null;
          return (
            <div key={tab.key} className={activeTab !== tab.key ? 'hidden' : ''} aria-hidden={activeTab !== tab.key || undefined}>
              {tab.key === 'general' && (
                <GeneralTab fqdn={fqdn} routeData={routeData} onDirtyChange={makeOnDirtyChange('general')} />
              )}
              {tab.key === 'waf' && (
                <WafTab fqdn={fqdn} initialData={bwSettings} onDirtyChange={makeOnDirtyChange('waf')} />
              )}
              {tab.key === 'ip-whitelist' && (
                <IpWhitelistTab fqdn={fqdn} initialData={bwSettings} onDirtyChange={makeOnDirtyChange('ip-whitelist')} />
              )}
              {tab.key === 'rate-limiting' && (
                <RateLimitingTab fqdn={fqdn} initialData={bwSettings} onDirtyChange={makeOnDirtyChange('rate-limiting')} />
              )}
              {tab.key === 'country' && (
                <CountryTab fqdn={fqdn} initialData={bwSettings} onDirtyChange={makeOnDirtyChange('country')} />
              )}
              {tab.key === 'bot-protection' && (
                <BotProtectionTab fqdn={fqdn} initialData={bwSettings} onDirtyChange={makeOnDirtyChange('bot-protection')} />
              )}
              {tab.key === 'advanced' && (
                <AdvancedTab fqdn={fqdn} initialData={bwSettings} onDirtyChange={makeOnDirtyChange('advanced')} />
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
