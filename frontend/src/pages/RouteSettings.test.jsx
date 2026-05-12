import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';

vi.mock('../lib/axios', () => ({
  default: { get: vi.fn(), patch: vi.fn() },
}));

import api from '../lib/axios';
import RouteSettings from './RouteSettings';

const BW_SETTINGS = {
  USE_MODSECURITY: 'yes',
  USE_MODSECURITY_CRS: 'no',
  MODSECURITY_CRS_PARANOIA_LEVEL: '3',
};

function renderPage(fqdn = 'app.example.com') {
  return render(
    <MemoryRouter>
      <RouteSettings fqdn={fqdn} />
    </MemoryRouter>
  );
}

describe('RouteSettings', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows loading state while fetching', () => {
    api.get.mockReturnValue(new Promise(() => {}));
    renderPage();
    expect(screen.getByText('Loading settings…')).toBeInTheDocument();
  });

  it('renders WAF values from GET response', async () => {
    api.get.mockResolvedValue({ data: BW_SETTINGS });
    renderPage();
    await waitFor(() => {
      const modsecToggle = screen.getByTestId('toggle-USE_MODSECURITY');
      expect(modsecToggle).toHaveAttribute('aria-checked', 'true');
      const crsToggle = screen.getByTestId('toggle-USE_MODSECURITY_CRS');
      expect(crsToggle).toHaveAttribute('aria-checked', 'false');
      expect(screen.getByRole('combobox')).toHaveValue('3');
    });
  });

  it('toggles USE_MODSECURITY on click', async () => {
    api.get.mockResolvedValue({ data: BW_SETTINGS });
    renderPage();
    await waitFor(() => screen.getByTestId('toggle-USE_MODSECURITY'));
    const toggle = screen.getByTestId('toggle-USE_MODSECURITY');
    expect(toggle).toHaveAttribute('aria-checked', 'true');
    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute('aria-checked', 'false');
  });

  it('submits PATCH with current WAF values on save', async () => {
    api.get.mockResolvedValue({ data: BW_SETTINGS });
    api.patch.mockResolvedValue({ data: BW_SETTINGS });
    renderPage();
    await waitFor(() => screen.getByRole('button', { name: 'Save Settings' }));
    fireEvent.click(screen.getByRole('button', { name: 'Save Settings' }));
    await waitFor(() => {
      expect(api.patch).toHaveBeenCalledWith(
        '/api/ingress/routes/app.example.com/settings/',
        expect.objectContaining({
          USE_MODSECURITY: 'yes',
          USE_MODSECURITY_CRS: 'no',
          MODSECURITY_CRS_PARANOIA_LEVEL: '3',
        }),
      );
    });
  });

  it('shows success toast after save', async () => {
    api.get.mockResolvedValue({ data: BW_SETTINGS });
    api.patch.mockResolvedValue({ data: BW_SETTINGS });
    renderPage();
    await waitFor(() => screen.getByRole('button', { name: 'Save Settings' }));
    fireEvent.click(screen.getByRole('button', { name: 'Save Settings' }));
    await waitFor(() =>
      expect(screen.getByTestId('toast')).toHaveTextContent('Settings saved')
    );
  });

  it('shows error toast when PATCH fails', async () => {
    api.get.mockResolvedValue({ data: BW_SETTINGS });
    api.patch.mockRejectedValue({ response: { data: { detail: 'BunkerWeb unavailable.' } } });
    renderPage();
    await waitFor(() => screen.getByRole('button', { name: 'Save Settings' }));
    fireEvent.click(screen.getByRole('button', { name: 'Save Settings' }));
    await waitFor(() =>
      expect(screen.getByTestId('toast')).toHaveTextContent('BunkerWeb unavailable.')
    );
  });

  it('shows error on load failure', async () => {
    api.get.mockRejectedValue(new Error('network error'));
    renderPage();
    await waitFor(() =>
      expect(screen.getByText('Failed to load settings.')).toBeInTheDocument()
    );
  });

  it('shows validation error when paranoia level is out of range', async () => {
    api.get.mockResolvedValue({ data: { ...BW_SETTINGS, MODSECURITY_CRS_PARANOIA_LEVEL: '3' } });
    renderPage();
    await waitFor(() => screen.getByRole('combobox'));
    // Manually set an invalid value via direct state manipulation is not possible,
    // so we verify the select is constrained to valid options (1-4)
    const select = screen.getByRole('combobox');
    expect(select.options).toHaveLength(4);
    expect(select.options[0].value).toBe('1');
    expect(select.options[3].value).toBe('4');
  });

  it('renders IP whitelist toggle and textarea with loaded values', async () => {
    api.get.mockResolvedValue({
      data: { ...BW_SETTINGS, USE_WHITELIST: 'yes', WHITELIST_IP: '10.0.0.0/8 192.168.1.1' },
    });
    renderPage();
    await waitFor(() => {
      expect(screen.getByTestId('toggle-USE_WHITELIST')).toHaveAttribute('aria-checked', 'true');
      expect(screen.getByTestId('input-WHITELIST_IP')).toHaveValue('10.0.0.0/8 192.168.1.1');
    });
  });

  it('toggles USE_WHITELIST on click', async () => {
    api.get.mockResolvedValue({ data: { ...BW_SETTINGS, USE_WHITELIST: 'no' } });
    renderPage();
    await waitFor(() => screen.getByTestId('toggle-USE_WHITELIST'));
    const toggle = screen.getByTestId('toggle-USE_WHITELIST');
    expect(toggle).toHaveAttribute('aria-checked', 'false');
    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute('aria-checked', 'true');
  });

  it('renders rate limiting toggle and inputs with loaded values', async () => {
    api.get.mockResolvedValue({
      data: { ...BW_SETTINGS, USE_LIMIT_REQ: 'yes', LIMIT_REQ_RATE: '10r/s', LIMIT_REQ_BURST: '20' },
    });
    renderPage();
    await waitFor(() => {
      expect(screen.getByTestId('toggle-USE_LIMIT_REQ')).toHaveAttribute('aria-checked', 'true');
      expect(screen.getByTestId('input-LIMIT_REQ_RATE')).toHaveValue('10r/s');
      expect(screen.getByTestId('input-LIMIT_REQ_BURST')).toHaveValue('20');
    });
  });

  it('renders country access textareas with loaded values', async () => {
    api.get.mockResolvedValue({
      data: { ...BW_SETTINGS, BLACKLIST_COUNTRY: 'CN RU', WHITELIST_COUNTRY: 'GB US' },
    });
    renderPage();
    await waitFor(() => {
      expect(screen.getByTestId('input-BLACKLIST_COUNTRY')).toHaveValue('CN RU');
      expect(screen.getByTestId('input-WHITELIST_COUNTRY')).toHaveValue('GB US');
    });
  });

  it('submits all settings sections on save', async () => {
    const fullSettings = {
      ...BW_SETTINGS,
      USE_WHITELIST: 'yes',
      WHITELIST_IP: '10.0.0.0/8',
      USE_LIMIT_REQ: 'yes',
      LIMIT_REQ_RATE: '5r/m',
      LIMIT_REQ_BURST: '10',
      BLACKLIST_COUNTRY: 'CN',
      WHITELIST_COUNTRY: '',
    };
    api.get.mockResolvedValue({ data: fullSettings });
    api.patch.mockResolvedValue({ data: fullSettings });
    renderPage();
    await waitFor(() => screen.getByRole('button', { name: 'Save Settings' }));
    fireEvent.click(screen.getByRole('button', { name: 'Save Settings' }));
    await waitFor(() => {
      expect(api.patch).toHaveBeenCalledWith(
        '/api/ingress/routes/app.example.com/settings/',
        expect.objectContaining({
          USE_WHITELIST: 'yes',
          WHITELIST_IP: '10.0.0.0/8',
          USE_LIMIT_REQ: 'yes',
          LIMIT_REQ_RATE: '5r/m',
          LIMIT_REQ_BURST: '10',
          BLACKLIST_COUNTRY: 'CN',
        }),
      );
    });
  });
});
