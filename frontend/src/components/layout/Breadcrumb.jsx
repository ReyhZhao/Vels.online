import { Link, useLocation, useParams } from 'react-router-dom';

function buildCrumbs(pathname, params) {
  if (pathname.startsWith('/admin')) {
    if (pathname === '/admin/status-settings') return [{ label: 'Admin', to: null }, { label: 'Service Monitor', to: null }];
    if (pathname === '/admin/security/organizations') return [{ label: 'Admin', to: null }, { label: 'Organisations', to: null }];
    if (pathname === '/admin/security/service-accounts') return [{ label: 'Admin', to: null }, { label: 'Service Accounts', to: null }];
    if (pathname === '/admin/security/downloads') return [{ label: 'Admin', to: null }, { label: 'Downloads', to: null }];
  }

  if (pathname.startsWith('/security')) {
    if (pathname === '/security') return [{ label: 'Security', to: null }];
    if (pathname === '/security/enroll') return [{ label: 'Security', to: '/security' }, { label: 'Enroll', to: null }];
    if (params.agentId) return [{ label: 'Security', to: '/security' }, { label: 'Dashboard', to: '/security' }, { label: `Agent ${params.agentId}`, to: null }];
  }

  return [];
}

export default function Breadcrumb() {
  const { pathname } = useLocation();
  const params = useParams();
  const crumbs = buildCrumbs(pathname, params);

  if (crumbs.length <= 1) return null;

  return (
    <nav aria-label="breadcrumb" className="flex items-center gap-1.5 border-b border-border px-6 py-2 text-sm text-muted-foreground">
      {crumbs.map((crumb, i) => (
        <span key={i} className="flex items-center gap-1.5">
          {i > 0 && <span aria-hidden="true">/</span>}
          {crumb.to ? (
            <Link to={crumb.to} className="hover:text-foreground transition-colors">
              {crumb.label}
            </Link>
          ) : (
            <span className="text-foreground font-medium">{crumb.label}</span>
          )}
        </span>
      ))}
    </nav>
  );
}
