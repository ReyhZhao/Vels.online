import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { AuthContext } from '../../context/AuthContext';
import AppSidebar from './AppSidebar';

function renderSidebar(user, initialPath = '/security') {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <AuthContext.Provider value={{ user, isAuthenticated: true, isLoading: false }}>
        <AppSidebar />
      </AuthContext.Provider>
    </MemoryRouter>
  );
}

const regularUser = { id: 1, username: 'alice', is_staff: false };
const staffUser = { id: 2, username: 'bob', is_staff: true };

describe('AppSidebar', () => {
  it('renders Security section items for a regular user', () => {
    renderSidebar(regularUser);

    expect(screen.getByRole('link', { name: /overview/i })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /vulnerabilities/i })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /enroll/i })).toBeInTheDocument();
  });

  it('does not render Admin section for a regular user', () => {
    renderSidebar(regularUser);

    expect(screen.queryByText('Admin')).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /posts/i })).not.toBeInTheDocument();
  });

  it('renders Admin section items for a staff user', () => {
    renderSidebar(staffUser);

    expect(screen.getByRole('link', { name: /^posts$/i })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /new post/i })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /service monitor/i })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /organisations/i })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /downloads/i })).toBeInTheDocument();
  });

  it('renders Analytics as visually disabled (not a link) for staff user', () => {
    renderSidebar(staffUser);

    expect(screen.queryByRole('link', { name: /analytics/i })).not.toBeInTheDocument();
    expect(screen.getByText('Analytics')).toBeInTheDocument();
  });

  it('highlights the Overview link when on /security', () => {
    renderSidebar(regularUser, '/security');

    const overviewLink = screen.getByRole('link', { name: /overview/i });
    expect(overviewLink).toHaveClass('bg-accent');
  });

  it('highlights the Vulnerabilities link when on /security/vulnerabilities', () => {
    renderSidebar(regularUser, '/security/vulnerabilities');

    const vulnLink = screen.getByRole('link', { name: /vulnerabilities/i });
    expect(vulnLink).toHaveClass('bg-accent');
  });

  it('does not highlight Overview when on a sub-route', () => {
    renderSidebar(regularUser, '/security/vulnerabilities');

    const overviewLink = screen.getByRole('link', { name: /overview/i });
    expect(overviewLink).not.toHaveClass('bg-accent');
  });
});
