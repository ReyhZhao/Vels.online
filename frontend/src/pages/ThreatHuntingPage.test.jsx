import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';

vi.mock('../lib/axios', () => ({
  default: { get: vi.fn(), post: vi.fn(), delete: vi.fn() },
}));

import api from '../lib/axios';
import ThreatHuntingPage from './ThreatHuntingPage';

const HUNTS = [
  { id: 1, title: 'Alpha hunt', scope_all_orgs: true, status: 'completed', finding_count: 5, spawned_incident_count: 2, owner_username: 'alice' },
  { id: 2, title: 'Bravo hunt', scope_all_orgs: false, status: 'running', finding_count: 1, spawned_incident_count: 0, owner_username: 'bob' },
];

function mockGet(hunts = HUNTS) {
  api.get.mockImplementation(url => {
    if (url.startsWith('/api/security/organizations/')) return Promise.resolve({ data: [] });
    return Promise.resolve({ data: hunts });
  });
}

function renderPage() {
  return render(<MemoryRouter><ThreatHuntingPage /></MemoryRouter>);
}

// Both a mobile card list and a desktop table render in jsdom; the table is
// the deterministic surface for assertions.
const table = () => screen.getByRole('table');

describe('ThreatHuntingPage', () => {
  beforeEach(() => { vi.clearAllMocks(); });

  it('renders heading and hunt rows', async () => {
    mockGet();
    renderPage();
    await waitFor(() => within(table()).getByText('Alpha hunt'));
    expect(within(table()).getByText('Bravo hunt')).toBeInTheDocument();
  });

  it('shows empty state', async () => {
    mockGet([]);
    renderPage();
    await waitFor(() => expect(screen.getAllByText('No hunts yet.').length).toBeGreaterThan(0));
  });

  it('sorts by findings', async () => {
    mockGet();
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => within(table()).getByText('Alpha hunt'));
    // sort findings → default desc, Alpha (5) first
    await user.click(within(table()).getByRole('button', { name: 'Sort by Findings' }));
    let rows = within(table()).getAllByRole('row').slice(1);
    expect(within(rows[0]).getByText('Alpha hunt')).toBeInTheDocument();
    // toggle to asc → Bravo (1) first
    await user.click(within(table()).getByRole('button', { name: 'Sort by Findings' }));
    rows = within(table()).getAllByRole('row').slice(1);
    expect(within(rows[0]).getByText('Bravo hunt')).toBeInTheDocument();
  });

  it('excludes in-flight hunts from selection (disabled checkbox)', async () => {
    mockGet();
    renderPage();
    await waitFor(() => within(table()).getByText('Bravo hunt'));
    expect(within(table()).getByLabelText('Select Bravo hunt')).toBeDisabled();
    expect(within(table()).getByLabelText('Select Alpha hunt')).not.toBeDisabled();
  });

  it('bulk-deletes only deletable selected hunts after confirmation', async () => {
    mockGet();
    api.delete.mockResolvedValue({});
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => within(table()).getByText('Alpha hunt'));
    // Select all only picks up the deletable (non in-flight) hunt.
    await user.click(within(table()).getByLabelText('Select all'));
    await user.click(screen.getByRole('button', { name: 'Delete selected' }));
    await waitFor(() => expect(api.delete).toHaveBeenCalledWith('/api/hunts/1/'));
    expect(api.delete).not.toHaveBeenCalledWith('/api/hunts/2/');
  });

  it('search box and status filter remain present', async () => {
    mockGet();
    renderPage();
    await waitFor(() => within(table()).getByText('Alpha hunt'));
    expect(screen.getByLabelText('Search hunts')).toBeInTheDocument();
    expect(screen.getByLabelText('Filter by status')).toBeInTheDocument();
  });
});
