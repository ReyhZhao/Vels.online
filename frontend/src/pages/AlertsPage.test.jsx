import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';

vi.mock('../lib/axios', () => ({
  default: { get: vi.fn(), post: vi.fn(), patch: vi.fn() },
}));

vi.mock('../components/SlideOver', () => ({
  default: ({ open, children }) => open ? <div data-testid="slide-over">{children}</div> : null,
}));

vi.mock('../components/BulkPromoteModal', () => ({
  default: () => null,
}));

vi.mock('../components/CorrelationFromAlertsDrawer', () => ({
  default: () => null,
}));

vi.mock('../components/RuleAuthorDrawer', () => ({
  default: ({ initialScope, initialMessage, onClose }) => (
    <div data-testid="rule-author-drawer" data-scope={initialScope} data-message={initialMessage}>
      <button onClick={onClose}>close-drawer</button>
    </div>
  ),
}));

vi.mock('../context/AuthContext', () => ({
  useAuth: vi.fn(() => ({ user: { id: 1 } })),
}));

vi.mock('../context/OrgContext', () => {
  const selectedOrg = { slug: 'acme', name: 'Acme Corp' };
  return { useOrganization: vi.fn(() => ({ selectedOrg })) };
});

const mockNavigate = vi.fn();
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return { ...actual, useNavigate: () => mockNavigate };
});

import api from '../lib/axios';
import { useAuth } from '../context/AuthContext';
import AlertsPage from './AlertsPage';

const EMPTY_ALERTS = { count: 0, page: 1, per_page: 25, total_pages: 1, results: [] };

const SUGGESTION = {
  id: 42,
  rationale: 'Two alerts share the same source IP suggesting coordinated scanning.',
  confidence: 0.85,
  status: 'pending',
  proposed_alerts: [
    { id: 1, display_id: 'AL-0001', title: 'Port scan detected', severity: 'medium' },
    { id: 2, display_id: 'AL-0002', title: 'Brute force login', severity: 'high' },
  ],
  created_at: '2026-06-01T10:00:00Z',
};

function renderPage() {
  return render(
    <MemoryRouter>
      <AlertsPage />
    </MemoryRouter>
  );
}

describe('AlertsPage — Detection Suggestions', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockNavigate.mockReset();
    api.get.mockImplementation(url => {
      if (url === '/api/correlations/suggestions/') return Promise.resolve({ data: [] });
      return Promise.resolve({ data: EMPTY_ALERTS });
    });
  });

  it('fetches suggestions for the selected org', async () => {
    api.get.mockImplementation(url => {
      if (url === '/api/correlations/suggestions/') return Promise.resolve({ data: [SUGGESTION] });
      return Promise.resolve({ data: EMPTY_ALERTS });
    });
    renderPage();
    await waitFor(() =>
      expect(api.get).toHaveBeenCalledWith(
        '/api/correlations/suggestions/',
        expect.objectContaining({ params: { org: 'acme' } })
      )
    );
  });

  it('renders suggestion rationale and confidence', async () => {
    api.get.mockImplementation(url => {
      if (url === '/api/correlations/suggestions/') return Promise.resolve({ data: [SUGGESTION] });
      return Promise.resolve({ data: EMPTY_ALERTS });
    });
    renderPage();
    await waitFor(() => screen.getByText(SUGGESTION.rationale));
    expect(screen.getByText('85%')).toBeInTheDocument();
  });

  it('renders the grouped alert display_ids', async () => {
    api.get.mockImplementation(url => {
      if (url === '/api/correlations/suggestions/') return Promise.resolve({ data: [SUGGESTION] });
      return Promise.resolve({ data: EMPTY_ALERTS });
    });
    renderPage();
    await waitFor(() => screen.getByText('AL-0001'));
    expect(screen.getByText('AL-0002')).toBeInTheDocument();
  });

  it('does not show the suggestions section when there are no suggestions', async () => {
    renderPage();
    await waitFor(() => expect(api.get).toHaveBeenCalledWith('/api/correlations/suggestions/', expect.any(Object)));
    expect(screen.queryByText('Detection Suggestions')).not.toBeInTheDocument();
  });

  it('accept calls POST and removes suggestion, then navigates to new incident', async () => {
    api.get.mockImplementation(url => {
      if (url === '/api/correlations/suggestions/') return Promise.resolve({ data: [SUGGESTION] });
      return Promise.resolve({ data: EMPTY_ALERTS });
    });
    api.post.mockResolvedValue({ data: { incident_display_id: 'INC-2026-0099', suggestion: { id: 42 } } });

    renderPage();
    await waitFor(() => screen.getByText(SUGGESTION.rationale));

    fireEvent.click(screen.getByRole('button', { name: /accept/i }));

    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith('/api/correlations/suggestions/42/accept/')
    );
    await waitFor(() => expect(mockNavigate).toHaveBeenCalledWith('/incidents/INC-2026-0099'));
    expect(screen.queryByText(SUGGESTION.rationale)).not.toBeInTheDocument();
  });

  it('dismiss calls POST and removes suggestion from the list', async () => {
    api.get.mockImplementation(url => {
      if (url === '/api/correlations/suggestions/') return Promise.resolve({ data: [SUGGESTION] });
      return Promise.resolve({ data: EMPTY_ALERTS });
    });
    api.post.mockResolvedValue({ data: { id: 42, status: 'dismissed' } });

    renderPage();
    await waitFor(() => screen.getByText(SUGGESTION.rationale));

    fireEvent.click(screen.getByRole('button', { name: /dismiss/i }));

    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith('/api/correlations/suggestions/42/dismiss/')
    );
    await waitFor(() => expect(screen.queryByText(SUGGESTION.rationale)).not.toBeInTheDocument());
  });

  it('shows Detection Suggestions section heading with count', async () => {
    api.get.mockImplementation(url => {
      if (url === '/api/correlations/suggestions/') return Promise.resolve({ data: [SUGGESTION] });
      return Promise.resolve({ data: EMPTY_ALERTS });
    });
    renderPage();
    await waitFor(() => screen.getByText('Detection Suggestions'));
    expect(screen.getByText('(1)')).toBeInTheDocument();
  });
});

