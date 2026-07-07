import { colors } from './theme';

export const SEVERITIES = ['critical', 'high', 'medium', 'low', 'info'] as const;

export function severityColor(severity: string | null | undefined): string {
  switch (severity) {
    case 'critical':
      return colors.destructive;
    case 'high':
      return colors.orange;
    case 'medium':
      return colors.warning;
    case 'low':
      return colors.primary;
    default:
      return colors.muted;
  }
}

export const ALERT_STATES = ['new', 'acknowledged', 'imported', 'ignored'] as const;

export const INCIDENT_STATES = [
  'new',
  'triaged',
  'in_progress',
  'on_hold',
  'pending_closure',
  'closed',
] as const;

export function stateColor(state: string | null | undefined): string {
  switch (state) {
    case 'new':
      return colors.primary;
    case 'triaged':
      return colors.purple;
    case 'in_progress':
    case 'acknowledged':
      return colors.warning;
    case 'on_hold':
      return colors.muted;
    case 'pending_closure':
      return colors.orange;
    case 'closed':
    case 'imported':
    case 'done':
      return colors.success;
    case 'ignored':
    case 'cancelled':
      return colors.muted;
    case 'running':
      return colors.warning;
    case 'failed':
    case 'error':
      return colors.destructive;
    default:
      return colors.muted;
  }
}

export const SOURCE_KINDS = [
  'wazuh_event',
  'vulnerability',
  'agent_finding',
  'api',
  'workflow',
  'external',
  'inbound_email',
  'scheduled_search',
] as const;
