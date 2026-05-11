import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('../lib/axios', () => ({
  default: { patch: vi.fn() },
}));

import api from '../lib/axios';
import EditExceptionModal from './EditExceptionModal';

const RULE = {
  id: 1,
  wazuh_rule_id: 200001,
  description: 'Suppress login failures',
  trigger_rule_id: 5763,
  match_value: '',
  field_name: 'agent.name',
  field_value: 'web-01',
  field_type: 'literal',
  scope: 'org',
  agent_name: 'web-01',
  status: 'pending',
};

describe('EditExceptionModal', () => {
  beforeEach(() => { vi.clearAllMocks(); });

  it('renders nothing when rule is null', () => {
    const { container } = render(
      <EditExceptionModal rule={null} onClose={vi.fn()} onSaved={vi.fn()} />
    );
    expect(container.firstChild).toBeNull();
  });

  it('renders with rule data pre-filled', () => {
    render(<EditExceptionModal rule={RULE} onClose={vi.fn()} onSaved={vi.fn()} />);
    expect(screen.getByRole('textbox', { name: /description/i })).toHaveValue('Suppress login failures');
    expect(screen.getByRole('spinbutton', { name: /trigger rule id/i })).toHaveValue(5763);
    expect(screen.getByRole('textbox', { name: /field name/i })).toHaveValue('agent.name');
  });

  it('shows title with wazuh_rule_id', () => {
    render(<EditExceptionModal rule={RULE} onClose={vi.fn()} onSaved={vi.fn()} />);
    expect(screen.getByText(/edit exception rule #200001/i)).toBeInTheDocument();
  });

  it('submit button disabled when description is empty', () => {
    render(<EditExceptionModal rule={{ ...RULE, description: '' }} onClose={vi.fn()} onSaved={vi.fn()} />);
    expect(screen.getByRole('button', { name: /save changes/i })).toBeDisabled();
  });

  it('calls PATCH and invokes onSaved on success', async () => {
    const updatedRule = { ...RULE, description: 'Updated', status: 'pending' };
    api.patch.mockResolvedValueOnce({ data: updatedRule });
    const onSaved = vi.fn();

    render(<EditExceptionModal rule={RULE} onClose={vi.fn()} onSaved={onSaved} />);

    const descField = screen.getByRole('textbox', { name: /description/i });
    fireEvent.change(descField, { target: { value: 'Updated' } });
    fireEvent.click(screen.getByRole('button', { name: /save changes/i }));

    await waitFor(() => expect(api.patch).toHaveBeenCalledWith(
      '/api/exceptions/1/',
      expect.objectContaining({ description: 'Updated' })
    ));
    await waitFor(() => expect(onSaved).toHaveBeenCalledWith(updatedRule));
  });

  it('shows inline error on API failure', async () => {
    api.patch.mockRejectedValueOnce({ response: { data: { detail: 'Permission denied.' } } });

    render(<EditExceptionModal rule={RULE} onClose={vi.fn()} onSaved={vi.fn()} />);
    fireEvent.click(screen.getByRole('button', { name: /save changes/i }));

    await waitFor(() => expect(screen.getByText('Permission denied.')).toBeInTheDocument());
  });

  it('calls onClose when Cancel is clicked', () => {
    const onClose = vi.fn();
    render(<EditExceptionModal rule={RULE} onClose={onClose} onSaved={vi.fn()} />);
    fireEvent.click(screen.getByRole('button', { name: /cancel/i }));
    expect(onClose).toHaveBeenCalled();
  });
});
