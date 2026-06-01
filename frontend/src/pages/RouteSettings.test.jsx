import { render, screen, waitFor, fireEvent, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';

vi.mock('../lib/axios', () => ({
  default: { get: vi.fn(), patch: vi.fn() },
}));

import api from '../lib/axios';
import RouteSettings from './RouteSettings';

const ROUTE_DATA = {
  fqdn: 'app.example.com',
  name: 'My App',
  backend_host: '10.0.0.1',
  backend_port: 8080,
  backend_protocol: 'http',
  status: 'active',
};

const BW_SETTINGS = {
  USE_MODSECURITY: 'yes',
  USE_MODSECURITY_CRS: 'no',
  MODSECURITY_CRS_PARANOIA_LEVEL: '3',
  USE_WHITELIST: 'yes',
  WHITELIST_IP: '10.0.0.0/8 192.168.1.1',
  USE_LIMIT_REQ: 'yes',
  LIMIT_REQ_RATE: '10r/s',
  LIMIT_REQ_BURST: '20',
  BLACKLIST_COUNTRY: 'CN RU',
  WHITELIST_COUNTRY: 'GB US',
  USE_ANTIBOT: 'no',
  ANTIBOT_TYPE: 'cookie',
};

function setupMocks(bwData = BW_SETTINGS, routeData = ROUTE_DATA) {
  api.get.mockImplementation(url => {
    if (url.endsWith('/settings/')) return Promise.resolve({ data: bwData });
    return Promise.resolve({ data: routeData });
  });
}

function renderPage(fqdn = 'app.example.com') {
  return render(
    <MemoryRouter>
      <RouteSettings fqdn={fqdn} />
    </MemoryRouter>
  );
}

async function waitForLoad() {
  await waitFor(() => expect(screen.queryByText('Loading settings…')).not.toBeInTheDocument());
}

describe('RouteSettings shell', () => {
  beforeEach(() => { vi.clearAllMocks(); });

  it('shows loading state while fetching', () => {
    api.get.mockReturnValue(new Promise(() => {}));
    renderPage();
    expect(screen.getByText('Loading settings…')).toBeInTheDocument();
  });

  it('shows error when load fails', async () => {
    api.get.mockRejectedValue(new Error('network error'));
    renderPage();
    await waitFor(() =>
      expect(screen.getByText('Failed to load settings.')).toBeInTheDocument()
    );
  });

  it('renders 7 sub-tabs after loading', async () => {
    setupMocks();
    renderPage();
    await waitForLoad();
    expect(screen.getByTestId('subtab-general')).toBeInTheDocument();
    expect(screen.getByTestId('subtab-waf')).toBeInTheDocument();
    expect(screen.getByTestId('subtab-ip-whitelist')).toBeInTheDocument();
    expect(screen.getByTestId('subtab-rate-limiting')).toBeInTheDocument();
    expect(screen.getByTestId('subtab-country')).toBeInTheDocument();
    expect(screen.getByTestId('subtab-bot-protection')).toBeInTheDocument();
    expect(screen.getByTestId('subtab-advanced')).toBeInTheDocument();
  });

  it('shows General tab by default', async () => {
    setupMocks();
    renderPage();
    await waitForLoad();
    expect(screen.getByTestId('fqdn-display')).toBeInTheDocument();
  });

  it('shows sync warning when BunkerWeb returns empty settings', async () => {
    api.get.mockImplementation(url => {
      if (url.endsWith('/settings/')) return Promise.resolve({ data: {} });
      return Promise.resolve({ data: ROUTE_DATA });
    });
    renderPage();
    await waitFor(() =>
      expect(screen.getByTestId('sync-warning')).toBeInTheDocument()
    );
  });
});

describe('GeneralTab', () => {
  beforeEach(() => { vi.clearAllMocks(); });

  it('pre-populates fields from route GET response', async () => {
    setupMocks();
    renderPage();
    await waitForLoad();
    expect(screen.getByTestId('input-name')).toHaveValue('My App');
    expect(screen.getByTestId('input-backend_host')).toHaveValue('10.0.0.1');
    expect(screen.getByTestId('input-backend_port')).toHaveValue(8080);
    expect(screen.getByTestId('select-backend_protocol')).toHaveValue('http');
  });

  it('shows FQDN as read-only text, not an input', async () => {
    setupMocks();
    renderPage();
    await waitForLoad();
    const fqdnDisplay = screen.getByTestId('fqdn-display');
    expect(fqdnDisplay.tagName).not.toBe('INPUT');
    expect(fqdnDisplay).toHaveTextContent('app.example.com');
  });

  it('saves via PATCH /api/ingress/routes/<fqdn>/ with correct payload', async () => {
    setupMocks();
    api.patch.mockResolvedValue({ data: ROUTE_DATA });
    renderPage();
    await waitForLoad();

    fireEvent.change(screen.getByTestId('input-name'), { target: { value: 'Updated Name' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() => {
      expect(api.patch).toHaveBeenCalledWith(
        '/api/ingress/routes/app.example.com/',
        expect.objectContaining({ name: 'Updated Name' }),
      );
    });
  });

  it('shows success toast after General save', async () => {
    setupMocks();
    api.patch.mockResolvedValue({ data: ROUTE_DATA });
    renderPage();
    await waitForLoad();
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() =>
      expect(screen.getByTestId('toast')).toHaveTextContent('Route saved.')
    );
  });

  it('shows dirty dot when field is changed', async () => {
    setupMocks();
    renderPage();
    await waitForLoad();
    expect(screen.queryByTestId('dirty-dot-general')).not.toBeInTheDocument();
    fireEvent.change(screen.getByTestId('input-name'), { target: { value: 'Changed' } });
    await waitFor(() =>
      expect(screen.getByTestId('dirty-dot-general')).toBeInTheDocument()
    );
  });

  it('removes dirty dot after save', async () => {
    setupMocks();
    api.patch.mockResolvedValue({ data: ROUTE_DATA });
    renderPage();
    await waitForLoad();
    fireEvent.change(screen.getByTestId('input-name'), { target: { value: 'Changed' } });
    await waitFor(() => screen.getByTestId('dirty-dot-general'));
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() =>
      expect(screen.queryByTestId('dirty-dot-general')).not.toBeInTheDocument()
    );
  });
});

describe('WafTab', () => {
  beforeEach(() => { vi.clearAllMocks(); });

  it('renders with WAF values pre-populated', async () => {
    setupMocks();
    renderPage();
    await waitForLoad();
    fireEvent.click(screen.getByTestId('subtab-waf'));
    await waitFor(() => {
      expect(screen.getByTestId('toggle-USE_MODSECURITY')).toHaveAttribute('aria-checked', 'true');
      expect(screen.getByTestId('toggle-USE_MODSECURITY_CRS')).toHaveAttribute('aria-checked', 'false');
      expect(screen.getByTestId('paranoia-level-3')).toHaveAttribute('aria-pressed', 'true');
    });
  });

  it('renders HTTPS redirect toggle', async () => {
    setupMocks();
    renderPage();
    await waitForLoad();
    fireEvent.click(screen.getByTestId('subtab-waf'));
    await waitFor(() =>
      expect(screen.getByTestId('toggle-USE_REDIRECT_HTTP_TO_HTTPS')).toBeInTheDocument()
    );
  });

  it('segmented paranoia control switches level on click', async () => {
    setupMocks();
    renderPage();
    await waitForLoad();
    fireEvent.click(screen.getByTestId('subtab-waf'));
    await waitFor(() => screen.getByTestId('paranoia-level-2'));
    fireEvent.click(screen.getByTestId('paranoia-level-2'));
    expect(screen.getByTestId('paranoia-level-2')).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByTestId('paranoia-level-3')).toHaveAttribute('aria-pressed', 'false');
  });

  it('saves via PATCH /settings/ when WAF Save clicked', async () => {
    setupMocks();
    api.patch.mockResolvedValue({ data: {} });
    renderPage();
    await waitForLoad();
    fireEvent.click(screen.getByTestId('subtab-waf'));
    await waitFor(() => screen.getByRole('button', { name: 'Save' }));
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() =>
      expect(api.patch).toHaveBeenCalledWith(
        '/api/ingress/routes/app.example.com/settings/',
        expect.objectContaining({ USE_MODSECURITY: 'yes' }),
      )
    );
  });
});

