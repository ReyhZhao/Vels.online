import { render, screen, waitFor, within } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('../lib/axios', () => ({
  default: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
}));

import api from '../lib/axios';
import IncidentComments from './IncidentComments';

function aiTriageComment(overrides = {}) {
  return {
    id: 1,
    kind: 'ai_triage',
    author: null,
    author_username: null,
    body: 'Triage summary',
    is_internal: true,
    created_at: '2026-06-22T10:00:00Z',
    metadata: {},
    ...overrides,
  };
}

describe('IncidentComments', () => {
  beforeEach(() => {
    api.get.mockReset();
  });

  it('renders LLM-response labels on an AI triage comment (#592)', async () => {
    api.get.mockResolvedValue({
      data: [
        aiTriageComment({
          metadata: {
            primary_action: 'create_exception',
            secondary_action: 'notify_customer',
            false_positive_confidence: 0.82,
            disposition_confidence: 0.4,
            subject_recommendation: 'brute_force',
          },
        }),
      ],
    });
    render(<IncidentComments incidentId="INC-1" currentUserId={5} isStaff />);

    expect(await screen.findByText('create exception')).toBeInTheDocument();
    expect(screen.getByText('notify customer')).toBeInTheDocument();
    expect(screen.getByText('FP confidence: 82%')).toBeInTheDocument();
    expect(screen.getByText('Disposition confidence: 40%')).toBeInTheDocument();
    expect(screen.getByText('Subject: brute force')).toBeInTheDocument();
  });

  it('still renders a zero confidence rather than hiding it (#592)', async () => {
    api.get.mockResolvedValue({
      data: [aiTriageComment({ metadata: { disposition_confidence: 0 } })],
    });
    render(<IncidentComments incidentId="INC-1" currentUserId={5} isStaff />);
    expect(await screen.findByText('Disposition confidence: 0%')).toBeInTheDocument();
  });

  it('marks every AI triage comment but the latest as superseded (#593)', async () => {
    api.get.mockResolvedValue({
      data: [
        aiTriageComment({ id: 1, body: 'old triage', created_at: '2026-06-22T10:00:00Z' }),
        aiTriageComment({ id: 2, body: 'new triage', created_at: '2026-06-22T11:00:00Z' }),
      ],
    });
    render(<IncidentComments incidentId="INC-1" currentUserId={5} isStaff />);

    await screen.findByText('old triage');
    // Exactly one Superseded badge, attached to the older comment.
    const badges = screen.getAllByText('Superseded');
    expect(badges).toHaveLength(1);
    expect(badges[0].closest('.rounded-md')).toHaveTextContent('old triage');
  });

  it('does not mark a lone AI triage comment as superseded (#593)', async () => {
    api.get.mockResolvedValue({ data: [aiTriageComment({ body: 'only triage' })] });
    render(<IncidentComments incidentId="INC-1" currentUserId={5} isStaff />);
    await screen.findByText('only triage');
    expect(screen.queryByText('Superseded')).not.toBeInTheDocument();
  });
});
