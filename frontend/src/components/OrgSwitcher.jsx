import { useAuth } from '../context/AuthContext';
import { useOrganization } from '../context/OrgContext';

function OrgSwitcher() {
  const { user } = useAuth();
  const { orgs, selectedOrg, setSelectedOrg } = useOrganization();

  const isAdmin = user?.is_staff;

  if (orgs.length === 0 || !selectedOrg) return null;
  if (!isAdmin && orgs.length <= 1) return null;

  function handleChange(e) {
    const org = orgs.find((o) => o.slug === e.target.value);
    if (org) setSelectedOrg(org);
  }

  return (
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
  );
}

export default OrgSwitcher;
