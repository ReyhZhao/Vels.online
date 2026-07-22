/**
 * Static content for the public landing page and user handbook.
 *
 * Prose, not data — it is versioned with the UI that renders it, so a copy
 * change ships as a normal frontend deploy. Article bodies are markdown.
 */

export const FEATURES = [
  {
    key: 'detect',
    icon: 'Radar',
    title: 'Correlate, don\'t drown',
    blurb:
      'Multi-leg Correlation Rules join alerts across Wazuh, vulnerability scans, ingress and email on a shared entity — so one incident lands on your desk, not forty alerts.',
  },
  {
    key: 'triage',
    icon: 'Sparkles',
    title: 'Agentic triage',
    blurb:
      'Every alert gets a cheap classification pass. High-confidence cases are worked end-to-end by the Triage Agent against your playbook, and it learns from the corrections you make.',
  },
  {
    key: 'assets',
    icon: 'Boxes',
    title: 'Assets in context',
    blurb:
      'Hosts and public routes are first-class records. Every incident is linked to what it actually touched, and internet-facing exposure is derived rather than guessed.',
  },
  {
    key: 'vuln',
    icon: 'Bug',
    title: 'Vulnerability to action',
    blurb:
      'CVEs are scored against your real fleet, bundled into work packages your team can actually close, and risk-accepted with an audit trail when they can\'t.',
  },
  {
    key: 'ingress',
    icon: 'Globe',
    title: 'Protected ingress',
    blurb:
      'Self-service reverse proxy and WAF in front of your public FQDNs, with per-route reporting that feeds straight back into detection.',
  },
  {
    key: 'reports',
    icon: 'ScrollText',
    title: 'Reports that hold up',
    blurb:
      'Immutable snapshot reports built from SOC-maintained templates, with an audience visibility floor so a customer-facing report never leaks internal notes.',
  },
];

