import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { vi, describe, it, expect } from 'vitest';
import LandingPage from './LandingPage';

vi.mock('../lib/axios', () => ({
  default: { get: vi.fn() },
}));

import api from '../lib/axios';

function renderLandingPage() {
  return render(
    <MemoryRouter>
      <LandingPage />
    </MemoryRouter>
  );
}

describe('LandingPage', () => {
  it('renders the hero headline', () => {
    api.get.mockResolvedValue({ data: [] });
    renderLandingPage();
    expect(screen.getByRole('heading', { level: 1 })).toBeInTheDocument();
  });

  it('renders a "View Blog" CTA link pointing to /blog', () => {
    api.get.mockResolvedValue({ data: [] });
    renderLandingPage();
    const link = screen.getByRole('link', { name: /view blog/i });
    expect(link).toBeInTheDocument();
    expect(link).toHaveAttribute('href', '/blog');
  });

  it('renders the Services section with four service cards', () => {
    api.get.mockResolvedValue({ data: [] });
    renderLandingPage();
    expect(screen.getByText('Infrastructure')).toBeInTheDocument();
    expect(screen.getAllByText('App Ingress').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('Automation')).toBeInTheDocument();
    expect(screen.getByText('Managed Security')).toBeInTheDocument();
  });

  it('renders the Managed Security Services section heading', () => {
    api.get.mockResolvedValue({ data: [] });
    renderLandingPage();
    expect(screen.getByRole('heading', { name: 'Managed Security Services' })).toBeInTheDocument();
  });

  it('renders all six MSSP feature highlights', () => {
    api.get.mockResolvedValue({ data: [] });
    renderLandingPage();
    expect(screen.getByText('Incident triage and response')).toBeInTheDocument();
    expect(screen.getByText('Playbook enforcement')).toBeInTheDocument();
    expect(screen.getByText('Delegation and transfers')).toBeInTheDocument();
    expect(screen.getByText('TLP/PAP-aware communications')).toBeInTheDocument();
    expect(screen.getByText('Full audit trail')).toBeInTheDocument();
    expect(screen.getByText('Multi-organisation support')).toBeInTheDocument();
  });

  it('renders up to three PostCards when the API returns posts', async () => {
    api.get.mockResolvedValue({
      data: [
        { slug: 'post-1', title: 'Post One', published_at: '2026-01-01T00:00:00Z', content: 'Content one' },
        { slug: 'post-2', title: 'Post Two', published_at: '2026-01-02T00:00:00Z', content: 'Content two' },
        { slug: 'post-3', title: 'Post Three', published_at: '2026-01-03T00:00:00Z', content: 'Content three' },
      ],
    });
    renderLandingPage();
    await waitFor(() => {
      expect(screen.getByText('Post One')).toBeInTheDocument();
      expect(screen.getByText('Post Two')).toBeInTheDocument();
      expect(screen.getByText('Post Three')).toBeInTheDocument();
    });
  });

  it('renders an empty state when no posts are returned', async () => {
    api.get.mockResolvedValue({ data: [] });
    renderLandingPage();
    await waitFor(() => {
      expect(screen.getByText(/no posts yet/i)).toBeInTheDocument();
    });
  });

  it('renders a "View all posts" link pointing to /blog', async () => {
    api.get.mockResolvedValue({ data: [] });
    renderLandingPage();
    const links = screen.getAllByRole('link', { name: /view all posts/i });
    expect(links[0]).toHaveAttribute('href', '/blog');
  });
});
