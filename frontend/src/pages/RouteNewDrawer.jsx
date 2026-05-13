import { useState, useEffect, useRef } from 'react';
import api from '../lib/axios';

// ─── ISO 3166-1 alpha-2 country list ─────────────────────────────────

const COUNTRIES = [
  { code: 'AF', name: 'Afghanistan' }, { code: 'AL', name: 'Albania' },
  { code: 'DZ', name: 'Algeria' }, { code: 'AD', name: 'Andorra' },
  { code: 'AO', name: 'Angola' }, { code: 'AG', name: 'Antigua and Barbuda' },
  { code: 'AR', name: 'Argentina' }, { code: 'AM', name: 'Armenia' },
  { code: 'AU', name: 'Australia' }, { code: 'AT', name: 'Austria' },
  { code: 'AZ', name: 'Azerbaijan' }, { code: 'BS', name: 'Bahamas' },
  { code: 'BH', name: 'Bahrain' }, { code: 'BD', name: 'Bangladesh' },
  { code: 'BB', name: 'Barbados' }, { code: 'BY', name: 'Belarus' },
  { code: 'BE', name: 'Belgium' }, { code: 'BZ', name: 'Belize' },
  { code: 'BJ', name: 'Benin' }, { code: 'BT', name: 'Bhutan' },
  { code: 'BO', name: 'Bolivia' }, { code: 'BA', name: 'Bosnia and Herzegovina' },
  { code: 'BW', name: 'Botswana' }, { code: 'BR', name: 'Brazil' },
  { code: 'BN', name: 'Brunei' }, { code: 'BG', name: 'Bulgaria' },
  { code: 'BF', name: 'Burkina Faso' }, { code: 'BI', name: 'Burundi' },
  { code: 'CV', name: 'Cabo Verde' }, { code: 'KH', name: 'Cambodia' },
  { code: 'CM', name: 'Cameroon' }, { code: 'CA', name: 'Canada' },
  { code: 'CF', name: 'Central African Republic' }, { code: 'TD', name: 'Chad' },
  { code: 'CL', name: 'Chile' }, { code: 'CN', name: 'China' },
  { code: 'CO', name: 'Colombia' }, { code: 'KM', name: 'Comoros' },
  { code: 'CD', name: 'Congo (DRC)' }, { code: 'CG', name: 'Congo (Republic)' },
  { code: 'CR', name: 'Costa Rica' }, { code: 'CI', name: "Côte d'Ivoire" },
  { code: 'HR', name: 'Croatia' }, { code: 'CU', name: 'Cuba' },
  { code: 'CY', name: 'Cyprus' }, { code: 'CZ', name: 'Czech Republic' },
  { code: 'DK', name: 'Denmark' }, { code: 'DJ', name: 'Djibouti' },
  { code: 'DM', name: 'Dominica' }, { code: 'DO', name: 'Dominican Republic' },
  { code: 'EC', name: 'Ecuador' }, { code: 'EG', name: 'Egypt' },
  { code: 'SV', name: 'El Salvador' }, { code: 'GQ', name: 'Equatorial Guinea' },
  { code: 'ER', name: 'Eritrea' }, { code: 'EE', name: 'Estonia' },
  { code: 'SZ', name: 'Eswatini' }, { code: 'ET', name: 'Ethiopia' },
  { code: 'FJ', name: 'Fiji' }, { code: 'FI', name: 'Finland' },
  { code: 'FR', name: 'France' }, { code: 'GA', name: 'Gabon' },
  { code: 'GM', name: 'Gambia' }, { code: 'GE', name: 'Georgia' },
  { code: 'DE', name: 'Germany' }, { code: 'GH', name: 'Ghana' },
  { code: 'GR', name: 'Greece' }, { code: 'GD', name: 'Grenada' },
  { code: 'GT', name: 'Guatemala' }, { code: 'GN', name: 'Guinea' },
  { code: 'GW', name: 'Guinea-Bissau' }, { code: 'GY', name: 'Guyana' },
  { code: 'HT', name: 'Haiti' }, { code: 'HN', name: 'Honduras' },
  { code: 'HK', name: 'Hong Kong' }, { code: 'HU', name: 'Hungary' },
  { code: 'IS', name: 'Iceland' }, { code: 'IN', name: 'India' },
  { code: 'ID', name: 'Indonesia' }, { code: 'IR', name: 'Iran' },
  { code: 'IQ', name: 'Iraq' }, { code: 'IE', name: 'Ireland' },
  { code: 'IL', name: 'Israel' }, { code: 'IT', name: 'Italy' },
  { code: 'JM', name: 'Jamaica' }, { code: 'JP', name: 'Japan' },
  { code: 'JO', name: 'Jordan' }, { code: 'KZ', name: 'Kazakhstan' },
  { code: 'KE', name: 'Kenya' }, { code: 'KI', name: 'Kiribati' },
  { code: 'KP', name: 'North Korea' }, { code: 'KR', name: 'South Korea' },
  { code: 'KW', name: 'Kuwait' }, { code: 'KG', name: 'Kyrgyzstan' },
  { code: 'LA', name: 'Laos' }, { code: 'LV', name: 'Latvia' },
  { code: 'LB', name: 'Lebanon' }, { code: 'LS', name: 'Lesotho' },
  { code: 'LR', name: 'Liberia' }, { code: 'LY', name: 'Libya' },
  { code: 'LI', name: 'Liechtenstein' }, { code: 'LT', name: 'Lithuania' },
  { code: 'LU', name: 'Luxembourg' }, { code: 'MO', name: 'Macao' },
  { code: 'MG', name: 'Madagascar' }, { code: 'MW', name: 'Malawi' },
  { code: 'MY', name: 'Malaysia' }, { code: 'MV', name: 'Maldives' },
  { code: 'ML', name: 'Mali' }, { code: 'MT', name: 'Malta' },
  { code: 'MH', name: 'Marshall Islands' }, { code: 'MR', name: 'Mauritania' },
  { code: 'MU', name: 'Mauritius' }, { code: 'MX', name: 'Mexico' },
  { code: 'FM', name: 'Micronesia' }, { code: 'MD', name: 'Moldova' },
  { code: 'MC', name: 'Monaco' }, { code: 'MN', name: 'Mongolia' },
  { code: 'ME', name: 'Montenegro' }, { code: 'MA', name: 'Morocco' },
  { code: 'MZ', name: 'Mozambique' }, { code: 'MM', name: 'Myanmar' },
  { code: 'NA', name: 'Namibia' }, { code: 'NR', name: 'Nauru' },
  { code: 'NP', name: 'Nepal' }, { code: 'NL', name: 'Netherlands' },
  { code: 'NZ', name: 'New Zealand' }, { code: 'NI', name: 'Nicaragua' },
  { code: 'NE', name: 'Niger' }, { code: 'NG', name: 'Nigeria' },
  { code: 'MK', name: 'North Macedonia' }, { code: 'NO', name: 'Norway' },
  { code: 'OM', name: 'Oman' }, { code: 'PK', name: 'Pakistan' },
  { code: 'PW', name: 'Palau' }, { code: 'PS', name: 'Palestine' },
  { code: 'PA', name: 'Panama' }, { code: 'PG', name: 'Papua New Guinea' },
  { code: 'PY', name: 'Paraguay' }, { code: 'PE', name: 'Peru' },
  { code: 'PH', name: 'Philippines' }, { code: 'PL', name: 'Poland' },
  { code: 'PT', name: 'Portugal' }, { code: 'QA', name: 'Qatar' },
  { code: 'RO', name: 'Romania' }, { code: 'RU', name: 'Russia' },
  { code: 'RW', name: 'Rwanda' }, { code: 'KN', name: 'Saint Kitts and Nevis' },
  { code: 'LC', name: 'Saint Lucia' }, { code: 'VC', name: 'Saint Vincent and the Grenadines' },
  { code: 'WS', name: 'Samoa' }, { code: 'SM', name: 'San Marino' },
  { code: 'ST', name: 'São Tomé and Príncipe' }, { code: 'SA', name: 'Saudi Arabia' },
  { code: 'SN', name: 'Senegal' }, { code: 'RS', name: 'Serbia' },
  { code: 'SC', name: 'Seychelles' }, { code: 'SL', name: 'Sierra Leone' },
  { code: 'SG', name: 'Singapore' }, { code: 'SK', name: 'Slovakia' },
  { code: 'SI', name: 'Slovenia' }, { code: 'SB', name: 'Solomon Islands' },
  { code: 'SO', name: 'Somalia' }, { code: 'ZA', name: 'South Africa' },
  { code: 'SS', name: 'South Sudan' }, { code: 'ES', name: 'Spain' },
  { code: 'LK', name: 'Sri Lanka' }, { code: 'SD', name: 'Sudan' },
  { code: 'SR', name: 'Suriname' }, { code: 'SE', name: 'Sweden' },
  { code: 'CH', name: 'Switzerland' }, { code: 'SY', name: 'Syria' },
  { code: 'TW', name: 'Taiwan' }, { code: 'TJ', name: 'Tajikistan' },
  { code: 'TZ', name: 'Tanzania' }, { code: 'TH', name: 'Thailand' },
  { code: 'TL', name: 'Timor-Leste' }, { code: 'TG', name: 'Togo' },
  { code: 'TO', name: 'Tonga' }, { code: 'TT', name: 'Trinidad and Tobago' },
  { code: 'TN', name: 'Tunisia' }, { code: 'TR', name: 'Turkey' },
  { code: 'TM', name: 'Turkmenistan' }, { code: 'TV', name: 'Tuvalu' },
  { code: 'UG', name: 'Uganda' }, { code: 'UA', name: 'Ukraine' },
  { code: 'AE', name: 'United Arab Emirates' }, { code: 'GB', name: 'United Kingdom' },
  { code: 'US', name: 'United States' }, { code: 'UY', name: 'Uruguay' },
  { code: 'UZ', name: 'Uzbekistan' }, { code: 'VU', name: 'Vanuatu' },
  { code: 'VE', name: 'Venezuela' }, { code: 'VN', name: 'Vietnam' },
  { code: 'YE', name: 'Yemen' }, { code: 'ZM', name: 'Zambia' },
  { code: 'ZW', name: 'Zimbabwe' },
];

