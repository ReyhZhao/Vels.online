import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import Breadcrumb from './Breadcrumb';

function renderAt(path, routePattern = path) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path={routePattern} element={<Breadcrumb />} />
      </Routes>
    </MemoryRouter>
  );
}

describe('Breadcrumb', () => {
  // Root pages — hidden
  it('renders nothing on /security root', () => {
    renderAt('/security');
    expect(screen.queryByRole('navigation', { name: /breadcrumb/i })).not.toBeInTheDocument();
  });

  // Admin — Services. "Admin" is a non-clickable label (the /admin blog dashboard
  // was removed with the blog split), only the leaf identifies the page.
  it('renders Admin › Service Monitor on /admin/status-settings', () => {
    renderAt('/admin/status-settings');
    expect(screen.getByText('Admin')).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Admin' })).not.toBeInTheDocument();
    expect(screen.getByText('Service Monitor')).toBeInTheDocument();
  });

  it('renders Admin › Organisations on /admin/security/organizations', () => {
    renderAt('/admin/security/organizations');
    expect(screen.getByText('Admin')).toBeInTheDocument();
    expect(screen.getByText('Organisations')).toBeInTheDocument();
  });

  it('renders Admin › Downloads on /admin/security/downloads', () => {
    renderAt('/admin/security/downloads');
    expect(screen.getByText('Admin')).toBeInTheDocument();
    expect(screen.getByText('Downloads')).toBeInTheDocument();
  });

  // Security
  it('renders Security › Enroll on /security/enroll', () => {
    renderAt('/security/enroll');
    expect(screen.getByRole('link', { name: 'Security' })).toHaveAttribute('href', '/security');
    expect(screen.getByText('Enroll')).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Enroll' })).not.toBeInTheDocument();
  });

  it('renders Security › Dashboard › Agent {id} on /security/agents/:agentId', () => {
    renderAt('/security/agents/001', '/security/agents/:agentId');
    expect(screen.getByRole('link', { name: 'Security' })).toHaveAttribute('href', '/security');
    expect(screen.getByRole('link', { name: 'Dashboard' })).toHaveAttribute('href', '/security');
    expect(screen.getByText('Agent 001')).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Agent 001' })).not.toBeInTheDocument();
  });

  // Accessibility
  it('has aria-label="breadcrumb" on the nav element', () => {
    renderAt('/admin/status-settings');
    expect(screen.getByRole('navigation', { name: /breadcrumb/i })).toBeInTheDocument();
  });
});
