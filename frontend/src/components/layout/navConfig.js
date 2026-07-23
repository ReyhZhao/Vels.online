import {
  LayoutDashboard,
  FileText,
  HardDrive,
  Server,
  Shield,
  Download,
  ShieldCheck,
  Bug,
  Activity,
  UserPlus,
  BarChart2,
  ClipboardList,
  ShieldOff,
  AlertTriangle,
  Tag,
  ListChecks,
  Lightbulb,
  Zap,
  Filter,
  Bell,
  Globe,
  History,
  CalendarClock,
  Mail,
  Users,
  GitBranch,
  Search,
  Handshake,
  Inbox,
  KeyRound,
  Webhook,
} from 'lucide-react';

// Top-level link rendered above the sections.
export const DASHBOARD_LINK = {
  to: '/dashboard',
  end: true,
  icon: LayoutDashboard,
  label: 'Dashboard',
};

// `badge` names a key in the counts object returned by useNavCounts.
// `badgeTone: 'info'` renders the badge blue (informational) instead of primary.
export const NAV_SECTIONS = [
  {
    id: 'investigate',
    label: 'Investigate',
    items: [
      { to: '/alerts', icon: Bell, label: 'Alert Inbox', badge: 'newAlerts', badgeTone: 'info' },
      { to: '/incidents', icon: AlertTriangle, label: 'Incidents', badge: 'openIncidents' },
      { to: '/reports', icon: FileText, label: 'Reports' },
    ],
  },
  {
    id: 'respond',
    label: 'Respond',
    items: [
      { to: '/tasks', icon: ListChecks, label: 'Tasks', badge: 'myTasks' },
      { to: '/admin/incidents/subjects', icon: Tag, label: 'Subjects', staffOnly: true },
      { to: '/admin/incidents/task-templates', icon: ListChecks, label: 'Task Templates', staffOnly: true },
      { to: '/admin/incidents/report-templates', icon: FileText, label: 'Report Templates', staffOnly: true },
      { to: '/admin/incidents/triage-lessons', icon: Lightbulb, label: 'Triage Lessons', staffOnly: true, badge: 'proposedTriageLessons', badgeTone: 'info' },
      { to: '/admin/incidents/automations', icon: Zap, label: 'Automations', staffOnly: true },
      { to: '/admin/wazuh-responses', icon: ShieldCheck, label: 'Wazuh Responses', staffOnly: true },
      { to: '/admin/partners/connections', icon: Handshake, label: 'Partner Connections', staffOnly: true },
      { to: '/admin/partners/intake-inbox', icon: Inbox, label: 'Intake Inbox', staffOnly: true, badge: 'intakeInbox', badgeTone: 'info' },
      { to: '/admin/ingest-endpoints', icon: Webhook, label: 'Ingest Endpoints', staffOnly: true },
    ],
  },
  {
    id: 'detect',
    label: 'Detect',
    staffOnly: true,
    items: [
      { to: '/admin/correlations/rules', icon: GitBranch, label: 'Correlation Rules' },
      { to: '/admin/correlations/search-rules', icon: Search, label: 'Search Rules' },
    ],
  },
  {
    id: 'threatops',
    label: 'Threat Ops',
    staffOnly: true,
    items: [
      { to: '/hunting', icon: Search, label: 'Threat Hunting' },
      { to: '/attack-map', icon: Globe, label: 'Attack Map' },
    ],
  },
  {
    id: 'environment',
    label: 'Environment',
    items: [
      { to: '/assets', icon: HardDrive, label: 'Assets' },
      { to: '/contacts', icon: Users, label: 'Contacts' },
    ],
  },
  {
    id: 'security',
    label: 'Security',
    items: [
      { to: '/security', end: true, icon: ShieldCheck, label: 'Overview' },
      { to: '/security/vulnerabilities', icon: Bug, label: 'Vulnerabilities' },
      { to: '/security/events', icon: Activity, label: 'Events' },
      { to: '/security/work-package', icon: ClipboardList, label: 'Work Package' },
      { to: '/security/risk-acceptances', icon: ShieldOff, label: 'Accepted Risks' },
      { to: '/exceptions', icon: Filter, label: 'Exception Rules' },
      { to: '/security/enroll', icon: UserPlus, label: 'Enroll' },
    ],
  },
  {
    id: 'ingress',
    label: 'App Ingress',
    items: [
      { to: '/routes', icon: Globe, label: 'Routes' },
    ],
  },
  {
    id: 'admin',
    label: 'Admin',
    staffOnly: true,
    items: [
      { to: '/admin/incidents/oncall', icon: CalendarClock, label: 'On-Call' },
      { to: '/admin/status-settings', icon: Server, label: 'Service Monitor' },
      { to: '/admin/security/organizations', icon: Shield, label: 'Organisations' },
      { to: '/admin/security/service-accounts', icon: KeyRound, label: 'Service Accounts' },
      { to: '/admin/security/downloads', icon: Download, label: 'Downloads' },
      { to: '/admin/signup-requests', icon: UserPlus, label: 'Signup Requests', badge: 'pendingSignups' },
      { to: '/admin/tasks/history', icon: History, label: 'Task History' },
      { to: '/admin/tasks/scheduled', icon: CalendarClock, label: 'Scheduled Tasks' },
      { to: '/admin/email-templates', icon: Mail, label: 'Email Templates' },
      { icon: BarChart2, label: 'Analytics', disabled: true, hint: 'Soon' },
    ],
  },
  {
    id: 'account',
    label: 'Account',
    items: [
      { to: '/account/notifications', icon: Bell, label: 'Notifications' },
    ],
  },
];