export const DOC_SECTIONS = [
  {
    id: 'getting-started',
    icon: 'CirclePlay',
    title: 'Getting started',
    summary: 'Sign in, find your way around, and get your first alerts flowing.',
    articles: [
      {
        id: 'first-login',
        title: 'Your first sign-in',
        body: [
          'Polaris uses single sign-on. Select **Sign in** and you will be handed to your identity provider; once it confirms you, you land on the dashboard for the organisation you belong to.',
          'If you belong to more than one organisation, use the organisation switcher in the top bar. Everything you see — alerts, incidents, assets, reports — is scoped to the organisation currently selected.',
          'No account yet? Use **Request access**. A member of the SOC reviews every request before it is approved.',
        ],
      },
      {
        id: 'tour',
        title: 'A tour of the interface',
        body: [
          '**Dashboard** — the daily starting point: open incidents assigned to you, what fired overnight, and the health of your fleet.',
          '**Alerts** — the raw feed of every signal received, before correlation. Useful for hunting and for understanding why an incident exists.',
          '**Incidents** — the work surface. Everything an analyst does happens here: timeline, tasks, comments, linked assets and contacts, reports.',
          '**Security** — fleet posture: agents, events, vulnerabilities, work packages and risk acceptances.',
          '**Assets** — the hosts and public routes your organisation owns.',
        ],
      },
      {
        id: 'notifications',
        title: 'Notifications and on-call',
        body: [
          'Set your preferences under **Account → Notifications**. You can choose which events reach you by email, in-app, or push to the mobile app.',
          'If you carry a pager, the on-call calendar decides who a newly triaged incident is auto-assigned to. Swaps made on the calendar take effect immediately.',
        ],
      },
    ],
  },
  {
    id: 'alerts',
    icon: 'Siren',
    title: 'Alerts & detection',
    summary: 'How signals arrive, get correlated, and become something worth your time.',
    articles: [
      {
        id: 'what-is-an-alert',
        title: 'What an alert is',
        body: [
          'An **alert** is a single security signal from one source — a Wazuh event, a vulnerability finding, an inbound email from a partner, or a direct API push. It carries a severity, a source reference, and an entity envelope.',
          'The **entity envelope** is the normalised set of values on an alert — `host.name`, `source.ip`, `user.name`, `file.hash.sha256`, `process.name`. It is what lets alerts from completely different sources be joined together.',
        ],
      },
      {
        id: 'correlation',
        title: 'Correlation rules',
        body: [
          'A **correlation rule** promotes a combination of alerts to an incident when all of its **legs** are satisfied for the same **correlation key** inside a rolling **window**.',
          'Each leg matches a class of alert by its fields. The correlation key is the entity the legs bind on — an agent, a source IP, a username, or nothing at all for org-wide rules.',
          'While a rule\'s firing is live, further matching alerts join the existing incident instead of spawning a new one. A fresh firing only becomes possible once that incident closes.',
        ],
      },
      {
        id: 'system-vs-org',
        title: 'System rules vs. your own rules',
        body: [
          '**System rules** are authored by the Polaris SOC and apply to every tenant as baseline detection. You cannot edit them, but you can **mute** one for your organisation if it is noisy in your environment.',
          '**Org rules** are yours. You author, test and tune them, and they only ever evaluate against your data.',
          'Before enabling a rule, run a **rule test**: it replays real data through the rule against a scratch index and tells you what it would have fired on.',
        ],
      },
      {
        id: 'exceptions',
        title: 'Exceptions',
        body: [
          'When a detection is legitimately wrong for your environment, raise an **exception** rather than muting the whole rule. Exceptions are reviewed and approved, then pushed into the upstream ruleset with a full audit trail.',
        ],
      },
    ],
  },
  {
    id: 'incidents',
    icon: 'ShieldCheck',
    title: 'Incidents & triage',
    summary: 'The work surface: from first verdict to closure and reporting.',
    articles: [
      {
        id: 'lifecycle',
        title: 'The incident lifecycle',
        body: [
          'Incidents move through triage, investigation, containment and closure. The state is always visible at the top of the incident, and every transition is recorded on the timeline.',
          'Nothing on the timeline can be edited after the fact. That is deliberate — the timeline is the record you will hand to an auditor.',
        ],
      },
      {
        id: 'agentic-triage',
        title: 'Agentic triage',
        body: [
          'Every incoming alert gets a cheap classification pass. When the classifier is confident and your organisation has opted in, the **Triage Agent** works the playbook unattended and leaves its reasoning on the timeline.',
          'The agent never closes an incident silently — it moves it to a pending-closure state that a human confirms.',
          'Correcting a classification is not just a fix for that one incident. Corrections feed **triage lessons**, which inform — but never by themselves fire — future triage.',
        ],
      },
      {
        id: 'collaboration',
        title: 'Working an incident with others',
        body: [
          'You can see who else has the incident open, live. If someone is drafting a comment, you will see a soft lock so two analysts don\'t write the same update twice.',
          '**Tasks** break the work down and can be delegated. **Contacts** record who at the customer was informed and when. **Attachments** hold evidence.',
        ],
      },
      {
        id: 'reports',
        title: 'Reports',
        body: [
          'A **report** is an immutable snapshot of an incident, assembled from SOC-maintained section templates. Once issued, it cannot change — reissue instead.',
          'Every report has an **audience**, and the audience sets a visibility floor: content above that floor is filtered out before the report is assembled, including before the executive summary is written.',
        ],
      },
    ],
  },
  {
    id: 'assets',
    icon: 'Boxes',
    title: 'Assets & exposure',
    summary: 'Hosts, public routes, and what is actually reachable from the internet.',
    articles: [
      {
        id: 'assets',
        title: 'Hosts and routes',
        body: [
          'An **asset** is a thing your organisation owns that the SOC tracks and links to incidents. It is either a **host asset** (an endpoint running an agent) or a **route asset** (a public FQDN proxied through the protected ingress).',
          'A route asset is internet-facing by its nature. It is the front **through** which a host may be exposed — the host behind it is a separate record.',
        ],
      },
      {
        id: 'agents',
        title: 'Enrolling endpoints',
        body: [
          'Use **Security → Enroll** to generate an enrolment command for your platform. Run it on the endpoint; it appears in the fleet within a minute or two.',
          'An agent that stops reporting is flagged automatically — a silent agent is treated as a finding, not as good news.',
        ],
      },
      {
        id: 'routes',
        title: 'Ingress routes',
        body: [
          'Add an FQDN under **Routes**, point it at an upstream, and Polaris provisions the reverse proxy and WAF for you. DNS is checked before the route goes live.',
          'Per-route reports show what the WAF blocked and what reached your upstream.',
        ],
      },
    ],
  },
  {
    id: 'vulnerabilities',
    icon: 'Bug',
    title: 'Vulnerabilities',
    summary: 'From CVE feed to a work package your team can actually close.',
    articles: [
      {
        id: 'triage-cves',
        title: 'Prioritising CVEs',
        body: [
          'The vulnerability dashboard scores CVEs against your real fleet — how many hosts are affected, whether any of them are internet-facing, and whether exploitation is known.',
          'Open a CVE to see the advisory, the affected hosts, and the remediation guidance.',
        ],
      },
      {
        id: 'work-packages',
        title: 'Work packages',
        body: [
          'A work package bundles related remediation into a single unit of work with an owner and a due date, so patching is tracked like any other deliverable.',
        ],
      },
      {
        id: 'risk-acceptance',
        title: 'Risk acceptance',
        body: [
          'When a vulnerability genuinely cannot be remediated, record a **risk acceptance**. It requires a justification, an expiry, and an approver — and it resurfaces automatically when it expires.',
        ],
      },
    ],
  },
  {
    id: 'faq',
    icon: 'CircleAlert',
    title: 'FAQ & support',
    summary: 'Common questions, and how to reach a human.',
    articles: [
      {
        id: 'access',
        title: 'I can\'t sign in',
        body: [
          'Sign-in is handled by your identity provider, so password resets and MFA changes happen there, not in Polaris. If your provider lets you in but Polaris does not, your account may not be linked to an organisation yet — contact the SOC.',
        ],
      },
      {
        id: 'data',
        title: 'Who can see my organisation\'s data?',
        body: [
          'Your data is scoped to your organisation. SOC staff working your incidents can see it; other tenants never can. Reports carry an explicit audience so a customer-facing document cannot include internal analyst notes.',
        ],
      },
      {
        id: 'contact',
        title: 'Getting help',
        body: [
          'Use **Report an issue** from anywhere in the app — it captures the page you were on. For anything time-critical, raise it on the incident itself so it reaches whoever is on call.',
        ],
      },
    ],
  },
];
