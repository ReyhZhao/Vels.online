import { useState } from 'react';
import { useAuth } from '../context/AuthContext';
import { useOrganization } from '../context/OrgContext';

function OrgSwitcher() {
  const { user } = useAuth();
  const orgContext = useOrganization();
  const [saving, setSaving] = useState(false);

  if (!orgContext) return null;

  const { orgs, selectedOrg, setSelectedOrg, setDefaultOrg } = orgContext;
  const isAdmin = user?.is_staff;

  if (orgs.length === 0 || !selectedOrg) return null;
  if (!isAdmin && orgs.length <= 1) return null;

  const isDefault = selectedOrg?.slug === user?.default_org_slug;

  function handleChange(e) {
    const org = orgs.find((o) => o.slug === e.target.value);
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
        value={selectedOrg.slug}
        onChange={handleChange}
        className="rounded-md border border-input bg-background px-3 py-1.5 text-sm text-foreground shadow-sm focus:outline-none focus:ring-1 focus:ring-ring"
        aria-label="Select organisation"
      >
        {orgs.map((org) => (
          <option key={org.id} value={org.slug}>
            {org.name}
          </option>
        ))}
      </select>
      <button
        onClick={handleSetDefault}
        disabled={saving || isDefault}
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