describe('IpWhitelistTab', () => {
  beforeEach(() => { vi.clearAllMocks(); });

  async function openTab() {
    setupMocks();
    renderPage();
    await waitForLoad();
    fireEvent.click(screen.getByTestId('subtab-ip-whitelist'));
    await waitFor(() => screen.getByTestId('ip-chip-list'));
  }

  it('loads existing IPs as chips', async () => {
    await openTab();
    expect(screen.getByTestId('ip-chip-0')).toHaveTextContent('10.0.0.0/8');
    expect(screen.getByTestId('ip-chip-1')).toHaveTextContent('192.168.1.1');
  });

  it('adds a valid IP chip on button click', async () => {
    await openTab();
    fireEvent.change(screen.getByTestId('ip-add-input'), { target: { value: '10.1.1.0/24' } });
    fireEvent.click(screen.getByTestId('ip-add-button'));
    await waitFor(() => screen.getByTestId('ip-chip-2'));
    expect(screen.getByTestId('ip-chip-2')).toHaveTextContent('10.1.1.0/24');
  });

  it('shows inline error for invalid IP and does not add chip', async () => {
    await openTab();
    fireEvent.change(screen.getByTestId('ip-add-input'), { target: { value: 'not-an-ip' } });
    fireEvent.click(screen.getByTestId('ip-add-button'));
    expect(screen.getByTestId('ip-input-error')).toBeInTheDocument();
    expect(screen.queryByTestId('ip-chip-2')).not.toBeInTheDocument();
  });

  it('shows cap message when 10 chips are present', async () => {
    const tenIPs = Array.from({ length: 10 }, (_, i) => `10.0.0.${i + 1}`).join(' ');
    api.get.mockImplementation(url => {
      if (url.endsWith('/settings/')) return Promise.resolve({ data: { WHITELIST_IP: tenIPs } });
      return Promise.resolve({ data: ROUTE_DATA });
    });
    renderPage();
    await waitForLoad();
    fireEvent.click(screen.getByTestId('subtab-ip-whitelist'));
    await waitFor(() =>
      expect(screen.getByTestId('ip-cap-message')).toBeInTheDocument()
    );
    expect(screen.queryByTestId('ip-add-input')).not.toBeInTheDocument();
  });

  it('adding an 11th chip does not add (cap reached)', async () => {
    const tenIPs = Array.from({ length: 10 }, (_, i) => `10.0.0.${i + 1}`).join(' ');
    api.get.mockImplementation(url => {
      if (url.endsWith('/settings/')) return Promise.resolve({ data: { WHITELIST_IP: tenIPs } });
      return Promise.resolve({ data: ROUTE_DATA });
    });
    renderPage();
    await waitForLoad();
    fireEvent.click(screen.getByTestId('subtab-ip-whitelist'));
    await waitFor(() => screen.getByTestId('ip-cap-message'));
    // No add input visible — add button gone
    expect(screen.queryByTestId('ip-add-button')).not.toBeInTheDocument();
  });

  it('removes a chip when × clicked', async () => {
    await openTab();
    const removeBtn = screen.getByRole('button', { name: 'Remove 10.0.0.0/8' });
    fireEvent.click(removeBtn);
    await waitFor(() =>
      expect(screen.queryByRole('button', { name: 'Remove 10.0.0.0/8' })).not.toBeInTheDocument()
    );
  });

  it('save sends WHITELIST_IP as space-separated string', async () => {
    setupMocks();
    api.patch.mockResolvedValue({ data: {} });
    renderPage();
    await waitForLoad();
    fireEvent.click(screen.getByTestId('subtab-ip-whitelist'));
    await waitFor(() => screen.getByRole('button', { name: 'Save' }));
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() =>
      expect(api.patch).toHaveBeenCalledWith(
        '/api/ingress/routes/app.example.com/settings/',
        expect.objectContaining({ WHITELIST_IP: '10.0.0.0/8 192.168.1.1' }),
      )
    );
  });
});

