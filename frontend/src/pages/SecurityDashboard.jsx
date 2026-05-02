import { useOrganization } from '../context/OrgContext';

function SecurityDashboard() {
  const { selectedOrg, isLoading } = useOrganization();

  if (isLoading) {
    return <p className="text-sm text-muted-foreground">Loading…</p>;
  }

  if (!selectedOrg) {
    return <p className="text-sm text-muted-foreground">No organisation assigned.</p>;
  }

  return (
    <div>
      <h1 className="text-2xl font-semibold text-foreground">{selectedOrg.name}</h1>
      <p className="mt-1 text-sm text-muted-foreground">
        Select a section from the navigation to view agents, events, or vulnerabilities.
      </p>
    </div>
  );
}

export default SecurityDashboard;
