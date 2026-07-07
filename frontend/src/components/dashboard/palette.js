// Chart colors for the dashboard, validated with the dataviz palette checker
// against the app card surface (#0e172a): lightness band, chroma floor,
// adjacent-pair CVD separation and ≥3:1 contrast all pass. Change surfaces or
// hues together, not independently.

// Severity is a status scale (semantic heat). "info"/unrated is a deliberate
// neutral — same convention as the muted "Other" series in IncidentTrendChart.
export const SEVERITY_COLORS = {
  critical: '#d03b3b',
  high: '#e06a3f',
  medium: '#c98500',
  low: '#3987e5',
  info: '#64748b',
};

export const SEVERITY_ORDER = ['critical', 'high', 'medium', 'low', 'info'];

// Fixed categorical order for identity series (incident Subjects). Assigned by
// sorted position, never cycled; synthetic series get the neutral grays below.
export const CATEGORICAL = [
  '#3987e5', '#199e70', '#c98500', '#008300',
  '#9085e9', '#e66767', '#d55181', '#d95926',
];
export const NEUTRAL_SERIES = '#64748b';
export const NEUTRAL_SERIES_DIM = '#475569';

// Reserved status tokens (never used for identity series). Rendered with an
// icon or label beside them, never color alone.
export const STATUS_COLORS = {
  good: '#0ca30c',
  warning: '#c98500',
  critical: '#d03b3b',
};

export const INCIDENT_STATES = [
  { key: 'new', label: 'New' },
  { key: 'triaged', label: 'Triaged' },
  { key: 'in_progress', label: 'In Progress' },
  { key: 'on_hold', label: 'On Hold' },
  { key: 'needs_tuning', label: 'Needs Tuning' },
  { key: 'pending_closure', label: 'Pending Closure' },
];

export const SEVERITY_LABELS = {
  critical: 'Critical',
  high: 'High',
  medium: 'Medium',
  low: 'Low',
  info: 'Info',
};

// Chart chrome, one step off the card surface — solid hairlines, recessive.
export const GRID_STROKE = 'hsl(220 40% 18%)';
export const AXIS_TICK = { fontSize: 11, fill: 'hsl(215 20% 65%)' };
export const SURFACE = 'hsl(220 50% 11%)';

export const TOOLTIP_STYLE = {
  backgroundColor: 'hsl(220 50% 11%)',
  border: '1px solid hsl(220 40% 18%)',
  borderRadius: '6px',
  fontSize: '12px',
};