describe('RateLimitingTab', () => {
  beforeEach(() => { vi.clearAllMocks(); });

  async function openTab() {
    setupMocks();
    renderPage();
    await waitForLoad();
    fireEvent.click(screen.getByTestId('subtab-rate-limiting'));
    await waitFor(() => screen.getByTestId('input-LIMIT_REQ_RATE_NUM'));
  }

  it('splits LIMIT_REQ_RATE into number and unit fields', async () => {
    await openTab();
    expect(screen.getByTestId('input-LIMIT_REQ_RATE_NUM')).toHaveValue(10);
    expect(screen.getByTestId('select-LIMIT_REQ_RATE_UNIT')).toHaveValue('r/s');
  });

  it('combines number and unit into correct format on save', async () => {
    setupMocks();
    api.patch.mockResolvedValue({ data: {} });
    renderPage();
    await waitForLoad();
    fireEvent.click(screen.getByTestId('subtab-rate-limiting'));
    await waitFor(() => screen.getByTestId('input-LIMIT_REQ_RATE_NUM'));

    fireEvent.change(screen.getByTestId('input-LIMIT_REQ_RATE_NUM'), { target: { value: '5' } });
    fireEvent.change(screen.getByTestId('select-LIMIT_REQ_RATE_UNIT'), { target: { value: 'r/m' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() =>
      expect(api.patch).toHaveBeenCalledWith(
        '/api/ingress/routes/app.example.com/settings/',
        expect.objectContaining({ LIMIT_REQ_RATE: '5r/m' }),
      )
    );
  });

  it('unit dropdown contains exactly r/s, r/m, r/h', async () => {
    await openTab();
    const select = screen.getByTestId('select-LIMIT_REQ_RATE_UNIT');
    const options = Array.from(select.options).map(o => o.value);
    expect(options).toEqual(['r/s', 'r/m', 'r/h']);
  });

  it('shows validation error if rate limiting enabled but number is empty', async () => {
    // Start with rate limiting enabled (USE_LIMIT_REQ: 'yes') from BW_SETTINGS
    setupMocks();
    api.patch.mockResolvedValue({ data: {} });
    renderPage();
    await waitForLoad();
    fireEvent.click(screen.getByTestId('subtab-rate-limiting'));
    await waitFor(() => screen.getByTestId('input-LIMIT_REQ_RATE_NUM'));

    // Toggle IS already 'yes'; clear the rate number then try to save
    fireEvent.change(screen.getByTestId('input-LIMIT_REQ_RATE_NUM'), { target: { value: '' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() =>
      expect(screen.getByTestId('rate-error')).toBeInTheDocument()
    );
  });
});

describe('BotProtectionTab', () => {
  beforeEach(() => { vi.clearAllMocks(); });

  async function openTab(botSettings = {}) {
    api.get.mockImplementation(url => {
      if (url.endsWith('/settings/')) return Promise.resolve({ data: { ...BW_SETTINGS, ...botSettings } });
      return Promise.resolve({ data: ROUTE_DATA });
    });
    renderPage();
    await waitForLoad();
    fireEvent.click(screen.getByTestId('subtab-bot-protection'));
    await waitFor(() => screen.getByTestId('select-ANTIBOT_TYPE'));
  }

  it('renders enable toggle and type selector', async () => {
    await openTab();
    expect(screen.getByTestId('toggle-USE_ANTIBOT')).toBeInTheDocument();
    expect(screen.getByTestId('select-ANTIBOT_TYPE')).toBeInTheDocument();
  });

  it('shows no credential fields for cookie type', async () => {
    await openTab({ ANTIBOT_TYPE: 'cookie' });
    expect(screen.queryByTestId('recaptcha-fields')).not.toBeInTheDocument();
    expect(screen.queryByTestId('hcaptcha-fields')).not.toBeInTheDocument();
    expect(screen.queryByTestId('turnstile-fields')).not.toBeInTheDocument();
  });

  it('shows reCAPTCHA fields when recaptcha selected', async () => {
    await openTab({ ANTIBOT_TYPE: 'cookie' });
    fireEvent.change(screen.getByTestId('select-ANTIBOT_TYPE'), { target: { value: 'recaptcha' } });
    expect(screen.getByTestId('recaptcha-fields')).toBeInTheDocument();
    expect(screen.queryByTestId('hcaptcha-fields')).not.toBeInTheDocument();
  });

  it('shows hCaptcha fields when hcaptcha selected', async () => {
    await openTab({ ANTIBOT_TYPE: 'cookie' });
    fireEvent.change(screen.getByTestId('select-ANTIBOT_TYPE'), { target: { value: 'hcaptcha' } });
    expect(screen.getByTestId('hcaptcha-fields')).toBeInTheDocument();
    expect(screen.queryByTestId('recaptcha-fields')).not.toBeInTheDocument();
  });

  it('shows Turnstile fields when turnstile selected', async () => {
    await openTab({ ANTIBOT_TYPE: 'cookie' });
    fireEvent.change(screen.getByTestId('select-ANTIBOT_TYPE'), { target: { value: 'turnstile' } });
    expect(screen.getByTestId('turnstile-fields')).toBeInTheDocument();
  });

  it('hides credential fields when switching back to javascript', async () => {
    await openTab({ ANTIBOT_TYPE: 'recaptcha' });
    expect(screen.getByTestId('recaptcha-fields')).toBeInTheDocument();
    fireEvent.change(screen.getByTestId('select-ANTIBOT_TYPE'), { target: { value: 'javascript' } });
    expect(screen.queryByTestId('recaptcha-fields')).not.toBeInTheDocument();
  });
});

describe('Unsaved indicator across tabs', () => {
  beforeEach(() => { vi.clearAllMocks(); });

  it('dirty dot appears when field edited, disappears after save', async () => {
    setupMocks();
    api.patch.mockResolvedValue({ data: ROUTE_DATA });
    renderPage();
    await waitForLoad();

    // Edit in General tab
    fireEvent.change(screen.getByTestId('input-name'), { target: { value: 'Changed' } });
    await waitFor(() => screen.getByTestId('dirty-dot-general'));

    // Save
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() =>
      expect(screen.queryByTestId('dirty-dot-general')).not.toBeInTheDocument()
    );
  });

  it('switching to another tab preserves dirty state on first tab', async () => {
    setupMocks();
    renderPage();
    await waitForLoad();

    // Edit General tab
    fireEvent.change(screen.getByTestId('input-name'), { target: { value: 'Changed' } });
    await waitFor(() => screen.getByTestId('dirty-dot-general'));

    // Switch to WAF tab
    fireEvent.click(screen.getByTestId('subtab-waf'));
    await waitFor(() => screen.getByTestId('toggle-USE_MODSECURITY'));

    // Dot still on General tab
    expect(screen.getByTestId('dirty-dot-general')).toBeInTheDocument();
  });
});
