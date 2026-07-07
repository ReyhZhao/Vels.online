import { render, screen, within } from '@testing-library/react';
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

vi.mock('@/lib/axios', () => ({
  default: { get: vi.fn(), post: vi.fn() },
}));

import api from '@/lib/axios';
import AppSidebar from './AppSidebar';

let store = {};
const mockStorage = {
  getItem: (key) => store[key] ?? null,
  setItem: (key, value) => { store[key] = String(value); },
  removeItem: (key) => { delete store[key]; },
};

// api.get responder for the useNavCounts endpoints.
function mockCounts({ alerts = 0, incidents = 0, tasksNew = 0, tasksInProgress = 0, signups = 0 } = {}) {
  api.get.mockImplementation((url, opts) => {
    const params = opts?.params ?? {};
    if (url === '/api/alerts/') return Promise.resolve({ data: { count: alerts } });
    if (url === '/api/incidents/') return Promise.resolve({ data: { count: incidents } });
    if (url === '/api/tasks/') {
      return Promise.resolve({ data: { count: params.state === 'new' ? tasksNew : tasksInProgress } });
    }
    if (url === '/api/signups/pending-count/') return Promise.resolve({ data: { count: signups } });
    return Promise.resolve({ data: {} });
  });
}

function renderSidebar(user, initialPath = '/security', props = {}) {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <AuthContext.Provider value={{ user, isAuthenticated: true, isLoading: false }}>
        <AppSidebar {...props} />
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
    mockCounts();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.clearAllMocks();
  });

  // ── nav content ────────────────────────────────────────────────────────────

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

  it('does not duplicate Subjects or Task Templates across sections', () => {
    renderSidebar(staffUser);

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

  // ── count badges (insights) ─────────────────────────────────────────────────

  it('shows new-alert count badge on the Alert Inbox link', async () => {
    mockCounts({ alerts: 7 });
    renderSidebar(regularUser);

    const link = screen.getByRole('link', { name: /alert inbox/i });
    expect(await within(link).findByText('7')).toBeInTheDocument();
  });

  it('shows open-incident count badge on the Incidents link', async () => {
    mockCounts({ incidents: 4 });
    renderSidebar(regularUser);

    const link = screen.getByRole('link', { name: /^incidents/i });
    expect(await within(link).findByText('4')).toBeInTheDocument();
  });

  it('shows my open tasks badge on the Tasks link (new + in progress)', async () => {
    mockCounts({ tasksNew: 2, tasksInProgress: 3 });
    renderSidebar(regularUser);

    const link = screen.getByRole('link', { name: /^tasks/i });
    expect(await within(link).findByText('5')).toBeInTheDocument();
  });

  it('shows pending signups badge on the Signup Requests link for staff', async () => {
    mockCounts({ signups: 6 });
    renderSidebar(staffUser);

    const link = screen.getByRole('link', { name: /signup requests/i });
    expect(await within(link).findByText('6')).toBeInTheDocument();
  });

  it('does not fetch pending signups for a regular user', async () => {
    mockCounts({ alerts: 1 });
    renderSidebar(regularUser);
    await screen.findByText('1');

    expect(api.get).not.toHaveBeenCalledWith('/api/signups/pending-count/', undefined);
  });

  it('caps badge counts at 99+', async () => {
    mockCounts({ alerts: 250 });
    renderSidebar(regularUser);

    expect(await screen.findByText('99+')).toBeInTheDocument();
  });

  it('shows no badge when a count is zero', async () => {
    mockCounts({ incidents: 0, alerts: 3 });
    renderSidebar(regularUser);
    await screen.findByText('3');

    const link = screen.getByRole('link', { name: /^incidents$/i });
    expect(within(link).queryByText('0')).not.toBeInTheDocument();
  });

  it('rolls badge counts up onto a closed section header', async () => {
    store['sidebar:investigate:open'] = 'false';
    mockCounts({ alerts: 3, incidents: 2 });
    renderSidebar(regularUser);

    const toggle = screen.getByRole('button', { name: /investigate/i });
    expect(await within(toggle).findByText('5')).toBeInTheDocument();
  });

  it('does not show a rollup badge on an open section header', async () => {
    mockCounts({ alerts: 3, incidents: 2 });
    renderSidebar(regularUser);
    await screen.findByText('3');

    const toggle = screen.getByRole('button', { name: /^investigate$/i });
    expect(within(toggle).queryByText('5')).not.toBeInTheDocument();
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

    await user.click(screen.getByRole('button', { name: /^security$/i }));

    expect(screen.queryByRole('link', { name: /overview/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /vulnerabilities/i })).not.toBeInTheDocument();
  });

  it('expands Security section again after a second toggle click', async () => {
    const user = userEvent.setup();
    renderSidebar(regularUser);

    await user.click(screen.getByRole('button', { name: /^security$/i }));
    await user.click(screen.getByRole('button', { name: /^security$/i }));

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

  it('renders Account as a collapsible section', async () => {
    const user = userEvent.setup();
    renderSidebar(regularUser);

    expect(screen.getByRole('link', { name: /notifications/i })).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /^account$/i }));

    expect(screen.queryByRole('link', { name: /notifications/i })).not.toBeInTheDocument();
  });

  // ── quick filter ──────────────────────────────────────────────────────────

  it('renders a menu filter input', () => {
    renderSidebar(regularUser);
    expect(screen.getByRole('textbox', { name: /filter menu/i })).toBeInTheDocument();
  });

  it('filters nav items by label', async () => {
    const user = userEvent.setup();
    renderSidebar(regularUser);

    await user.type(screen.getByRole('textbox', { name: /filter menu/i }), 'vuln');

    expect(screen.getByRole('link', { name: /vulnerabilities/i })).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /^incidents$/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /dashboard/i })).not.toBeInTheDocument();
  });

  it('filter reveals matching items inside a closed section', async () => {
    store['sidebar:investigate:open'] = 'false';
    const user = userEvent.setup();
    renderSidebar(regularUser);

    expect(screen.queryByRole('link', { name: /^incidents$/i })).not.toBeInTheDocument();

    await user.type(screen.getByRole('textbox', { name: /filter menu/i }), 'incident');

    expect(screen.getByRole('link', { name: /^incidents$/i })).toBeInTheDocument();
  });

  it('hides sections with no matching items while filtering', async () => {
    const user = userEvent.setup();
    renderSidebar(regularUser);

    await user.type(screen.getByRole('textbox', { name: /filter menu/i }), 'assets');

    expect(screen.queryByRole('button', { name: /^investigate$/i })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^environment$/i })).toBeInTheDocument();
  });

  it('shows an empty state when nothing matches the filter', async () => {
    const user = userEvent.setup();
    renderSidebar(regularUser);

    await user.type(screen.getByRole('textbox', { name: /filter menu/i }), 'zzzz');

    expect(screen.getByText(/no menu items match/i)).toBeInTheDocument();
  });

  it('clear button resets the filter', async () => {
    const user = userEvent.setup();
    renderSidebar(regularUser);

    await user.type(screen.getByRole('textbox', { name: /filter menu/i }), 'vuln');
    await user.click(screen.getByRole('button', { name: /clear filter/i }));

    expect(screen.getByRole('link', { name: /^incidents$/i })).toBeInTheDocument();
    expect(screen.getByRole('textbox', { name: /filter menu/i })).toHaveValue('');
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

  it('hides the filter input in icon-only mode', async () => {
    const user = userEvent.setup();
    renderSidebar(regularUser);

    await user.click(screen.getByRole('button', { name: /collapse sidebar/i }));

    expect(screen.queryByRole('textbox', { name: /filter menu/i })).not.toBeInTheDocument();
  });

  it('shows a dot indicator on badge links in icon-only mode', async () => {
    mockCounts({ alerts: 5 });
    const user = userEvent.setup();
    renderSidebar(regularUser);
    await screen.findByText('5');

    await user.click(screen.getByRole('button', { name: /collapse sidebar/i }));

    const link = screen.getByRole('link', { name: /alert inbox/i });
    expect(within(link).queryByText('5')).not.toBeInTheDocument();
    expect(link.querySelector('.rounded-full')).not.toBeNull();
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

    await user.click(screen.getByRole('button', { name: /^security$/i }));

    expect(JSON.parse(store['sidebar:security:open'])).toBe(false);
  });

  // ── mobile drawer ─────────────────────────────────────────────────────────

  it('mobile-open drawer covers the full viewport height', () => {
    const { container } = renderSidebar(regularUser, '/security', { mobileOpen: true, onMobileClose: () => {} });
    const aside = container.querySelector('aside');
    expect(aside.className).toContain('inset-y-0');
    expect(aside.className).toContain('w-72');
  });

  it('backdrop covers full viewport when mobile sidebar is open', () => {
    const { container } = renderSidebar(regularUser, '/security', { mobileOpen: true, onMobileClose: () => {} });
    const backdrop = container.querySelector('[aria-hidden="true"]');
    expect(backdrop.className).toContain('inset-0');
  });

  it('clicking the backdrop closes the mobile drawer', async () => {
    const onMobileClose = vi.fn();
    const user = userEvent.setup();
    const { container } = renderSidebar(regularUser, '/security', { mobileOpen: true, onMobileClose });

    await user.click(container.querySelector('[aria-hidden="true"]'));

    expect(onMobileClose).toHaveBeenCalled();
  });

  it('shows a close button in the mobile drawer that closes it', async () => {
    const onMobileClose = vi.fn();
    const user = userEvent.setup();
    renderSidebar(regularUser, '/security', { mobileOpen: true, onMobileClose });

    await user.click(screen.getByRole('button', { name: /close menu/i }));

    expect(onMobileClose).toHaveBeenCalled();
  });

  it('closes the mobile drawer when a nav link is clicked', async () => {
    const onMobileClose = vi.fn();
    const user = userEvent.setup();
    renderSidebar(regularUser, '/security', { mobileOpen: true, onMobileClose });

    await user.click(screen.getByRole('link', { name: /^incidents$/i }));

    expect(onMobileClose).toHaveBeenCalled();
  });

  it('closes the mobile drawer on Escape', async () => {
    const onMobileClose = vi.fn();
    const user = userEvent.setup();
    renderSidebar(regularUser, '/security', { mobileOpen: true, onMobileClose });

    await user.keyboard('{Escape}');

    expect(onMobileClose).toHaveBeenCalled();
  });

  it('does not close on Escape when the drawer is not open', async () => {
    const onMobileClose = vi.fn();
    const user = userEvent.setup();
    renderSidebar(regularUser, '/security', { mobileOpen: false, onMobileClose });

    await user.keyboard('{Escape}');

    expect(onMobileClose).not.toHaveBeenCalled();
  });

  it('mobile drawer always shows labels even when desktop icon-only mode is saved', () => {
    store['sidebar:collapsed'] = 'true';
    renderSidebar(regularUser, '/security', { mobileOpen: true, onMobileClose: () => {} });

    expect(screen.getByText('Overview')).toBeInTheDocument();
    expect(screen.getByTestId('org-switcher')).toBeInTheDocument();
  });

  it('does not render the desktop collapse toggle in the mobile drawer', () => {
    renderSidebar(regularUser, '/security', { mobileOpen: true, onMobileClose: () => {} });

    expect(screen.queryByRole('button', { name: /collapse sidebar/i })).not.toBeInTheDocument();
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