const DEFAULT_SECURITY = {
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

function isSecurityModified(security) {
  return Object.keys(DEFAULT_SECURITY).some(k => security[k] !== DEFAULT_SECURITY[k]);
}

// ─── Primitives ───────────────────────────────────────────────────────

function Toggle({ checked, onChange }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      onClick={onChange}
      className={`relative inline-flex h-5 w-9 shrink-0 items-center rounded-full transition-colors ${checked ? 'bg-primary' : 'bg-muted'}`}
    >
      <span className={`inline-block h-3 w-3 transform rounded-full bg-white transition-transform ${checked ? 'translate-x-5' : 'translate-x-1'}`} />
    </button>
  );
}

function Field({ label, required, hint, children }) {
  return (
    <div>
      <label className="block text-sm font-medium text-foreground mb-1">
        {label}{required && <span className="text-destructive ml-0.5">*</span>}
      </label>
      {children}
      {hint && <p className="mt-1 text-xs text-muted-foreground">{hint}</p>}
    </div>
  );
}

function TextInput({ name, value, onChange, placeholder, type = 'text' }) {
  return (
    <input
      name={name}
      type={type}
      value={value}
      onChange={onChange}
      placeholder={placeholder}
      className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-1 focus:ring-ring"
    />
  );
}

// ─── Country multi-select ─────────────────────────────────────────────

