import { Link, Outlet, useLocation } from 'react-router-dom';
import {
  Shield, ArrowRight, Radar, Sparkles, Boxes, Bug, Globe, ScrollText,
  CirclePlay, Siren, ShieldCheck, CircleAlert,
} from 'lucide-react';

export const LOGIN_URL = import.meta.env.VITE_LOGIN_URL ?? '/auth/oidc/authentik/login/';

/** Icon names referenced by src/content/siteContent.js. */
export const CONTENT_ICONS = {
  Radar, Sparkles, Boxes, Bug, Globe, ScrollText, CirclePlay, Siren, ShieldCheck, CircleAlert,
};

const NAV = [
  { label: 'Platform', to: '/#platform' },
  { label: 'Documentation', to: '/docs' },
  { label: 'Status', to: '/status' },
];

function TopBar() {
  const { pathname } = useLocation();

  return (
    <header className="fixed inset-x-0 top-0 z-50 border-b border-white/5 bg-[#070d1a]/70 backdrop-blur-xl">
      <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-6">
        <Link to="/" className="flex items-center gap-2.5">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-sky-400 to-blue-600 shadow-lg shadow-blue-500/30">
            <Shield className="h-4 w-4 text-[#070d1a]" strokeWidth={2.5} aria-hidden="true" />
          </div>
          <span className="text-[15px] font-semibold tracking-tight">Polaris Security</span>
        </Link>

        <nav className="hidden items-center gap-8 md:flex" aria-label="Main">
          {NAV.map((item) => {
            const isCurrent = item.to === '/docs' && pathname.startsWith('/docs');
            return (
              <Link
                key={item.label}
                to={item.to}
                aria-current={isCurrent ? 'page' : undefined}
                className={`text-sm transition-colors hover:text-white ${
                  isCurrent ? 'font-medium text-white' : 'text-slate-400'
                }`}
              >
                {item.label}
              </Link>
            );
          })}
        </nav>

        <a
          href={LOGIN_URL}
          className="group inline-flex items-center gap-2 rounded-full bg-white px-4 py-2 text-sm font-semibold text-[#070d1a] transition-all hover:bg-sky-200 hover:shadow-lg hover:shadow-sky-400/25"
        >
          Sign in
          <ArrowRight className="h-3.5 w-3.5 transition-transform group-hover:translate-x-0.5" aria-hidden="true" />
        </a>
      </div>
    </header>
  );
}

function SiteFooter() {
  return (
    <footer className="border-t border-white/10 py-10">
      <div className="mx-auto flex max-w-7xl flex-col items-center justify-between gap-4 px-6 text-sm text-slate-500 sm:flex-row">
        <span>© {new Date().getFullYear()} Polaris Security</span>
        <div className="flex gap-6">
          <Link to="/status" className="hover:text-slate-300">Status</Link>
          <Link to="/docs" className="hover:text-slate-300">Docs</Link>
          <Link to="/signup" className="hover:text-slate-300">Request access</Link>
          <a href={LOGIN_URL} className="hover:text-slate-300">Sign in</a>
        </div>
      </div>
    </footer>
  );
}

/**
 * Chrome for the public front door (landing page + user handbook). Deliberately
 * separate from PublicLayout: these pages own a dark full-bleed treatment rather
 * than the app's container-width shell.
 */
function LandingLayout() {
  return (
    <div className="min-h-screen bg-[#070d1a] text-white antialiased">
      <TopBar />
      <main>
        <Outlet />
      </main>
      <SiteFooter />
    </div>
  );
}

export default LandingLayout;
