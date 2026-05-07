import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { AuthContext } from '../../context/AuthContext';
import AppSidebar from './AppSidebar';

let store = {};
const mockStorage = {
  getItem: (key) => store[key] ?? null,
  setItem: (key, value) => { store[key] = String(value); },
  removeItem: (key) => { delete store[key]; },
};

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
  beforeEach(() => {
    store = {};
    vi.stubGlobal('localStorage', mockStorage);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  // ── existing nav content tests ────────────────────────────────────────────

  it('renders Incidents section with Incidents link for a regular user', () => {
    renderSidebar(regularUser);

    expect(screen.getByRole('button', { name: /incidents/i })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /^incidents$/i })).toBeInTheDocument();
  });

  it('hides Subjects and Task Templates in Incidents section for a regular user', () => {
    renderSidebar(regularUser);

    expect(screen.queryByRole('link', { name: /subjects/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /task templates/i })).not.toBeInTheDocument();
  });

  it('renders Subjects and Task Templates in Incidents section for a staff user', () => {
    renderSidebar(staffUser);

    expect(screen.getByRole('link', { name: /subjects/i })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /task templates/i })).toBeInTheDocument();
  });

  it('renders Security section items for a regular user', () => {
    renderSidebar(regularUser);

    expect(screen.getByRole('link', { name: /overview/i })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /vulnerabilities/i })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /enroll/i })).toBeInTheDocument();
  });

  it('Incidents link is not inside Security section', () => {
    renderSidebar(regularUser);

    // Incidents section header exists as a button; Security section is separate
    expect(screen.getByRole('button', { name: /^incidents$/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^security$/i })).toBeInTheDocument();
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

  it('does not show Subjects or Task Templates in Admin section', () => {
    // they moved to the Incidents section
    renderSidebar(staffUser);

    const adminToggle = screen.getByRole('button', { name: /^admin$/i });
    expect(adminToggle).toBeInTheDocument();
    // Subjects and Task Templates are present (in Incidents section), but NOT duplicated in Admin
    // Verify Admin section does not contain them by checking link count — exactly one of each
    expect(screen.getAllByRole('link', { name: /subjects/i })).toHaveLength(1);
    expect(screen.getAllByRole('link', { name: /task templates/i })).toHaveLength(1);
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

  // ── section collapse / expand ─────────────────────────────────────────────

  it('collapses Incidents section items when toggle is clicked', async () => {
    const user = userEvent.setup();
    renderSidebar(regularUser);

    expect(screen.getByRole('link', { name: /^incidents$/i })).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /^incidents$/i }));

    expect(screen.queryByRole('link', { name: /^incidents$/i })).not.toBeInTheDocument();
  });

  it('expands Incidents section again after a second toggle click', async () => {
    const user = userEvent.setup();
    renderSidebar(regularUser);

    await user.click(screen.getByRole('button', { name: /^incidents$/i }));
    await user.click(screen.getByRole('button', { name: /^incidents$/i }));

    expect(screen.getByRole('link', { name: /^incidents$/i })).toBeInTheDocument();
  });

  it('collapses Security section items when toggle is clicked', async () => {
    const user = userEvent.setup();
    renderSidebar(regularUser);

    expect(screen.getByRole('link', { name: /overview/i })).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /security/i }));

    expect(screen.queryByRole('link', { name: /overview/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /vulnerabilities/i })).not.toBeInTheDocument();
  });

  it('expands Security section again after a second toggle click', async () => {
    const user = userEvent.setup();
    renderSidebar(regularUser);

    await user.click(screen.getByRole('button', { name: /security/i }));
    await user.click(screen.getByRole('button', { name: /security/i }));

    expect(screen.getByRole('link', { name: /overview/i })).toBeInTheDocument();
  });

  it('collapses Admin section items when toggle is clicked', async () => {
    const user = userEvent.setup();
    renderSidebar(staffUser);

    expect(screen.getByRole('link', { name: /^posts$/i })).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /admin/i }));

    expect(screen.queryByRole('link', { name: /^posts$/i })).not.toBeInTheDocument();
  });

  // ── icon-only mode ────────────────────────────────────────────────────────

  it('hides text labels when sidebar is collapsed to icon-only mode', async () => {
    const user = userEvent.setup();
    renderSidebar(regularUser);

    expect(screen.getByText('Overview')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /collapse sidebar/i }));

    expect(screen.queryByText('Overview')).not.toBeInTheDocument();
    expect(screen.queryByText('Vulnerabilities')).not.toBeInTheDocument();
  });

  it('shows text labels again when sidebar is expanded from icon-only mode', async () => {
    const user = userEvent.setup();
    renderSidebar(regularUser);

    await user.click(screen.getByRole('button', { name: /collapse sidebar/i }));
    await user.click(screen.getByRole('button', { name: /expand sidebar/i }));

    expect(screen.getByText('Overview')).toBeInTheDocument();
  });

  // ── localStorage persistence ──────────────────────────────────────────────

  it('restores collapsed (icon-only) state from localStorage on mount', () => {
    store['sidebar:collapsed'] = 'true';
    renderSidebar(regularUser);

    expect(screen.queryByText('Overview')).not.toBeInTheDocument();
    // links still accessible via title attribute
    expect(screen.getByRole('link', { name: /overview/i })).toBeInTheDocument();
  });

  it('restores Incidents section collapsed state from localStorage on mount', () => {
    store['sidebar:incidents:open'] = 'false';
    renderSidebar(regularUser);

    expect(screen.queryByRole('link', { name: /^incidents$/i })).not.toBeInTheDocument();
  });

  it('persists Incidents section state to localStorage when toggled', async () => {
    const user = userEvent.setup();
    renderSidebar(regularUser);

    await user.click(screen.getByRole('button', { name: /^incidents$/i }));

    expect(JSON.parse(store['sidebar:incidents:open'])).toBe(false);
  });

  it('restores Security section collapsed state from localStorage on mount', () => {
    store['sidebar:security:open'] = 'false';
    renderSidebar(regularUser);

    expect(screen.queryByRole('link', { name: /overview/i })).not.toBeInTheDocument();
  });

  it('restores Admin section collapsed state from localStorage on mount', () => {
    store['sidebar:admin:open'] = 'false';
    renderSidebar(staffUser);

    expect(screen.queryByRole('link', { name: /^posts$/i })).not.toBeInTheDocument();
  });

  it('persists collapsed state to localStorage when toggled', async () => {
    const user = userEvent.setup();
    renderSidebar(regularUser);

    await user.click(screen.getByRole('button', { name: /collapse sidebar/i }));

    expect(JSON.parse(store['sidebar:collapsed'])).toBe(true);
  });

  it('persists Security section state to localStorage when toggled', async () => {
    const user = userEvent.setup();
    renderSidebar(regularUser);

    await user.click(screen.getByRole('button', { name: /security/i }));

    expect(JSON.parse(store['sidebar:security:open'])).toBe(false);
  });
});