function CountryMultiSelect({ value, onChange, placeholder }) {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState('');
  const ref = useRef(null);

  const selected = value ? value.split(' ').filter(Boolean) : [];

  function toggle(code) {
    const next = selected.includes(code)
      ? selected.filter(c => c !== code)
      : [...selected, code];
    onChange(next.join(' '));
  }

  function remove(code, e) {
    e.stopPropagation();
    onChange(selected.filter(c => c !== code).join(' '));
  }

  useEffect(() => {
    function onMouseDown(e) {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false);
    }
    document.addEventListener('mousedown', onMouseDown);
    return () => document.removeEventListener('mousedown', onMouseDown);
  }, []);

  const filtered = COUNTRIES.filter(c =>
    c.name.toLowerCase().includes(search.toLowerCase()) ||
    c.code.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div ref={ref} className="relative">
      <div
        onClick={() => setOpen(o => !o)}
        className="min-h-[38px] w-full cursor-pointer rounded-md border border-input bg-background px-3 py-1.5 text-sm flex flex-wrap gap-1 items-center"
      >
        {selected.length === 0 && (
          <span className="text-muted-foreground">{placeholder}</span>
        )}
        {selected.map(code => (
          <span key={code} className="inline-flex items-center gap-1 rounded bg-muted px-1.5 py-0.5 text-xs font-mono font-medium">
            {code}
            <button type="button" onClick={e => remove(code, e)} className="hover:text-destructive leading-none">×</button>
          </span>
        ))}
      </div>

      {open && (
        <div className="absolute z-20 mt-1 w-full rounded-md border border-border bg-card shadow-lg overflow-hidden">
          <div className="p-2 border-b border-border">
            <input
              autoFocus
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder="Search countries…"
              className="w-full rounded border border-input bg-background px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
            />
          </div>
          <div className="max-h-48 overflow-y-auto thin-scrollbar">
            {filtered.length === 0 && (
              <p className="px-3 py-2 text-sm text-muted-foreground">No countries found.</p>
            )}
            {filtered.map(c => (
              <label key={c.code} className="flex items-center gap-2.5 px-3 py-2 text-sm cursor-pointer hover:bg-muted/50">
                <input
                  type="checkbox"
                  checked={selected.includes(c.code)}
                  onChange={() => toggle(c.code)}
                  className="h-4 w-4 rounded border-border"
                />
                <span className="font-mono text-xs text-muted-foreground w-7 shrink-0">{c.code}</span>
                <span className="text-foreground">{c.name}</span>
              </label>
            ))}
          </div>
          {selected.length > 0 && (
            <div className="border-t border-border px-3 py-2">
              <button type="button" onClick={() => onChange('')}
                className="text-xs text-muted-foreground hover:text-destructive transition-colors">
                Clear all ({selected.length})
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ─── Accordion section ────────────────────────────────────────────────

function AccordionSection({ label, required, done, open, onToggle, children }) {
  return (
    <div className="border-b border-border">
      <button
        type="button"
        onClick={onToggle}
        className="flex w-full items-center justify-between px-6 py-4 text-left hover:bg-muted/30 transition-colors"
      >
        <div className="flex items-center gap-3">
          <span className={`h-2 w-2 rounded-full shrink-0 ${
            done === true ? 'bg-green-500' : done === false ? 'bg-amber-400' : 'bg-border'
          }`} />
          <span className="text-sm font-medium text-foreground">{label}</span>
          {!required && <span className="text-xs text-muted-foreground">(optional)</span>}
          {done === false && <span className="text-xs text-amber-600 dark:text-amber-400">required</span>}
        </div>
        <span className="text-xs text-muted-foreground">{open ? '▲' : '▼'}</span>
      </button>
      {open && <div className="px-6 pb-6 space-y-4">{children}</div>}
    </div>
  );
}

// ─── RouteNewDrawer ───────────────────────────────────────────────────

export default function RouteNewDrawer({ onClose, onCreated, orgSlug }) {
  const [openSection, setOpenSection] = useState({ basics: true, backend: false, security: false });
  const [bwIp, setBwIp] = useState('');

  const [basics, setBasics] = useState({ name: '', fqdn: '' });
  const [backend, setBackend] = useState({
    backend_host: '', backend_port: '', backend_protocol: 'http', backend_type: 'direct',
  });
  const [security, setSecurity] = useState({ ...DEFAULT_SECURITY });

  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    api.get('/api/ingress/settings/')
      .then(r => setBwIp(r.data.bunkerweb_public_ip || ''))
      .catch(() => {});
  }, []);

  const chBasics = e => setBasics(f => ({ ...f, [e.target.name]: e.target.value }));
  const chBackend = e => setBackend(f => ({ ...f, [e.target.name]: e.target.value }));
  const chSecurity = e => setSecurity(f => ({ ...f, [e.target.name]: e.target.value }));
  const togSecurity = k => setSecurity(f => ({ ...f, [k]: f[k] === 'yes' ? 'no' : 'yes' }));
  const valSecurity = (k, v) => setSecurity(f => ({ ...f, [k]: v }));
  const togSection = k => setOpenSection(o => ({ ...o, [k]: !o[k] }));

  const basicsDone = basics.fqdn.trim().length > 0;
  const backendDone = backend.backend_host.trim().length > 0 && !!backend.backend_port;
  const canCreate = basicsDone && backendDone;

  async function handleCreate() {
    setError(null);
    setSubmitting(true);
    try {
      await api.post(`/api/ingress/routes/?org=${orgSlug}`, {
        ...basics,
        ...backend,
        backend_port: Number(backend.backend_port),
      });
      if (isSecurityModified(security)) {
        await api.patch(`/api/ingress/routes/${basics.fqdn}/settings/`, security);
      }
      onCreated();
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to create route.');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div className="absolute inset-0 bg-black/40" onClick={onClose} />
      <div className="relative flex h-full w-full max-w-md flex-col border-l border-border bg-card shadow-2xl">

        {/* Header */}
        <div className="flex shrink-0 items-center justify-between border-b border-border px-6 py-4">
          <div>
            <h2 className="text-lg font-semibold text-foreground">New Route</h2>
            <p className="mt-0.5 text-xs text-muted-foreground">Configure and create a new ingress route</p>
          </div>
          <button onClick={onClose} className="text-lg text-muted-foreground hover:text-foreground transition-colors">✕</button>
        </div>

        {/* Accordion body */}
        <div className="flex-1 overflow-y-auto thin-scrollbar divide-y divide-border">

          <AccordionSection label="Basics" required done={basicsDone ? true : false} open={openSection.basics} onToggle={() => togSection('basics')}>
            {bwIp && (
              <div className="rounded-md border border-blue-200 bg-blue-50 px-4 py-3 text-sm dark:border-blue-800 dark:bg-blue-950/30">
                <p className="font-medium text-blue-800 dark:text-blue-300">
                  BunkerWeb IP: <span className="font-mono">{bwIp}</span>
                </p>
                <p className="mt-1 text-xs text-blue-600 dark:text-blue-400">
                  Point your DNS A record to this IP before traffic will be served.
                </p>
              </div>
            )}
            <Field label="Name" hint="Optional label for this route.">
              <TextInput name="name" value={basics.name} onChange={chBasics} placeholder="My service" />
            </Field>
            <Field label="Public FQDN" required>
              <TextInput name="fqdn" value={basics.fqdn} onChange={chBasics} placeholder="app.example.com" />
            </Field>
          </AccordionSection>

          <AccordionSection label="Backend" required done={backendDone ? true : false} open={openSection.backend} onToggle={() => togSection('backend')}>
            <Field label="Backend Host" required>
              <TextInput name="backend_host" value={backend.backend_host} onChange={chBackend} placeholder="10.0.0.1" />
            </Field>
            <Field label="Backend Port" required>
              <TextInput name="backend_port" value={backend.backend_port} onChange={chBackend} placeholder="8080" type="number" />
            </Field>
            <Field label="Backend Protocol">
              <select
                name="backend_protocol"
                value={backend.backend_protocol}
                onChange={chBackend}
                className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-1 focus:ring-ring"
              >
                <option value="http">HTTP</option>
                <option value="https">HTTPS</option>
              </select>
            </Field>
            <Field label="Backend Type" hint="Netbird overlay network support coming soon.">
              <div className="flex gap-3">
                {['direct', 'netbird'].map(bt => (
                  <label key={bt}
                    className={`flex items-center gap-2 rounded-md border px-3 py-2 text-sm transition-colors
                      ${backend.backend_type === bt ? 'border-primary bg-primary/5' : 'border-border'}
                      ${bt === 'netbird' ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer hover:bg-muted/30'}`}>
                    <input
                      type="radio"
                      name="backend_type"
                      value={bt}
                      checked={backend.backend_type === bt}
                      onChange={chBackend}
                      disabled={bt === 'netbird'}
                      className="h-4 w-4"
                    />
                    <span className="capitalize">{bt}</span>
                    {bt === 'netbird' && <span className="text-xs text-muted-foreground">(soon)</span>}
                  </label>
                ))}
              </div>
            </Field>
          </AccordionSection>

          <AccordionSection label="Security" open={openSection.security} onToggle={() => togSection('security')}>

            <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Web Application Firewall</p>
            <label className="flex items-center justify-between gap-4">
              <span className="text-sm font-medium text-foreground">Enable ModSecurity WAF</span>
              <Toggle checked={security.USE_MODSECURITY === 'yes'} onChange={() => togSecurity('USE_MODSECURITY')} />
            </label>
            <label className="flex items-center justify-between gap-4">
              <span className="text-sm font-medium text-foreground">Enable OWASP CRS</span>
              <Toggle checked={security.USE_MODSECURITY_CRS === 'yes'} onChange={() => togSecurity('USE_MODSECURITY_CRS')} />
            </label>
            <div className="flex items-center justify-between gap-4">
              <span className="text-sm font-medium text-foreground">CRS Paranoia Level</span>
              <select
                name="MODSECURITY_CRS_PARANOIA_LEVEL"
                value={security.MODSECURITY_CRS_PARANOIA_LEVEL}
                onChange={chSecurity}
                className="rounded-md border border-input bg-background px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
              >
                {[1, 2, 3, 4].map(l => <option key={l} value={String(l)}>{l}</option>)}
              </select>
            </div>

            <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground pt-2">IP Whitelist</p>
            <label className="flex items-center justify-between gap-4">
              <span className="text-sm font-medium text-foreground">Enable IP Whitelist</span>
              <Toggle checked={security.USE_WHITELIST === 'yes'} onChange={() => togSecurity('USE_WHITELIST')} />
            </label>
            <Field label="Allowed IPs / CIDRs" hint="Space-separated IPs or CIDR ranges.">
              <textarea
                name="WHITELIST_IP"
                value={security.WHITELIST_IP}
                onChange={chSecurity}
                rows={2}
                placeholder="192.168.1.0/24 10.0.0.1"
                className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm font-mono shadow-sm placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring"
              />
            </Field>

            <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground pt-2">Rate Limiting</p>
            <label className="flex items-center justify-between gap-4">
              <span className="text-sm font-medium text-foreground">Enable Rate Limiting</span>
              <Toggle checked={security.USE_LIMIT_REQ === 'yes'} onChange={() => togSecurity('USE_LIMIT_REQ')} />
            </label>
            {security.USE_LIMIT_REQ === 'yes' && (
              <div className="grid grid-cols-2 gap-3">
                <Field label="Rate">
                  <TextInput name="LIMIT_REQ_RATE" value={security.LIMIT_REQ_RATE} onChange={chSecurity} placeholder="10r/s" />
                </Field>
                <Field label="Burst">
                  <TextInput name="LIMIT_REQ_BURST" value={security.LIMIT_REQ_BURST} onChange={chSecurity} placeholder="20" />
                </Field>
              </div>
            )}

            <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground pt-2">Country Access</p>
            <Field label="Blocked Countries" hint="Traffic from selected countries will be blocked.">
              <CountryMultiSelect
                value={security.BLACKLIST_COUNTRY}
                onChange={val => valSecurity('BLACKLIST_COUNTRY', val)}
                placeholder="Select countries to block…"
              />
            </Field>
            <Field label="Allowed Countries Only" hint="Leave empty to allow all. Overrides block list.">
              <CountryMultiSelect
                value={security.WHITELIST_COUNTRY}
                onChange={val => valSecurity('WHITELIST_COUNTRY', val)}
                placeholder="Restrict to specific countries…"
              />
            </Field>

          </AccordionSection>
        </div>

        {/* Sticky footer */}
        <div className="shrink-0 border-t border-border bg-card px-6 py-4 space-y-3">
          {!canCreate && (
            <p className="text-xs text-muted-foreground">Complete Basics and Backend sections to create.</p>
          )}
          {error && <p className="text-sm text-destructive">{error}</p>}
          <div className="flex gap-3">
            <button
              type="button"
              onClick={onClose}
              className="flex-1 rounded-md border border-border px-4 py-2 text-sm font-medium text-foreground hover:bg-accent transition-colors"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={handleCreate}
              disabled={!canCreate || submitting}
              className="flex-1 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-colors"
            >
              {submitting ? 'Creating…' : 'Create Route'}
            </button>
          </div>
        </div>

      </div>
    </div>
  );
}
