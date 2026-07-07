export interface Paginated<T> {
  count: number;
  page: number;
  per_page: number;
  total_pages: number;
  results: T[];
}

export interface User {
  id: number;
  username: string;
  email: string;
  is_staff: boolean;
  default_org_slug: string | null;
}

export interface Organization {
  id: number;
  name: string;
  slug: string;
  is_infrastructure: boolean;
}

export interface Alert {
  id: number;
  display_id: string;
  title: string;
  severity: string;
  description: string;
  pap: string;
  tlp: string;
  state: string;
  source_kind: string;
  source_ref: Record<string, unknown>;
  incident: number | null;
  incident_display_id: string | null;
  acknowledged_by: number | null;
  acknowledged_at: string | null;
  created_at: string;
  updated_at: string;
  org_slug: string;
}

export interface Incident {
  id: number;
  display_id: string;
  title: string;
  description: string;
  severity: string;
  tlp: string;
  pap: string;
  state: string;
  closure_reason: string | null;
  subject_slug: string | null;
  subject_name: string | null;
  source_kind: string;
  org_slug: string;
  org_name: string;
  assignee: number | null;
  assignee_username: string | null;
  created_by_username: string | null;
  created_at: string;
  updated_at: string;
  response_sla: { due_at: string; breached: boolean } | null;
  resolve_sla: { due_at: string; breached: boolean } | null;
  linked_alert_count: number;
  attachment_count: number;
  task_count: number;
  contact_count: number;
  triage_running: boolean;
  iocs: { id: number; kind: string; value: string }[];
  assets: { id: number; asset: Asset }[];
}

export interface Comment {
  id: number;
  incident: number;
  task: number | null;
  author_username: string | null;
  kind: string;
  origin: string;
  body: string;
  is_internal: boolean;
  created_at: string;
  updated_at: string;
  deleted_at: string | null;
  can_edit: boolean;
}

export interface IncidentTask {
  id: number;
  title: string;
  description: string;
  state: string;
  task_type: string;
  assignee_username: string | null;
  display_order: number;
  created_at: string;
  closed_at: string | null;
}

export interface SearchRuleLeg {
  id: number;
  count: number;
  count_operator: 'gte' | 'lte';
  display_order: number;
  distinct_field: string | null;
  min_distinct: number | null;
  novelty_field: string | null;
  conditions: { field_name: string; operator: string; value: string }[];
}

export interface SearchRule {
  id: number;
  organization: number | null;
  name: string;
  description: string;
  severity: string;
  correlation_key: string;
  window_minutes: number;
  interval_minutes: number;
  enabled: boolean;
  created_at: string;
  updated_at: string;
  legs: SearchRuleLeg[];
  test_summary: { total: number; passing: number; failing: number; error: number; never: number };
  firing_summary: { count: number; last_fired_at: string | null };
}

export interface HuntFinding {
  id: number;
  organization: number;
  organization_name: string;
  lens: string;
  source_index: string;
  wazuh_doc_id: string;
  summary: string;
  materialised_incident_display_id: string | null;
  created_at: string;
}

export interface HuntEvent {
  seq: number;
  turn: number;
  type: string;
  data: Record<string, unknown>;
  created_at: string;
}

export interface Hunt {
  id: string;
  title: string;
  seed_kind: string;
  status: string;
  scope_all_orgs: boolean;
  lookback_days: number;
  owner_username: string | null;
  finding_count: number;
  spawned_incident_count: number;
  created_at: string;
  updated_at: string;
  // detail-only fields
  seed_text?: string;
  seed_url?: string;
  plan?: string;
  transcript?: string;
  events?: HuntEvent[];
  findings?: HuntFinding[];
  proposed_incidents?: {
    organization_id: number;
    organization_name: string;
    finding_count: number;
    title?: string;
  }[];
}

export interface Contact {
  id: number;
  name: string;
  email: string;
  job_title: string;
  department: string;
  org_slug: string;
  org_name: string;
  created_at: string;
}

export interface AssetExposure {
  kind: 'ingress_route' | 'direct_nat';
  protection: 'protected' | 'raw';
  specifics: Record<string, unknown>;
}

export interface Asset {
  id: number;
  kind: 'host' | 'route';
  name: string;
  agent_name: string | null;
  ip_address: string | null;
  role: string | null;
  route_fqdn: string | null;
  org_slug: string;
  is_active: boolean;
  is_permanent: boolean;
  last_seen_at: string | null;
  created_at: string;
  internet_facing: boolean;
  exposures: AssetExposure[];
}

export interface AppNotification {
  id: number;
  kind: string;
  incident_id: number | null;
  incident_display_id: string | null;
  task_id: number | null;
  payload: { title?: string; body?: string; link?: string };
  created_at: string;
  read_at: string | null;
}
