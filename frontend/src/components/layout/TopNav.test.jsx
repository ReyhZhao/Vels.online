import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';

vi.mock('../../hooks/useStatus', () => ({
  useStatus: () => ({ overallStatus: 'operational', isLoading: false }),
}));

import TopNav from './TopNav';

function renderTopNav(initialPath = '/') {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <TopNav />
    </MemoryRouter>
  );
}

describe('TopNav', () => {
  it('renders the site brand link', () => {
    renderTopNav();
    const brand = screen.getByRole('link', { name: 'vels.online' });
    expect(brand).toBeInTheDocument();
    expect(brand).toHaveAttribute('href', '/');
  });

  it('renders a Blog navigation link pointing to /blog', () => {
    renderTopNav();
    const blogLink = screen.getByRole('link', { name: 'Blog' });
    expect(blogLink).toBeInTheDocument();
    expect(blogLink).toHaveAttribute('href', '/blog');
  });

  it('renders StatusIndicator linking to /status', () => {
    renderTopNav();
    const statusLink = screen.getByRole('link', { name: /site status/i });
    expect(statusLink).toBeInTheDocument();
    expect(statusLink).toHaveAttribute('href', '/status');
  });
});
