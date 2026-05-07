import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('../lib/axios', () => ({
  default: { get: vi.fn(), post: vi.fn() },
}));

import api from '../lib/axios';
import DelegationPanel from './DelegationPanel';

const STAFF_USERS = [
  { id: 2, username: 'bob' },
  { id: 3, username: 'carol' },
];

const ACTIVE_DELEGATIONS = [
  { id: 10, user: 2, delegate_username: 'bob', delegated_by: 1, delegated_by_username: 'alice', delegated_at: '2026-01-01T00:00:00Z', note: 'please handle' },
];

function renderPanel(props = {}) {
  return render(
    <DelegationPanel
      incidentId="1"
      activeDelegations={[]}
      isStaff={true}
      onIncidentUpdate={vi.fn()}
      {...props}
    />
  );
}

describe('DelegationPanel', () => {
  beforeEach(() => vi.clearAllMocks());

  it('shows empty state when no active delegations', () => {
    renderPanel();
    expect(screen.getByText('No active delegations.')).toBeInTheDocument();
  });

  it('renders active delegation chips', () => {
    renderPanel({ activeDelegations: ACTIVE_DELEGATIONS });
    expect(screen.getByText('bob')).toBeInTheDocument();
    expect(screen.getByText(/please handle/)).toBeInTheDocument();
  });

  it('shows Delegate button for staff', () => {
    renderPanel({ isStaff: true });
    expect(screen.getByRole('button', { name: 'Delegate' })).toBeInTheDocument();
  });

  it('hides Delegate button for non-staff', () => {
    renderPanel({ isStaff: false });
    expect(screen.queryByRole('button', { name: 'Delegate' })).not.toBeInTheDocument();
  });

  it('opens delegate dialog with staff users', async () => {
    api.get.mockResolvedValue({ data: STAFF_USERS });
    const user = userEvent.setup();
    renderPanel();
    await user.click(screen.getByRole('button', { name: 'Delegate' }));
    await waitFor(() => screen.getByRole('heading', { name: 'Delegate incident' }));
    expect(screen.getByRole('option', { name: 'bob' })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: 'carol' })).toBeInTheDocument();
  });

  it('calls delegate API on confirm and closes dialog', async () => {
    api.get.mockResolvedValue({ data: STAFF_USERS });
    const updated = { active_delegations: [ACTIVE_DELEGATIONS[0]] };
    api.post.mockResolvedValue({ data: updated });
    const onUpdate = vi.fn();
    const user = userEvent.setup();
    renderPanel({ onIncidentUpdate: onUpdate });
    await user.click(screen.getByRole('button', { name: 'Delegate' }));
    await waitFor(() => screen.getByRole('heading', { name: 'Delegate incident' }));
    await user.selectOptions(screen.getByLabelText('Delegate to'), '2');
    await user.type(screen.getByLabelText(/Note/), 'please handle');
    await user.click(screen.getByRole('button', { name: 'Delegate' }));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith(
      '/api/incidents/1/delegate/',
      { user_id: 2, note: 'please handle' }
    ));
    expect(onUpdate).toHaveBeenCalledWith(updated);
    expect(screen.queryByRole('heading', { name: 'Delegate incident' })).not.toBeInTheDocument();
  });

  it('cancels delegate dialog without calling API', async () => {
    api.get.mockResolvedValue({ data: STAFF_USERS });
    const user = userEvent.setup();
    renderPanel();
    await user.click(screen.getByRole('button', { name: 'Delegate' }));
    await waitFor(() => screen.getByRole('heading', { name: 'Delegate incident' }));
    await user.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(api.post).not.toHaveBeenCalled();
    expect(screen.queryByRole('heading', { name: 'Delegate incident' })).not.toBeInTheDocument();
  });

  it('calls return API when Return button clicked', async () => {
    const onUpdate = vi.fn();
    api.post.mockResolvedValue({ data: { active_delegations: [] } });
    const user = userEvent.setup();
    renderPanel({ activeDelegations: ACTIVE_DELEGATIONS, onIncidentUpdate: onUpdate });
    await user.click(screen.getByRole('button', { name: 'Return delegation from bob' }));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith(
      '/api/incidents/1/delegations/10/return/'
    ));
    expect(onUpdate).toHaveBeenCalledWith({ active_delegations: [] });
  });

  it('shows error when delegate API fails', async () => {
    api.get.mockResolvedValue({ data: STAFF_USERS });
    api.post.mockRejectedValue({ response: { data: { detail: 'Cannot delegate to self.' } } });
    const user = userEvent.setup();
    renderPanel();
    await user.click(screen.getByRole('button', { name: 'Delegate' }));
    await waitFor(() => screen.getByRole('heading', { name: 'Delegate incident' }));
    await user.selectOptions(screen.getByLabelText('Delegate to'), '2');
    await user.click(screen.getByRole('button', { name: 'Delegate' }));
    await waitFor(() => screen.getByText('Cannot delegate to self.'));
  });
});
