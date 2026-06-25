import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { AuthContext } from '../../context/AuthContext';

vi.mock('../OrgSwitcher', () => ({
  default: () => <div data-testid="org-switcher" />,
}));

vi.mock('../ReportIssueModal', () => ({
  default: ({ open, onClose }) =>
    open ? <div data-testid="report-modal"><button onClick={onClose}>close-modal</button></div> : null,
}));

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

  it('renders Investigate section with Incidents link for a regular user', () => {
    renderSidebar(regularUser);

    expect(screen.getByRole('button', { name: /^investigate$/i })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /^incidents$/i })).toBeInTheDocument();
  });

  it('hides Subjects and Task Templates in Respond section for a regular user', () => {
    renderSidebar(regularUser);

    expect(screen.queryByRole('link', { name: /subjects/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /task templates/i })).not.toBeInTheDocument();
  });

  it('renders Subjects and Task Templates in Respond section for a staff user', () => {
    renderSidebar(staffUser);

    expect(screen.getByRole('link', { name: /subjects/i })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /task templates/i })).toBeInTheDocument();
  });

  it('hides Detect and Threat Ops sections for a regular user', () => {
    renderSidebar(regularUser);

    expect(screen.queryByRole('button', { name: /^detect$/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^threat ops$/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /correlation rules/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /threat hunting/i })).not.toBeInTheDocument();
  });

  it('renders Detect and Threat Ops sections for a staff user', () => {
    renderSidebar(staffUser);

    expect(screen.getByRole('link', { name: /correlation rules/i })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /search rules/i })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /threat hunting/i })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /attack map/i })).toBeInTheDocument();
  });

  it('renders Environment section with Assets and Contacts', () => {
    renderSidebar(regularUser);

    expect(screen.getByRole('button', { name: /^environment$/i })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /assets/i })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /contacts/i })).toBeInTheDocument();
  });

  it('renders On-Call link in the Admin section for a staff user', () => {
    renderSidebar(staffUser);

    expect(screen.getByRole('link', { name: /on-call/i })).toBeInTheDocument();
  });

  it('renders Security section items for a regular user', () => {
    renderSidebar(regularUser);

    expect(screen.getByRole('link', { name: /overview/i })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /vulnerabilities/i })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /enroll/i })).toBeInTheDocument();
  });

  it('Investigate and Security are separate sections', () => {
    renderSidebar(regularUser);

    expect(screen.getByRole('button', { name: /^investigate$/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^security$/i })).toBeInTheDocument();
  });

  it('does not render Blog or Admin sections for a regular user', () => {
    renderSidebar(regularUser);

    expect(screen.queryByText('Blog')).not.toBeInTheDocument();
    expect(screen.queryByText('Admin')).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /posts/i })).not.toBeInTheDocument();
  });

  it('renders Blog section items for a staff user', () => {
    renderSidebar(staffUser);

    expect(screen.getByRole('button', { name: /^blog$/i })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /^posts$/i })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /new post/i })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /blog administration/i })).toBeInTheDocument();
  });

  it('renders Admin section items for a staff user', () => {
    renderSidebar(staffUser);

    expect(screen.getByRole('link', { name: /service monitor/i })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /organisations/i })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /downloads/i })).toBeInTheDocument();
  });

  it('Blog section does not contain Admin-only items', () => {
    renderSidebar(staffUser);

    const blogToggle = screen.getByRole('button', { name: /^blog$/i });
    expect(blogToggle).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /service monitor/i })).toBeInTheDocument();
    expect(screen.getAllByRole('link', { name: /^posts$/i })).toHaveLength(1);
  });

  it('does not show Subjects or Task Templates in Admin section', () => {
    // they live in the Respond section
    renderSidebar(staffUser);

    const adminToggle = screen.getByRole('button', { name: /^admin$/i });
    expect(adminToggle).toBeInTheDocument();
    // Subjects and Task Templates are present (in Respond section), but NOT duplicated in Admin
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

  it('collapses Investigate section items when toggle is clicked', async () => {
    const user = userEvent.setup();
    renderSidebar(regularUser);

    expect(screen.getByRole('link', { name: /^incidents$/i })).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /^investigate$/i }));

    expect(screen.queryByRole('link', { name: /^incidents$/i })).not.toBeInTheDocument();
  });

  it('expands Investigate section again after a second toggle click', async () => {
    const user = userEvent.setup();
    renderSidebar(regularUser);

    await user.click(screen.getByRole('button', { name: /^investigate$/i }));
    await user.click(screen.getByRole('button', { name: /^investigate$/i }));

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

  it('collapses Blog section items when toggle is clicked', async () => {
    const user = userEvent.setup();
    renderSidebar(staffUser);

    expect(screen.getByRole('link', { name: /^posts$/i })).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /^blog$/i }));

    expect(screen.queryByRole('link', { name: /^posts$/i })).not.toBeInTheDocument();
  });

  it('collapses Admin section items when toggle is clicked', async () => {
    const user = userEvent.setup();
    renderSidebar(staffUser);

    expect(screen.getByRole('link', { name: /service monitor/i })).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /^admin$/i }));

    expect(screen.queryByRole('link', { name: /service monitor/i })).not.toBeInTheDocument();
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

  it('restores Investigate section collapsed state from localStorage on mount', () => {
    store['sidebar:investigate:open'] = 'false';
    renderSidebar(regularUser);

    expect(screen.queryByRole('link', { name: /^incidents$/i })).not.toBeInTheDocument();
  });

  it('persists Investigate section state to localStorage when toggled', async () => {
    const user = userEvent.setup();
    renderSidebar(regularUser);

    await user.click(screen.getByRole('button', { name: /^investigate$/i }));

    expect(JSON.parse(store['sidebar:investigate:open'])).toBe(false);
  });

  it('restores Security section collapsed state from localStorage on mount', () => {
    store['sidebar:security:open'] = 'false';
    renderSidebar(regularUser);

    expect(screen.queryByRole('link', { name: /overview/i })).not.toBeInTheDocument();
  });

  it('restores Blog section collapsed state from localStorage on mount', () => {
    store['sidebar:blog:open'] = 'false';
    renderSidebar(staffUser);

    expect(screen.queryByRole('link', { name: /^posts$/i })).not.toBeInTheDocument();
  });

  it('restores Admin section collapsed state from localStorage on mount', () => {
    store['sidebar:admin:open'] = 'false';
    renderSidebar(staffUser);

    expect(screen.queryByRole('link', { name: /service monitor/i })).not.toBeInTheDocument();
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

  // ── mobile positioning ────────────────────────────────────────────────────

  it('mobile-open aside starts at top-28 not at the top of the viewport', () => {
    const { container } = render(
      <MemoryRouter>
        <AuthContext.Provider value={{ user: regularUser, isAuthenticated: true, isLoading: false }}>
          <AppSidebar mobileOpen onMobileClose={() => {}} />
        </AuthContext.Provider>
      </MemoryRouter>
    );
    const aside = container.querySelector('aside');
    expect(aside.className).toContain('top-28');
    expect(aside.className).not.toContain('inset-y-0');
  });

  it('backdrop covers full viewport when mobile sidebar is open', () => {
    const { container } = render(
      <MemoryRouter>
        <AuthContext.Provider value={{ user: regularUser, isAuthenticated: true, isLoading: false }}>
          <AppSidebar mobileOpen onMobileClose={() => {}} />
        </AuthContext.Provider>
      </MemoryRouter>
    );
    const backdrop = container.querySelector('[aria-hidden="true"]');
    expect(backdrop.className).toContain('inset-0');
  });

  // ── OrgSwitcher + Report Issue in sidebar ─────────────────────────────────

  it('renders OrgSwitcher in expanded sidebar', () => {
    renderSidebar(regularUser);
    expect(screen.getByTestId('org-switcher')).toBeInTheDocument();
  });

  it('hides OrgSwitcher when sidebar is collapsed to icon-only mode', async () => {
    const user = userEvent.setup();
    renderSidebar(regularUser);
    await user.click(screen.getByRole('button', { name: /collapse sidebar/i }));
    expect(screen.queryByTestId('org-switcher')).not.toBeInTheDocument();
  });

  it('shows Report issue button in expanded sidebar for staff', () => {
    renderSidebar(staffUser);
    expect(screen.getByRole('button', { name: /report issue/i })).toBeInTheDocument();
  });

  it('does not show Report issue button for non-staff users', () => {
    renderSidebar(regularUser);
    expect(screen.queryByRole('button', { name: /report issue/i })).not.toBeInTheDocument();
  });

  it('hides Report issue button when sidebar is collapsed to icon-only mode', async () => {
    const user = userEvent.setup();
    renderSidebar(staffUser);
    await user.click(screen.getByRole('button', { name: /collapse sidebar/i }));
    expect(screen.queryByRole('button', { name: /report issue/i })).not.toBeInTheDocument();
  });

  it('opens ReportIssueModal when Report issue button is clicked', async () => {
    const user = userEvent.setup();
    renderSidebar(staffUser);
    await user.click(screen.getByRole('button', { name: /report issue/i }));
    expect(screen.getByTestId('report-modal')).toBeInTheDocument();
  });

  it('closes ReportIssueModal when modal requests close', async () => {
    const user = userEvent.setup();
    renderSidebar(staffUser);
    await user.click(screen.getByRole('button', { name: /report issue/i }));
    await user.click(screen.getByRole('button', { name: /close-modal/i }));
    expect(screen.queryByTestId('report-modal')).not.toBeInTheDocument();
  });

  // ── version badge ─────────────────────────────────────────────────────────

  it('shows the version badge for staff users', () => {
    renderSidebar(staffUser);
    expect(screen.getByText(/^v\d+\.\d+\.\d+ ·/)).toBeInTheDocument();
  });

  it('does not show the version badge for non-staff users', () => {
    renderSidebar(regularUser);
    expect(screen.queryByText(/^v\d+\.\d+\.\d+ ·/)).not.toBeInTheDocument();
  });

  it('keeps the version badge visible when the sidebar is collapsed', async () => {
    const user = userEvent.setup();
    renderSidebar(staffUser);
    await user.click(screen.getByRole('button', { name: /collapse sidebar/i }));
    // Report issue button is hidden when collapsed, but the version stays.
    expect(screen.queryByRole('button', { name: /report issue/i })).not.toBeInTheDocument();
    expect(screen.getByLabelText(/^Version \d+\.\d+\.\d+/)).toBeInTheDocument();
  });
});