describe('AlertsPage — Codify as rule', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockNavigate.mockReset();
    api.get.mockImplementation(url => {
      if (url === '/api/correlations/suggestions/') return Promise.resolve({ data: [SUGGESTION] });
      return Promise.resolve({ data: EMPTY_ALERTS });
    });
  });

  it('"Codify as rule" button is not visible for non-staff users', async () => {
    useAuth.mockReturnValue({ user: { id: 1, is_staff: false } });
    renderPage();
    await waitFor(() => screen.getByText(SUGGESTION.rationale));
    expect(screen.queryByRole('button', { name: /codify as rule/i })).not.toBeInTheDocument();
  });

  it('"Codify as rule" button is not visible when is_staff is absent', async () => {
    useAuth.mockReturnValue({ user: { id: 1 } });
    renderPage();
    await waitFor(() => screen.getByText(SUGGESTION.rationale));
    expect(screen.queryByRole('button', { name: /codify as rule/i })).not.toBeInTheDocument();
  });

  it('"Codify as rule" button is visible for staff users', async () => {
    useAuth.mockReturnValue({ user: { id: 1, is_staff: true } });
    renderPage();
    await waitFor(() => screen.getByRole('button', { name: /codify as rule/i }));
  });

  it('clicking "Codify as rule" opens the drafting drawer scoped to the current org', async () => {
    useAuth.mockReturnValue({ user: { id: 1, is_staff: true } });
    renderPage();
    await waitFor(() => screen.getByRole('button', { name: /codify as rule/i }));

    fireEvent.click(screen.getByRole('button', { name: /codify as rule/i }));

    await waitFor(() => screen.getByTestId('rule-author-drawer'));
    expect(screen.getByTestId('rule-author-drawer')).toHaveAttribute('data-scope', 'acme');
  });

  it('the drawer initialMessage is seeded from suggestion rationale and alert IDs', async () => {
    useAuth.mockReturnValue({ user: { id: 1, is_staff: true } });
    renderPage();
    await waitFor(() => screen.getByRole('button', { name: /codify as rule/i }));

    fireEvent.click(screen.getByRole('button', { name: /codify as rule/i }));

    await waitFor(() => screen.getByTestId('rule-author-drawer'));
    const msg = screen.getByTestId('rule-author-drawer').getAttribute('data-message');
    expect(msg).toContain(SUGGESTION.rationale);
    expect(msg).toContain('AL-0001');
    expect(msg).toContain('AL-0002');
  });
});
