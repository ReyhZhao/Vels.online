import { render, screen, waitFor, fireEvent, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('@/lib/axios', () => ({
  default: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
}));

import api from '@/lib/axios';
import IncidentAssistantDrawer from './IncidentAssistantDrawer';

const DISPLAY_ID = 'INC-2026-0920';

/**
 * Build a minimal streaming fetch mock that emits a full SSE sequence
 * (phase + result + done) and optionally surfaces proposed_actions.
 */
function mockStreamingAssistantReply(proposedActions = []) {
  const sse = [
    'event: phase\ndata: {"phase":"research"}\n\n',
    'event: phase\ndata: {"phase":"synthesis"}\n\n',
    `event: result\ndata: ${JSON.stringify({
      assistant_reply: 'ok',
      proposed_actions: proposedActions,
      warnings: [],
    })}\n\n`,
    'event: done\ndata: {}\n\n',
  ].join('');

  const encoder = new TextEncoder();
  const bytes = encoder.encode(sse);

  global.fetch = vi.fn().mockImplementation((url) => {
    if (String(url).includes('/assistant/')) {
      let consumed = false;
      return Promise.resolve({
        ok: true,
        status: 200,
        body: {
          getReader() {
            return {
              read() {
                if (!consumed) {
                  consumed = true;
                  return Promise.resolve({ done: false, value: bytes });
                }
                return Promise.resolve({ done: true, value: undefined });
              },
              releaseLock() {},
            };
          },
        },
      });
    }
    return Promise.resolve({ ok: true, status: 200 });
  });

  // api.post still used for confirm + other mutations
  api.post.mockResolvedValue({ data: {} });
  api.patch.mockResolvedValue({ data: {} });
}

async function sendMessageAndConfirm(proposedActions) {
  mockStreamingAssistantReply(proposedActions);
  render(<IncidentAssistantDrawer displayId={DISPLAY_ID} onClose={() => {}} />);

  // Type into the textarea and click Send using fireEvent (avoids userEvent.setup() jsdom issue)
  fireEvent.change(screen.getByPlaceholderText(/Ask about the incident/), {
    target: { value: 'close it' },
  });
  await act(async () => {
    fireEvent.click(screen.getByLabelText('Send message'));
  });

  // Wait for the streaming to complete and Confirm button to appear
  const confirmBtn = await screen.findByText('Confirm', {}, { timeout: 3000 });
  await act(async () => {
    fireEvent.click(confirmBtn);
  });
}

describe('IncidentAssistantDrawer — confirming a close', () => {
  beforeEach(() => { vi.clearAllMocks(); });

  it('sends closure_reason to the transition endpoint when closing', async () => {
    await sendMessageAndConfirm([
      { type: 'transition_state', label: 'Close as false positive',
        payload: { state: 'closed', closure_reason: 'false_positive' } },
    ]);

    await waitFor(() => {
      expect(api.post).toHaveBeenCalledWith(
        `/api/incidents/${DISPLAY_ID}/transition/`,
        { state: 'closed', closure_reason: 'false_positive' },
      );
    });
  });

  it('sends duplicate_of for a close-as-duplicate', async () => {
    await sendMessageAndConfirm([
      { type: 'transition_state', label: 'Close as duplicate',
        payload: { state: 'closed', closure_reason: 'duplicate', duplicate_of: 42 } },
    ]);

    await waitFor(() => {
      expect(api.post).toHaveBeenCalledWith(
        `/api/incidents/${DISPLAY_ID}/transition/`,
        { state: 'closed', closure_reason: 'duplicate', duplicate_of: 42 },
      );
    });
  });

  it('omits closure_reason for a non-close transition', async () => {
    await sendMessageAndConfirm([
      { type: 'transition_state', label: 'Start work', payload: { state: 'in_progress' } },
    ]);

    await waitFor(() => {
      expect(api.post).toHaveBeenCalledWith(
        `/api/incidents/${DISPLAY_ID}/transition/`,
        { state: 'in_progress' },
      );
    });
  });
});
