import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';

vi.mock('@/lib/axios', () => ({
  default: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
}));

import api from '@/lib/axios';
import CorrelationRulesAdmin from './CorrelationRulesAdmin';

const CATALOG = {
  fields: {
    alert_field: [
      { value: 'severity', label: 'severity' },
      { value: 'title', label: 'title' },
    ],
    entity: [{ value: 'source.ip', label: 'source.ip' }],
    source_ref: [{ value: 'rule_id', label: 'rule_id' }],
  },
  operators: {
    alert_field: [
      { value: 'equals', label: 'Equals' },
      { value: 'contains', label: 'Contains' },
    ],
    entity: [
      { value: 'equals', label: 'Equals' },
      { value: 'cidr', label: 'IP in CIDR' },
    ],
    source_ref: [{ value: 'equals', label: 'Equals' }],
  },
  field_kinds: [
    { value: 'alert_field', label: 'Alert field' },
    { value: 'entity', label: 'ECS entity' },
    { value: 'source_ref', label: 'Source ref key' },
  ],
  correlation_keys: [
    { value: 'none', label: 'None (org-wide)' },
    { value: 'source.ip', label: 'Source IP (source.ip)' },
  ],
  severities: ['critical', 'high', 'medium', 'low', 'info'],
};

const RULES = [
  {
    id: 1,
    name: 'Port Scan Rule',
    description: 'Detects port scans',
    correlation_key: 'source.ip',
    window_minutes: 30,
    severity: 'high',
    enabled: true,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    legs: [
      {
        id: 1,
        count: 2,
        display_order: 0,
        conditions: [
          { id: 1, field_kind: 'alert_field', field_name: 'severity', operator: 'equals', value: 'high' },
        ],
      },
    ],
  },
  {
    id: 2,
    name: 'Brute Force Rule',
    description: '',
    correlation_key: 'none',
    window_minutes: 60,
    severity: 'critical',
    enabled: false,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    legs: [],
  },
];

function mockGet(rules = RULES, catalog = CATALOG) {
  api.get.mockImplementation(url => {
    if (url === '/api/correlations/catalog/') return Promise.resolve({ data: catalog });
    return Promise.resolve({ data: rules });
  });
}

function renderPage() {
  return render(
    <MemoryRouter>
      <CorrelationRulesAdmin />
    </MemoryRouter>
  );
}

// Both a mobile card list and a desktop table render in jsdom; the table is
// the deterministic surface for assertions.
function table() {
  return screen.getByRole('table');
}

async function openKebab(user, name) {
  await user.click(within(table()).getByLabelText(`Actions for ${name}`));
  return within(table()).getByRole('menu');
}

