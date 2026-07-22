import { Link, Navigate } from 'react-router-dom';
import { ArrowRight, LogIn, BookOpen } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { usePublicStats, formatCount } from '../hooks/usePublicStats';
import { CONTENT_ICONS, LOGIN_URL } from '../components/layout/LandingLayout';
import { FEATURES, DOC_SECTIONS } from '../content/siteContent';

function StatBand() {
  const { stats, isLoading } = usePublicStats();

  const orgs = formatCount(stats?.organizations_protected);
  const window = stats?.window_days ?? 30;

  const tiles = [
    {
      key: 'alerts',
      label: 'Alerts ingested',
      value: formatCount(stats?.alerts_ingested),
      sub: `last ${window} days`,
    },
    {
      key: 'incidents',
      label: 'Incidents resolved',
      value: formatCount(stats?.incidents_resolved),
      sub: `last ${window} days`,
    },
    {
      key: 'endpoints',
      label: 'Endpoints monitored',
      value: formatCount(stats?.endpoints_monitored),
      sub: orgs ? `across ${orgs} organisations` : 'across our customer base',
    },
    {
      key: 'rules',
      label: 'Detection rules live',
      value: formatCount(stats?.detection_rules_live),
      sub: 'baseline + per-org overlay',
    },
  ];

  return (
    <div className="relative border-y border-white/10 bg-white/[0.02] backdrop-blur">
      <div className="mx-auto grid max-w-7xl grid-cols-2 divide-x divide-white/10 px-6 lg:grid-cols-4">
        {tiles.map((tile) => (
          <div key={tile.key} className="px-4 py-8 text-center lg:py-10">
            <div
              className="font-mono text-3xl font-semibold tracking-tight text-white lg:text-4xl"
              data-testid={`stat-${tile.key}`}
            >
              {/* Never invent a figure: unknown renders as an em dash. */}
              {tile.value ?? (isLoading ? '·' : '—')}
            </div>
            <div className="mt-2 text-sm font-medium text-slate-300">{tile.label}</div>
            <div className="mt-0.5 text-xs text-slate-500">{tile.sub}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

function Hero() {
  return (
    <section className="relative overflow-hidden pt-16">
      <div className="pointer-events-none absolute inset-0" aria-hidden="true">
        <div className="absolute left-1/2 top-[-28rem] h-[52rem] w-[52rem] -translate-x-1/2 rounded-full bg-[radial-gradient(circle,rgba(56,132,255,0.30),transparent_62%)] blur-2xl" />
        <div className="absolute right-[-12rem] top-24 h-[34rem] w-[34rem] rounded-full bg-[radial-gradient(circle,rgba(139,92,246,0.20),transparent_65%)] blur-2xl" />
        <div
          className="absolute inset-0 opacity-[0.16]"
          style={{
            backgroundImage:
              'linear-gradient(rgba(148,182,255,0.4) 1px, transparent 1px), linear-gradient(90deg, rgba(148,182,255,0.4) 1px, transparent 1px)',
            backgroundSize: '64px 64px',
            maskImage: 'radial-gradient(ellipse 90% 60% at 50% 25%, black, transparent)',
            WebkitMaskImage: 'radial-gradient(ellipse 90% 60% at 50% 25%, black, transparent)',
          }}
        />
      </div>

      <div className="relative mx-auto max-w-7xl px-6 pb-24 pt-24 text-center lg:pt-32">
        <h1 className="mx-auto max-w-4xl text-balance text-5xl font-semibold leading-[1.05] tracking-tight lg:text-7xl">
          Your security signal,
          <br />
          <span className="bg-gradient-to-r from-sky-300 via-blue-400 to-violet-400 bg-clip-text text-transparent">
            already triaged.
          </span>
        </h1>

        <p className="mx-auto mt-7 max-w-2xl text-pretty text-lg leading-relaxed text-slate-400">
          Polaris correlates alerts across your endpoints, vulnerabilities and public
          ingress into incidents a human can act on — and works the obvious ones for
          you before you get there.
        </p>

        <div className="mt-10 flex flex-wrap items-center justify-center gap-3">
          <a
            href={LOGIN_URL}
            className="group inline-flex items-center gap-2 rounded-full bg-gradient-to-r from-sky-400 to-blue-500 px-7 py-3.5 text-[15px] font-semibold text-[#070d1a] shadow-xl shadow-blue-500/30 transition-all hover:shadow-2xl hover:shadow-blue-400/40"
          >
            <LogIn className="h-4 w-4" aria-hidden="true" />
            Sign in to Polaris
            <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-1" aria-hidden="true" />
          </a>
          <Link
            to="/docs"
            className="inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/5 px-7 py-3.5 text-[15px] font-medium text-slate-200 backdrop-blur transition-colors hover:border-white/30 hover:bg-white/10"
          >
            Read the documentation
          </Link>
        </div>
      </div>

      <StatBand />
    </section>
  );
}

function Features() {
  return (
    <section id="platform" className="mx-auto max-w-7xl scroll-mt-20 px-6 py-28">
      <div className="mb-16 max-w-2xl">
        <div className="mb-3 text-sm font-semibold uppercase tracking-[0.2em] text-sky-400">
          The platform
        </div>
        <h2 className="text-4xl font-semibold tracking-tight lg:text-5xl">
          Six things it does so you don&apos;t have to
        </h2>
      </div>

      <div className="grid gap-px overflow-hidden rounded-2xl border border-white/10 bg-white/10 md:grid-cols-2 lg:grid-cols-3">
        {FEATURES.map((feature) => {
          const Icon = CONTENT_ICONS[feature.icon];
          return (
            <div
              key={feature.key}
              className="group bg-[#0a1120] p-8 transition-colors hover:bg-[#0d1628]"
            >
              <div className="mb-5 inline-flex h-11 w-11 items-center justify-center rounded-xl border border-sky-400/20 bg-sky-400/10 text-sky-300 transition-all group-hover:border-sky-400/40 group-hover:bg-sky-400/15">
                <Icon className="h-5 w-5" aria-hidden="true" />
              </div>
              <h3 className="mb-2.5 text-lg font-semibold tracking-tight">{feature.title}</h3>
              <p className="text-[15px] leading-relaxed text-slate-400">{feature.blurb}</p>
            </div>
          );
        })}
      </div>
    </section>
  );
}

/** A pointer to the handbook, not the handbook itself — that lives at /docs. */
function DocsIndex() {
  return (
    <section id="documentation" className="border-t border-white/10 bg-[#060b16] py-28">
      <div className="mx-auto max-w-7xl px-6">
        <div className="mb-14 flex flex-wrap items-end justify-between gap-6">
          <div className="max-w-2xl">
            <div className="mb-3 text-sm font-semibold uppercase tracking-[0.2em] text-sky-400">
              Documentation
            </div>
            <h2 className="text-4xl font-semibold tracking-tight lg:text-5xl">
              Everything you need to work in Polaris
            </h2>
            <p className="mt-4 max-w-xl text-[15px] leading-relaxed text-slate-400">
              The full user handbook lives on its own page — no login required. Jump
              straight to a section, or read it end to end.
            </p>
          </div>
          <Link
            to="/docs"
            className="group inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/5 px-6 py-3 text-[15px] font-medium text-slate-200 transition-colors hover:border-white/30 hover:bg-white/10"
          >
            <BookOpen className="h-4 w-4" aria-hidden="true" />
            Open the documentation
            <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-1" aria-hidden="true" />
          </Link>
        </div>

        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {DOC_SECTIONS.map((section) => {
            const Icon = CONTENT_ICONS[section.icon];
            return (
              <Link
                key={section.id}
                to={`/docs#${section.id}`}
                className="group flex h-full flex-col rounded-xl border border-white/10 bg-white/[0.02] p-6 transition-all hover:-translate-y-0.5 hover:border-sky-400/40 hover:bg-white/[0.05]"
              >
                <div className="mb-4 inline-flex h-10 w-10 items-center justify-center rounded-lg border border-sky-400/20 bg-sky-400/10 text-sky-300 transition-colors group-hover:border-sky-400/40">
                  <Icon className="h-4 w-4" aria-hidden="true" />
                </div>
                <h3 className="text-[16px] font-semibold tracking-tight text-slate-100">
                  {section.title}
                </h3>
                <p className="mt-1.5 flex-1 text-[14px] leading-relaxed text-slate-400">
                  {section.summary}
                </p>
                <span className="mt-5 flex items-center gap-1.5 text-[13px] font-medium text-slate-500 transition-colors group-hover:text-sky-300">
                  {section.articles.length} articles
                  <ArrowRight className="h-3.5 w-3.5 transition-transform group-hover:translate-x-1" aria-hidden="true" />
                </span>
              </Link>
            );
          })}
        </div>
      </div>
    </section>
  );
}

function Cta() {
  return (
    <section className="relative overflow-hidden border-t border-white/10 py-28">
      <div
        className="pointer-events-none absolute left-1/2 top-1/2 h-[30rem] w-[60rem] -translate-x-1/2 -translate-y-1/2 rounded-full bg-[radial-gradient(ellipse,rgba(56,132,255,0.20),transparent_65%)] blur-2xl"
        aria-hidden="true"
      />
      <div className="relative mx-auto max-w-3xl px-6 text-center">
        <h2 className="text-4xl font-semibold tracking-tight lg:text-5xl">Ready when you are</h2>
        <p className="mx-auto mt-4 max-w-lg text-[15px] leading-relaxed text-slate-400">
          Sign in with your organisation&apos;s identity provider. No separate password to
          remember, no extra account to manage.
        </p>
        <div className="mt-9 flex flex-wrap items-center justify-center gap-3">
          <a
            href={LOGIN_URL}
            className="group inline-flex items-center gap-2 rounded-full bg-white px-7 py-3.5 text-[15px] font-semibold text-[#070d1a] transition-all hover:bg-sky-200"
          >
            Sign in
            <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-1" aria-hidden="true" />
          </a>
          <Link
            to="/signup"
            className="inline-flex items-center gap-2 rounded-full border border-white/15 px-7 py-3.5 text-[15px] font-medium text-slate-200 transition-colors hover:bg-white/5"
          >
            Request access
          </Link>
        </div>
      </div>
    </section>
  );
}

/**
 * The public front door. Signed-in users never see it — they go straight to the
 * dashboard, which is how `/` behaved before this page existed.
 */
function LandingPage() {
  const { isAuthenticated, isLoading } = useAuth();

  if (isLoading) return null;
  if (isAuthenticated) return <Navigate to="/dashboard" replace />;

  return (
    <>
      <Hero />
      <Features />
      <DocsIndex />
      <Cta />
    </>
  );
}

export default LandingPage;
