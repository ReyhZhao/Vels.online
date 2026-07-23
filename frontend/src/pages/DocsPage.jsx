import { Fragment, useEffect, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Search, ChevronDown, ArrowRight, ArrowLeft } from 'lucide-react';
import { CONTENT_ICONS, LOGIN_URL } from '../components/layout/LandingLayout';
import { DOC_SECTIONS } from '../content/siteContent';
import { useAuth } from '../context/AuthContext';
import api from '../lib/axios';

// Article headings sit below the fixed top bar; the observer's top margin has to
// clear it too or the article behind the bar wins the "nearest the top" race.
const HEADER_OFFSET_PX = 88;
const SCROLL_SETTLE_MS = 800;

function matches(section, article, needle) {
  return (
    article.title.toLowerCase().includes(needle) ||
    article.body.join(' ').toLowerCase().includes(needle) ||
    section.title.toLowerCase().includes(needle)
  );
}

function DocsPage() {
  const [query, setQuery] = useState('');
  const [activeArticle, setActiveArticle] = useState(DOC_SECTIONS[0].articles[0].id);
  const [navOpen, setNavOpen] = useState(false); // mobile only — always open from lg up
  const spySuppressedUntil = useRef(0);

  // The in-depth sections are not bundled — they come from an authenticated API,
  // so a logged-out visitor never receives them at all.
  const { isAuthenticated } = useAuth();
  const [extendedSections, setExtendedSections] = useState([]);

  useEffect(() => {
    if (!isAuthenticated) {
      setExtendedSections([]);
      return undefined;
    }
    let cancelled = false;
    api
      .get('/api/docs/extended/')
      .then((res) => {
        if (!cancelled) {
          setExtendedSections(
            (res.data?.sections ?? []).map((section) => ({ ...section, access: 'authenticated' })),
          );
        }
      })
      .catch(() => {}); // docs are non-critical — a failed fetch just hides the extra sections
    return () => {
      cancelled = true;
    };
  }, [isAuthenticated]);

  const sections = useMemo(() => {
    const allSections = [...DOC_SECTIONS, ...extendedSections];
    const needle = query.trim().toLowerCase();
    if (!needle) return allSections;
    return allSections
      .map((section) => ({
        ...section,
        articles: section.articles.filter((article) => matches(section, article, needle)),
      }))
      .filter((section) => section.articles.length > 0);
  }, [query, extendedSections]);

  const articleCount = sections.reduce((total, section) => total + section.articles.length, 0);
  const firstExtendedId = sections.find((section) => section.access === 'authenticated')?.id;

  // Deep links: #incidents lands on a section, #doc-agentic-triage on an article.
  // Re-runs once the extended sections arrive, so a link to an in-depth article scrolls too.
  useEffect(() => {
    const hash = window.location.hash.replace('#', '');
    if (!hash) return;
    const target = document.getElementById(hash);
    if (!target) return;

    const section = [...DOC_SECTIONS, ...extendedSections].find(
      (candidate) => candidate.id === hash,
    );
    setActiveArticle(section ? section.articles[0].id : hash.replace('doc-', ''));
    spySuppressedUntil.current = Date.now() + SCROLL_SETTLE_MS;
    target.scrollIntoView();
  }, [extendedSections]);

  // Highlight whichever article is nearest the top of the reading column.
  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        if (Date.now() < spySuppressedUntil.current) return;
        const nearest = entries
          .filter((entry) => entry.isIntersecting)
          .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top)[0];
        if (nearest) setActiveArticle(nearest.target.id.replace('doc-', ''));
      },
      { rootMargin: `-${HEADER_OFFSET_PX}px 0px -70% 0px` },
    );

    sections.forEach((section) =>
      section.articles.forEach((article) => {
        const element = document.getElementById(`doc-${article.id}`);
        if (element) observer.observe(element);
      }),
    );

    return () => observer.disconnect();
  }, [sections]);

  function goToArticle(id) {
    setActiveArticle(id);
    setNavOpen(false);
    spySuppressedUntil.current = Date.now() + SCROLL_SETTLE_MS;
    document.getElementById(`doc-${id}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  return (
    <>
      <div className="relative overflow-hidden border-b border-white/10 pt-16">
        <div
          className="pointer-events-none absolute left-1/2 top-[-24rem] h-[40rem] w-[40rem] -translate-x-1/2 rounded-full bg-[radial-gradient(circle,rgba(56,132,255,0.20),transparent_62%)] blur-2xl"
          aria-hidden="true"
        />
        <div className="relative mx-auto max-w-7xl px-6 py-14">
          <Link
            to="/"
            className="mb-6 inline-flex items-center gap-1.5 text-sm text-slate-500 transition-colors hover:text-slate-300"
          >
            <ArrowLeft className="h-3.5 w-3.5" aria-hidden="true" />
            Back to Polaris Security
          </Link>
          <div className="mb-3 text-sm font-semibold uppercase tracking-[0.2em] text-sky-400">
            Documentation
          </div>
          <h1 className="max-w-2xl text-4xl font-semibold tracking-tight lg:text-5xl">
            Everything you need to work in Polaris
          </h1>
          <p className="mt-4 max-w-xl text-[15px] leading-relaxed text-slate-400">
            The full user handbook, written for the people who use it daily. No login
            required — link a colleague straight to a section.
          </p>
        </div>
      </div>

      <div className="mx-auto max-w-7xl px-6 py-14">
        <div className="lg:grid lg:grid-cols-[17rem_minmax(0,1fr)] lg:gap-14">
          <div className="lg:sticky lg:top-[4.5rem] lg:h-[calc(100vh-6rem)] lg:self-start">
            <div className="relative mb-5">
              <Search
                className="pointer-events-none absolute left-3.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-slate-500"
                aria-hidden="true"
              />
              <input
                type="search"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Search the documentation…"
                aria-label="Search the documentation"
                className="w-full rounded-lg border border-white/15 bg-white/[0.04] py-2.5 pl-10 pr-3 text-[14px] text-white placeholder:text-slate-500 focus:border-sky-400/50 focus:outline-none focus:ring-4 focus:ring-sky-400/10"
              />
            </div>

            {/* The full tree would bury the prose on a phone. */}
            <button
              type="button"
              onClick={() => setNavOpen((open) => !open)}
              aria-expanded={navOpen}
              className="mb-5 flex w-full items-center justify-between rounded-lg border border-white/15 bg-white/[0.04] px-4 py-2.5 text-[14px] text-slate-300 lg:hidden"
            >
              Browse all {articleCount} articles
              <ChevronDown
                className={`h-4 w-4 text-slate-500 transition-transform ${navOpen ? 'rotate-180' : ''}`}
                aria-hidden="true"
              />
            </button>

            <nav
              aria-label="Documentation"
              className={`thin-scrollbar -mr-2 max-h-full overflow-y-auto pb-10 pr-2 lg:block ${
                navOpen ? 'block' : 'hidden'
              }`}
            >
              {sections.map((section) => {
                const Icon = CONTENT_ICONS[section.icon];
                return (
                  <Fragment key={section.id}>
                    {section.id === firstExtendedId && (
                      <div className="mb-4 mt-1 border-t border-white/10 px-2 pt-4 text-[10.5px] font-semibold uppercase tracking-[0.14em] text-sky-400/80">
                        In-depth reference
                      </div>
                    )}
                    <div className="mb-6">
                    <div className="mb-2 flex items-center gap-2 px-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-500">
                      <Icon className="h-3 w-3" aria-hidden="true" />
                      {section.title}
                    </div>
                    <ul className="border-l border-white/10">
                      {section.articles.map((article) => (
                        <li key={article.id}>
                          <button
                            type="button"
                            onClick={() => goToArticle(article.id)}
                            aria-current={activeArticle === article.id ? 'true' : undefined}
                            className={`-ml-px block w-full border-l py-1.5 pl-4 pr-2 text-left text-[13.5px] transition-colors ${
                              activeArticle === article.id
                                ? 'border-sky-400 font-medium text-sky-300'
                                : 'border-transparent text-slate-400 hover:border-white/25 hover:text-slate-100'
                            }`}
                          >
                            {article.title}
                          </button>
                        </li>
                      ))}
                    </ul>
                    </div>
                  </Fragment>
                );
              })}
              {sections.length === 0 && (
                <p className="px-2 text-[13.5px] text-slate-600">Nothing matches “{query}”.</p>
              )}
            </nav>
          </div>

          <div className="mt-10 min-w-0 lg:mt-0">
            {sections.map((section) => {
              const Icon = CONTENT_ICONS[section.icon];
              return (
                <Fragment key={section.id}>
                {section.id === firstExtendedId && (
                  <div className="mb-12 rounded-xl border border-sky-400/20 bg-sky-400/[0.05] px-6 py-5">
                    <p className="text-[13px] font-semibold uppercase tracking-[0.14em] text-sky-300">
                      In-depth reference
                    </p>
                    <p className="mt-2 max-w-xl text-[14.5px] leading-relaxed text-slate-400">
                      The sections below go under the hood of the detection engine. They are here
                      because you are signed in — logged-out visitors never load them.
                    </p>
                  </div>
                )}
                <section id={section.id} className="mb-16 scroll-mt-24 last:mb-0">
                  <div className="mb-8 flex items-center gap-2.5 border-b border-white/10 pb-3">
                    <Icon className="h-4 w-4 text-sky-400" aria-hidden="true" />
                    <h2 className="text-[13px] font-semibold uppercase tracking-[0.14em] text-slate-300">
                      {section.title}
                    </h2>
                    <span className="ml-auto hidden text-[12.5px] text-slate-600 sm:inline">
                      {section.summary}
                    </span>
                  </div>

                  {section.articles.map((article) => (
                    <article
                      key={article.id}
                      id={`doc-${article.id}`}
                      className="mb-11 scroll-mt-24 last:mb-0"
                    >
                      <h3 className="mb-3.5 text-[22px] font-semibold tracking-tight text-slate-100">
                        {article.title}
                      </h3>
                      <div className="prose prose-invert max-w-2xl prose-p:text-[15.5px] prose-p:leading-[1.75] prose-p:text-slate-400 prose-strong:text-slate-200 prose-code:rounded prose-code:bg-white/10 prose-code:px-1.5 prose-code:py-0.5 prose-code:text-[13px] prose-code:text-sky-200 prose-code:before:content-none prose-code:after:content-none">
                        <ReactMarkdown remarkPlugins={[remarkGfm]}>
                          {article.body.join('\n\n')}
                        </ReactMarkdown>
                      </div>
                    </article>
                  ))}
                </section>
                </Fragment>
              );
            })}

            {sections.length === 0 && (
              <p className="py-16 text-slate-500">Nothing matches “{query}”.</p>
            )}

            <div className="mt-16 rounded-xl border border-sky-400/20 bg-sky-400/[0.06] p-7">
              <h2 className="text-[17px] font-semibold text-slate-100">Ready to sign in?</h2>
              <p className="mt-2 max-w-md text-[15px] leading-relaxed text-slate-400">
                Polaris uses your organisation&apos;s identity provider — no separate password
                to remember.
              </p>
              <a
                href={LOGIN_URL}
                className="group mt-5 inline-flex items-center gap-2 rounded-full bg-gradient-to-r from-sky-400 to-blue-500 px-6 py-3 text-[14.5px] font-semibold text-[#070d1a] shadow-lg shadow-blue-500/25"
              >
                Sign in to Polaris
                <ArrowRight
                  className="h-4 w-4 transition-transform group-hover:translate-x-1"
                  aria-hidden="true"
                />
              </a>
            </div>
          </div>
        </div>
      </div>
    </>
  );
}

export default DocsPage;
