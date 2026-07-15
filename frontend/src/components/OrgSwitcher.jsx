import { useState } from 'react';
import { useLocation } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { useOrganization } from '../context/OrgContext';

// Sentinel option value for the staff "All organisations" dashboard view.
const ALL_ORGS = '__all__';

function OrgSwitcher() {
  const { user } = useAuth();
  const orgContext = useOrganization();
  const location = useLocation();
  const [saving, setSaving] = useState(false);

  if (!orgContext) return null;

  const { orgs, selectedOrg, setSelectedOrg, setDefaultOrg, viewAllOrgs, setViewAllOrgs } = orgContext;
  const isAdmin = user?.is_staff;

  if (orgs.length === 0 || !selectedOrg) return null;
  if (!isAdmin && orgs.length <= 1) return null;

  // "All organisations" aggregates the dashboard's DB-backed panels across every
  // tenant; it's only meaningful there, so offer it on the dashboard only.
  const showAllOrgs = isAdmin && location.pathname === '/dashboard';
  const inAllOrgs = showAllOrgs && viewAllOrgs;
  const isDefault = !inAllOrgs && selectedOrg?.slug === user?.default_org_slug;

  function handleChange(e) {
    const value = e.target.value;
    if (value === ALL_ORGS) {
      setViewAllOrgs?.(true);
      return;
    }
    setViewAllOrgs?.(false);
    const org = orgs.find((o) => o.slug === value);
    if (org) setSelectedOrg(org);
  }

  async function handleSetDefault() {
    if (saving || !selectedOrg) return;
    setSaving(true);
    try {
      await setDefaultOrg(selectedOrg);
      // Reflect the new default without a full page reload by mutating the
      // user object in place — AuthContext doesn't expose a setter, so we
      // patch the cached reference directly as a lightweight workaround.
      if (user) user.default_org_slug = selectedOrg.slug;
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="flex items-center gap-1">
      <select
        value={inAllOrgs ? ALL_ORGS : selectedOrg.slug}
        onChange={handleChange}
        className="rounded-md border border-input bg-background px-3 py-1.5 text-sm text-foreground shadow-sm focus:outline-none focus:ring-1 focus:ring-ring"
        aria-label="Select organisation"
      >
        {showAllOrgs && <option value={ALL_ORGS}>All organisations</option>}
        {orgs.map((org) => (
          <option key={org.id} value={org.slug}>
            {org.name}
          </option>
        ))}
      </select>
      <button
        onClick={handleSetDefault}
        disabled={saving || isDefault || inAllOrgs}
        title={isDefault ? 'This is your default organisation' : 'Set as default organisation'}
        className={`rounded p-1.5 text-sm transition-colors disabled:cursor-default ${
          isDefault
            ? 'text-amber-500'
            : 'text-muted-foreground hover:text-foreground'
        }`}
        aria-label={isDefault ? 'Default organisation' : 'Set as default'}
      >
        {isDefault ? '★' : '☆'}
      </button>
    </div>
  );
}

export default OrgSwitcher;
