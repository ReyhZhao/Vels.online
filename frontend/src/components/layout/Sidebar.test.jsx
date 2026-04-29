import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import Sidebar from './Sidebar';

function renderSidebar(initialPath = '/admin') {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <Sidebar />
    </MemoryRouter>
  );
}

describe('Sidebar', () => {
  it('renders a Dashboard link pointing to /admin', () => {
    renderSidebar();
    const link = screen.getByRole('link', { name: /dashboard/i });
    expect(link).toBeInTheDocument();
    expect(link).toHaveAttribute('href', '/admin');
  });

  it('renders an All Posts link pointing to /admin/posts', () => {
    renderSidebar();
    const link = screen.getByRole('link', { name: /all posts/i });
    expect(link).toBeInTheDocument();
    expect(link).toHaveAttribute('href', '/admin/posts');
  });

  it('renders a New Post link pointing to /admin/posts/new', () => {
    renderSidebar();
    const link = screen.getByRole('link', { name: /new post/i });
    expect(link).toBeInTheDocument();
    expect(link).toHaveAttribute('href', '/admin/posts/new');
  });

  it('renders Coming Soon service placeholders that are not links', () => {
    renderSidebar();
    expect(screen.getByText('Service Monitor')).toBeInTheDocument();
    expect(screen.getByText('Analytics')).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /service monitor/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /analytics/i })).not.toBeInTheDocument();
  });
});
