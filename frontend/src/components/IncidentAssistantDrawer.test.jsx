import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('@/lib/axios', () => ({
  default: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
}));

import api from '@/lib/axios';
import IncidentAssistantDrawer from './IncidentAssistantDrawer';

const DISPLAY_ID = 'INC-2026-0920';

function mockAssistantReply(proposedActions) {
  api.post.mockImplementation(url => {
    if (url.endsWith('/assistant/')) {
      return Promise.resolve({
        data: { assistant_reply: 'ok', proposed_actions: proposedActions, warnings: [], tool_trace: [], auto_actions: [] },
      });
    }
    // transition + assistant-confirm endpoints
    return Promise.resolve({ data: {} });
  });
}

async function sendMessageAndConfirm() {
  const user = userEvent.setup();
  render(<IncidentAssistantDrawer displayId={DISPLAY_ID} onClose={() => {}} />);
  await user.type(screen.getByPlaceholderText(/Ask about the incident/), 'close it');
  await user.click(screen.getByLabelText('Send message'));
  await screen.findByText('Confirm');
  await user.click(screen.getByText('Confirm'));
  return user;
}

describe('IncidentAssistantDrawer — confirming a close', () => {
  beforeEach(() => { vi.clearAllMocks(); });

  it('sends closure_reason to the transition endpoint when closing', async () => {
    mockAssistantReply([
      { type: 'transition_state', label: 'Close as false positive',
        payload: { state: 'closed', closure_reason: 'false_positive' } },
    ]);
    await sendMessageAndConfirm();

    await waitFor(() => {
      expect(api.post).toHaveBeenCalledWith(
        `/api/incidents/${DISPLAY_ID}/transition/`,
        { state: 'closed', closure_reason: 'false_positive' },
      );
    });
  });

  it('sends duplicate_of for a close-as-duplicate', async () => {
    mockAssistantReply([
      { type: 'transition_state', label: 'Close as duplicate',
        payload: { state: 'closed', closure_reason: 'duplicate', duplicate_of: 42 } },
    ]);
    await sendMessageAndConfirm();

    await waitFor(() => {
      expect(api.post).toHaveBeenCalledWith(
        `/api/incidents/${DISPLAY_ID}/transition/`,
        { state: 'closed', closure_reason: 'duplicate', duplicate_of: 42 },
      );
    });
  });

  it('omits closure_reason for a non-close transition', async () => {
    mockAssistantReply([
      { type: 'transition_state', label: 'Start work', payload: { state: 'in_progress' } },
    ]);
    await sendMessageAndConfirm();

    await waitFor(() => {
      expect(api.post).toHaveBeenCalledWith(
        `/api/incidents/${DISPLAY_ID}/transition/`,
        { state: 'in_progress' },
      );
    });
  });
});
