import { render, screen, waitFor, fireEvent, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';

vi.mock('../lib/axios', () => ({
  default: { post: vi.fn() },
}));

vi.mock('../context/OrgContext', () => ({
  useOrganization: () => ({ selectedOrg: { slug: 'acme', name: 'Acme' } }),
}));

vi.mock('./SlideOver', () => ({
  default: ({ open, children, title }) =>
    open ? <div data-testid="slide-over"><h2>{title}</h2>{children}</div> : null,
}));

import api from '../lib/axios';
import CreateExceptionSlideOver from './CreateExceptionSlideOver';

const INCIDENT_WAZUH = {
  display_id: 'INC-2026-0001',
  org_slug: 'acme',
  source_kind: 'wazuh_event',
};

const GENERATE_RESPONSE = {
  trigger_rule_id: 5763,
  description: 'Suppress login failures',
  match_value: null,
  field_name: 'agent.name',
  field_value: 'web-01',
  field_type: 'literal',
  agent_name: 'web-01',
};

function renderSlideOver(props = {}) {
  return render(
    <MemoryRouter>
      <CreateExceptionSlideOver
        open={true}
        onClose={vi.fn()}
        incident={INCIDENT_WAZUH}
        {...props}
      />
    </MemoryRouter>
  );
}

describe('CreateExceptionSlideOver', () => {
  beforeEach(() => { vi.clearAllMocks(); });

  it('renders nothing when closed', () => {
    api.post.mockResolvedValue({ data: GENERATE_RESPONSE });
    const { container } = render(
      <MemoryRouter>
        <CreateExceptionSlideOver open={false} onClose={vi.fn()} incident={INCIDENT_WAZUH} />
      </MemoryRouter>
    );
    expect(container.firstChild).toBeNull();
  });

  it('shows the slide-over title', async () => {
    api.post.mockResolvedValue({ data: GENERATE_RESPONSE });
    renderSlideOver();
    await waitFor(() => expect(screen.getByText('Create Exception Rule')).toBeInTheDocument());
  });

  it('calls generate endpoint on open', async () => {
    api.post.mockResolvedValue({ data: GENERATE_RESPONSE });
    renderSlideOver();
    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith('/api/exceptions/generate/', {
        display_id: 'INC-2026-0001',
      })
    );
  });

  it('pre-fills form fields from generate response', async () => {
    api.post.mockResolvedValue({ data: GENERATE_RESPONSE });
    renderSlideOver();
    await waitFor(() =>
      expect(screen.getByRole('textbox', { name: /description/i })).toHaveValue('Suppress login failures')
    );
    expect(screen.getByRole('spinbutton', { name: /trigger rule id/i })).toHaveValue(5763);
    expect(screen.getByRole('textbox', { name: /field name/i })).toHaveValue('agent.name');
  });

  it('submit button is disabled when description is empty', async () => {
    api.post.mockResolvedValue({ data: { ...GENERATE_RESPONSE, description: '' } });
    renderSlideOver();
    await waitFor(() => expect(screen.getByRole('button', { name: /create exception/i })).toBeDisabled());
  });

  it('submit button is enabled when description is filled', async () => {
    api.post.mockResolvedValue({ data: GENERATE_RESPONSE });
    renderSlideOver();
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /create exception/i })).not.toBeDisabled()
    );
  });

  it('submits correct payload to POST /api/exceptions/', async () => {
    api.post
      .mockResolvedValueOnce({ data: GENERATE_RESPONSE })
      .mockResolvedValueOnce({ data: { id: 1, status: 'applied' } });
    renderSlideOver();
    await waitFor(() => screen.getByRole('button', { name: /create exception/i }));
    fireEvent.click(screen.getByRole('button', { name: /create exception/i }));
    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith('/api/exceptions/', expect.objectContaining({
        description: 'Suppress login failures',
        org: 'acme',
        incident: 'INC-2026-0001',
        trigger_rule_id: 5763,
      }))
    );
  });

  it('shows success message after successful submission', async () => {
    api.post
      .mockResolvedValueOnce({ data: GENERATE_RESPONSE })
      .mockResolvedValueOnce({ data: { id: 1, status: 'applied' } });
    renderSlideOver();
    await waitFor(() => screen.getByRole('button', { name: /create exception/i }));
    fireEvent.click(screen.getByRole('button', { name: /create exception/i }));
    await waitFor(() =>
      expect(screen.getByText(/exception rule created successfully/i)).toBeInTheDocument()
    );
  });

  it('shows inline error on API failure without closing', async () => {
    const onClose = vi.fn();
    api.post
      .mockResolvedValueOnce({ data: GENERATE_RESPONSE })
      .mockRejectedValueOnce({ response: { data: { detail: 'Pool exhausted.' } } });
    renderSlideOver({ onClose });
    await waitFor(() => screen.getByRole('button', { name: /create exception/i }));
    fireEvent.click(screen.getByRole('button', { name: /create exception/i }));
    await waitFor(() => expect(screen.getByText('Pool exhausted.')).toBeInTheDocument());
    expect(onClose).not.toHaveBeenCalled();
  });

  it('calls onClose when Cancel is clicked', async () => {
    const onClose = vi.fn();
    api.post.mockResolvedValue({ data: GENERATE_RESPONSE });
    renderSlideOver({ onClose });
    await waitFor(() => screen.getByRole('button', { name: /cancel/i }));
    fireEvent.click(screen.getByRole('button', { name: /cancel/i }));
    expect(onClose).toHaveBeenCalled();
  });

  it('shows error and keeps form editable if generate fails', async () => {
    api.post.mockRejectedValueOnce(new Error('LLM down'));
    renderSlideOver();
    await waitFor(() =>
      expect(screen.getByText(/could not generate a proposal/i)).toBeInTheDocument()
    );
    // Form remains open with empty defaults so user can fill manually
    expect(screen.getByRole('textbox', { name: /description/i })).toHaveValue('');
  });
});
