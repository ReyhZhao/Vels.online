import { render, screen, waitFor } from '@testing-library/react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';

import DocsPage from './DocsPage';
import api from '../lib/axios';

// useAuth is read at render; flip `mockAuth.isAuthenticated` per test.
const { mockAuth } = vi.hoisted(() => ({ mockAuth: { isAuthenticated: true } }));
vi.mock('../context/AuthContext', () => ({ useAuth: () => mockAuth }));
vi.mock('../lib/axios', () => ({ default: { get: vi.fn() } }));

const EXTENDED = {
  sections: [
    {
      id: 'ssr-core',
      icon: 'Radar',
      title: 'Scheduled Search Rules — in depth',
      summary: 'The pull engine.',
      articles: [
        { id: 'pull-engine', title: 'The pull engine', body: ['A **Scheduled Search Rule** is a pull detector.'] },
      ],
    },
  ],
};

function renderPage() {
  return render(
    <MemoryRouter>
      <DocsPage />
    </MemoryRouter>
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mockAuth.isAuthenticated = true;
  vi.stubGlobal(
    'IntersectionObserver',
    class {
      observe() {}
      disconnect() {}
    }
  );
  Element.prototype.scrollIntoView = vi.fn();
});

describe('DocsPage — extended (authenticated) docs', () => {
  it('fetches and appends the in-depth sections when signed in', async () => {
    api.get.mockResolvedValue({ data: EXTENDED });
    renderPage();

    expect(api.get).toHaveBeenCalledWith('/api/docs/extended/');
    // The extended article renders inline alongside the public handbook.
    expect(await screen.findByRole('heading', { name: /the pull engine/i })).toBeInTheDocument();
    // …behind a divider that explains why it is visible (nav + reading column).
    expect(screen.getAllByText(/in-depth reference/i).length).toBeGreaterThan(0);
  });

  it('never requests the gated content when logged out', () => {
    mockAuth.isAuthenticated = false;
    api.get.mockResolvedValue({ data: EXTENDED });
    renderPage();

    expect(api.get).not.toHaveBeenCalled();
    expect(screen.queryByText(/in-depth reference/i)).not.toBeInTheDocument();
  });

  it('degrades quietly to the public handbook if the fetch fails', async () => {
    api.get.mockRejectedValue(new Error('offline'));
    renderPage();

    // The public content is still there; no extended divider appears.
    expect(screen.getByText(/Polaris uses single sign-on/i)).toBeInTheDocument();
    await waitFor(() => expect(api.get).toHaveBeenCalled());
    expect(screen.queryByText(/in-depth reference/i)).not.toBeInTheDocument();
  });
});
