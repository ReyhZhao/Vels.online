import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('@/lib/axios', () => ({
  default: { get: vi.fn(), post: vi.fn() },
}));

import api from '@/lib/axios';
import TriageLessonsReview from './TriageLessonsReview';

const LESSON = {
  id: 1, tier: 'org', subject_name: 'Brute Force', source_kind: 'wazuh_event',
  selector: 'internal source ip', guidance: 'verify the source is not our scanner',
  status: 'proposed', provenance: 'distilled_from_human_close', applied_count: 0,
  contradiction_count: 0, evidence_display_ids: ['INC-2026-0001'],
  created_at: '2026-07-10T10:00:00Z', updated_at: '2026-07-10T10:00:00Z',
};

const RUN = {
  id: 7, started_at: '2026-07-11T09:00:00Z', finished_at: '2026-07-11T09:00:01Z',
  eligible_count: 5, cluster_count: 2, proposed_count: 1, proposed_global_count: 0,
  clusters: [
    { tier: 'org', organization: 'acme', subject: 'Brute Force', source_kind: 'wazuh_event', evidence_count: 3, outcome: 'proposed' },
    { tier: 'org', organization: 'acme', subject: 'Port Scan', source_kind: 'wazuh_event', evidence_count: 2, outcome: 'skipped_insufficient_evidence' },
  ],
};

function mockApi({ lessons = [LESSON], runs = [RUN] } = {}) {
  api.get.mockImplementation((url) => {
    if (url.includes('/runs/')) return Promise.resolve({ data: runs });
    return Promise.resolve({ data: lessons });
  });
}

describe('TriageLessonsReview — recent sweeps (#697)', () => {
  beforeEach(() => vi.clearAllMocks());

  it('renders the lesson list and fetches recent sweeps', async () => {
    mockApi();
    render(<TriageLessonsReview />);
    await waitFor(() => expect(screen.getByText(/verify the source is not our scanner/)).toBeInTheDocument());
    expect(api.get).toHaveBeenCalledWith('/api/incidents/triage-lessons/runs/');
    expect(screen.getByText(/Recent sweeps/)).toBeInTheDocument();
  });

  it('expands a sweep to show per-cluster outcomes, including a skipped one', async () => {
    mockApi();
    render(<TriageLessonsReview />);
    await waitFor(() => expect(screen.getByText(/Recent sweeps/)).toBeInTheDocument());

    await userEvent.click(screen.getByText(/Recent sweeps/));
    // Run summary line is visible once the panel is open.
    const runLine = await screen.findByText(/1 proposed/);
    expect(screen.getByText(/5 eligible/)).toBeInTheDocument();

    // Expand the run to reveal the per-cluster breakdown.
    await userEvent.click(runLine);
    expect(await screen.findByText('Proposed')).toBeInTheDocument();
    expect(screen.getByText('Too few cases')).toBeInTheDocument();
    expect(screen.getByText('Port Scan')).toBeInTheDocument();
  });

  it('surfaces a sweep-fetch failure without breaking the page', async () => {
    api.get.mockImplementation((url) => {
      if (url.includes('/runs/')) return Promise.reject(new Error('boom'));
      return Promise.resolve({ data: [LESSON] });
    });
    render(<TriageLessonsReview />);
    await waitFor(() => expect(screen.getByText(/verify the source is not our scanner/)).toBeInTheDocument());
    await userEvent.click(screen.getByText(/Recent sweeps/));
    expect(await screen.findByText('Failed to load recent sweeps.')).toBeInTheDocument();
  });
});