describe('CorrelationRulesAdmin', () => {
  beforeEach(() => { vi.clearAllMocks(); });

  it('renders page heading', async () => {
    mockGet();
    renderPage();
    await waitFor(() => screen.getByText('Correlation Rules'));
  });

  it('shows loading state', () => {
    api.get.mockReturnValue(new Promise(() => {}));
    renderPage();
    expect(screen.getAllByText('Loading…').length).toBeGreaterThan(0);
  });

  it('shows empty state', async () => {
    mockGet([]);
    renderPage();
    await waitFor(() => expect(screen.getAllByText('No correlation rules.').length).toBeGreaterThan(0));
  });

  it('renders rule rows with severity and status badges', async () => {
    mockGet();
    renderPage();
    await waitFor(() => within(table()).getByText('Port Scan Rule'));
    expect(within(table()).getByText('Brute Force Rule')).toBeInTheDocument();
    expect(within(table()).getByText('Enabled')).toBeInTheDocument();
    expect(within(table()).getByText('Disabled')).toBeInTheDocument();
    expect(within(table()).getByText('high')).toBeInTheDocument();
    expect(within(table()).getByText('critical')).toBeInTheDocument();
  });

  it('filters by search query', async () => {
    mockGet();
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => within(table()).getByText('Port Scan Rule'));
    await user.type(screen.getByLabelText('Search rules'), 'brute');
    await waitFor(() => expect(within(table()).queryByText('Port Scan Rule')).not.toBeInTheDocument());
    expect(within(table()).getByText('Brute Force Rule')).toBeInTheDocument();
  });

  it('filters by severity', async () => {
    mockGet();
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => within(table()).getByText('Port Scan Rule'));
    await user.selectOptions(screen.getByLabelText('Severity filter'), 'critical');
    await waitFor(() => expect(within(table()).queryByText('Port Scan Rule')).not.toBeInTheDocument());
    expect(within(table()).getByText('Brute Force Rule')).toBeInTheDocument();
  });

  it('filters by enabled/disabled status', async () => {
    mockGet();
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => within(table()).getByText('Port Scan Rule'));
    await user.selectOptions(screen.getByLabelText('Status filter'), 'disabled');
    await waitFor(() => expect(within(table()).queryByText('Port Scan Rule')).not.toBeInTheDocument());
    expect(within(table()).getByText('Brute Force Rule')).toBeInTheDocument();
  });

  it('sorts by name', async () => {
    mockGet();
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => within(table()).getByText('Port Scan Rule'));
    // default name asc → Brute Force Rule first
    let rows = within(table()).getAllByRole('row').slice(1);
    expect(within(rows[0]).getByText('Brute Force Rule')).toBeInTheDocument();
    await user.click(within(table()).getByRole('button', { name: 'Sort by Name' }));
    rows = within(table()).getAllByRole('row').slice(1);
    expect(within(rows[0]).getByText('Port Scan Rule')).toBeInTheDocument();
  });

  it('disables a rule via the kebab', async () => {
    mockGet();
    api.patch.mockResolvedValue({ data: { ...RULES[0], enabled: false } });
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => within(table()).getByText('Port Scan Rule'));
    const menu = await openKebab(user, 'Port Scan Rule');
    await user.click(within(menu).getByRole('menuitem', { name: 'Disable' }));
    await waitFor(() => expect(api.patch).toHaveBeenCalledWith('/api/correlations/rules/1/', { enabled: false }));
  });

  it('enables a disabled rule via the kebab', async () => {
    mockGet();
    api.patch.mockResolvedValue({ data: { ...RULES[1], enabled: true } });
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => within(table()).getByText('Brute Force Rule'));
    const menu = await openKebab(user, 'Brute Force Rule');
    await user.click(within(menu).getByRole('menuitem', { name: 'Enable' }));
    await waitFor(() => expect(api.patch).toHaveBeenCalledWith('/api/correlations/rules/2/', { enabled: true }));
  });

  it('deletes a rule after confirmation via the kebab', async () => {
    mockGet();
    api.delete.mockResolvedValue({});
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => within(table()).getByText('Port Scan Rule'));
    const menu = await openKebab(user, 'Port Scan Rule');
    await user.click(within(menu).getByRole('menuitem', { name: 'Delete' }));
    await waitFor(() => expect(api.delete).toHaveBeenCalledWith('/api/correlations/rules/1/'));
    await waitFor(() => expect(within(table()).queryByText('Port Scan Rule')).not.toBeInTheDocument());
  });

  it('bulk-disables selected rules', async () => {
    mockGet();
    api.patch.mockResolvedValue({ data: { ...RULES[0], enabled: false } });
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => within(table()).getByText('Port Scan Rule'));
    await user.click(within(table()).getByLabelText('Select Port Scan Rule'));
    await user.click(screen.getByRole('button', { name: 'Disable selected' }));
    await waitFor(() => expect(api.patch).toHaveBeenCalledWith('/api/correlations/rules/1/', { enabled: false }));
  });

  it('bulk-deletes selected rules after confirmation', async () => {
    mockGet();
    api.delete.mockResolvedValue({});
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => within(table()).getByText('Port Scan Rule'));
    await user.click(within(table()).getByLabelText('Select Port Scan Rule'));
    await user.click(screen.getByRole('button', { name: 'Delete selected' }));
    await waitFor(() => expect(api.delete).toHaveBeenCalledWith('/api/correlations/rules/1/'));
  });

  it('opens the drawer when New rule is clicked', async () => {
    mockGet();
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => screen.getByText('Correlation Rules'));
    await user.click(screen.getByRole('button', { name: 'New rule' }));
    expect(screen.getByText('New Correlation Rule')).toBeInTheDocument();
  });

  it('opens edit drawer with pre-filled data via the kebab', async () => {
    mockGet();
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => within(table()).getByText('Port Scan Rule'));
    const menu = await openKebab(user, 'Port Scan Rule');
    await user.click(within(menu).getByRole('menuitem', { name: 'Edit' }));
    expect(screen.getByText('Edit Rule')).toBeInTheDocument();
    expect(screen.getByDisplayValue('Port Scan Rule')).toBeInTheDocument();
  });

  it('creates a new rule via the drawer', async () => {
    mockGet();
    const newRule = {
      id: 3,
      name: 'New Rule',
      description: '',
      correlation_key: 'none',
      window_minutes: 60,
      severity: 'medium',
      enabled: true,
      created_at: '2026-05-01T00:00:00Z',
      updated_at: '2026-05-01T00:00:00Z',
      legs: [{ id: 10, count: 1, display_order: 0, conditions: [] }],
    };
    api.post.mockResolvedValue({ data: newRule });
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => screen.getByText('Correlation Rules'));
    await user.click(screen.getByRole('button', { name: 'New rule' }));
    await user.type(screen.getByPlaceholderText('Rule name'), 'New Rule');
    await user.click(screen.getByRole('button', { name: 'Create rule' }));
    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith('/api/correlations/rules/', expect.objectContaining({ name: 'New Rule' }))
    );
    await waitFor(() => within(table()).getByText('New Rule'));
  });

  it('saves an edited rule via patch', async () => {
    mockGet();
    api.patch.mockResolvedValue({ data: { ...RULES[0], name: 'Updated Rule' } });
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => within(table()).getByText('Port Scan Rule'));
    const menu = await openKebab(user, 'Port Scan Rule');
    await user.click(within(menu).getByRole('menuitem', { name: 'Edit' }));
    const nameInput = screen.getByDisplayValue('Port Scan Rule');
    await user.clear(nameInput);
    await user.type(nameInput, 'Updated Rule');
    await user.click(screen.getByRole('button', { name: 'Save changes' }));
    await waitFor(() =>
      expect(api.patch).toHaveBeenCalledWith('/api/correlations/rules/1/', expect.objectContaining({ name: 'Updated Rule' }))
    );
  });

  it('leg builder adds and removes conditions', async () => {
    mockGet();
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => screen.getByText('Correlation Rules'));
    await user.click(screen.getByRole('button', { name: 'New rule' }));
    expect(screen.getByText('Leg 1')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '+ Add condition' }));
    expect(screen.getAllByRole('combobox', { name: 'Field kind' }).length).toBe(2);
    const removeBtns = screen.getAllByRole('button', { name: 'Remove condition' });
    await user.click(removeBtns[0]);
    expect(screen.getAllByRole('combobox', { name: 'Field kind' }).length).toBe(1);
  });

  it('leg builder adds a new leg', async () => {
    mockGet();
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => screen.getByText('Correlation Rules'));
    await user.click(screen.getByRole('button', { name: 'New rule' }));
    await user.click(screen.getByRole('button', { name: '+ Add leg' }));
    expect(screen.getByText('Leg 1')).toBeInTheDocument();
    expect(screen.getByText('Leg 2')).toBeInTheDocument();
  });
});
