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
        id: 'scheduled-search',
        title: 'Scheduled Search Rules',
        body: [
          'A **scheduled search rule** looks for a pattern in your raw monitoring data on a repeating schedule. Where a correlation rule reacts the instant a matching alert arrives, a scheduled search rule works the other way round: every few minutes it *asks* the full stream of events your agents produce — “has this happened?” — and raises an incident when the answer is yes.',
          'That difference is the whole point. Correlation rules are **push**: a signal has to reach Polaris as an alert before a rule can act on it. Scheduled search rules are **pull**: they query everything your endpoints report, including the vast majority of events that are never promoted to alerts. It lets the SOC detect things that would otherwise stay buried in the noise — a slow pattern building over an hour, a handful of events that only matter together.',
          'When a rule matches, the events it found are pulled in as the **evidence** behind a new incident — the same incident, timeline and tasks you would get from any other detection. You never have to go digging in the raw data yourself; the rule brings the relevant events to you.',
          'Some rules fire on **absence** rather than presence — they raise an incident precisely because something went quiet. “No logs from the firewall in the last hour” is a real detection: a device that stops reporting is often the first sign of trouble, not a non-event.',
          'Scheduled search rules are written and tuned by the SOC on your behalf. You experience them through the incidents they raise, so there is nothing here for you to configure.',
        ],
      },
      {
        id: 'system-vs-org',
        title: 'System rules and org rules',
        body: [
          'Detection rules — both correlation and scheduled search — come in two tiers. **System rules** are authored by the Polaris SOC and apply to every organisation as baseline detection: the shared coverage every tenant gets out of the box.',
          '**Org rules** are specific to your organisation and only ever evaluate against your data. The SOC authors and tunes these for you as well, shaped around your environment and the threats that matter to you.',
          'You do not edit rules yourself — detection engineering is the SOC’s job — but the tuning is a conversation. If a rule is too noisy in your environment, ask the SOC to **mute** it for your organisation or adjust its thresholds; if you think you are missing coverage, tell us what you want to catch.',
        ],
      },
      {
        id: 'rule-tests',
        title: 'How we keep rules honest',
        body: [
          'Before a rule goes live — and every time we change one — the SOC can attach **rule tests** to it: small, saved checks that replay sample events through the rule and confirm it still fires exactly when it should, and stays quiet when it should not.',
          'It is detection-as-code, the same discipline software teams use to stop a change from quietly breaking something. Rule tests are what let us tune a noisy rule for you without worrying that we have blunted the detection it was built for.',
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
