import { act, renderHook, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('../lib/axios', () => ({
  default: { get: vi.fn() },
}));

vi.mock('./AuthContext', () => ({
  useAuth: () => ({ user: null }),
}));

import api from '../lib/axios';
import { OrgContext, OrgProvider, useOrganization } from './OrgContext';

const ORGS = [
  { id: 1, name: 'Acme', slug: 'acme', wazuh_group: 'acme' },
  { id: 2, name: 'Contoso', slug: 'contoso', wazuh_group: 'contoso' },
];

const wrapper = ({ children }) => <OrgProvider>{children}</OrgProvider>;

describe('useOrganization', () => {
  beforeEach(() => vi.clearAllMocks());

  it('starts in loading state with no selected org', () => {
    api.get.mockReturnValue(new Promise(() => {}));
    const { result } = renderHook(() => useOrganization(), { wrapper });
    expect(result.current.isLoading).toBe(true);
    expect(result.current.selectedOrg).toBeNull();
  });

  it('fetches orgs and defaults to the first one', async () => {
    api.get.mockResolvedValue({ data: ORGS });
    const { result } = renderHook(() => useOrganization(), { wrapper });

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(result.current.orgs).toHaveLength(2);
    expect(result.current.selectedOrg.slug).toBe('acme');
    expect(api.get).toHaveBeenCalledWith('/api/security/organizations/');
  });

  it('handles empty org list gracefully', async () => {
    api.get.mockResolvedValue({ data: [] });
    const { result } = renderHook(() => useOrganization(), { wrapper });

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(result.current.orgs).toHaveLength(0);
    expect(result.current.selectedOrg).toBeNull();
  });

  it('handles fetch error gracefully', async () => {
    api.get.mockRejectedValue(new Error('Network error'));
    const { result } = renderHook(() => useOrganization(), { wrapper });

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(result.current.orgs).toHaveLength(0);
    expect(result.current.selectedOrg).toBeNull();
  });

  it('setSelectedOrg updates the selected org', async () => {
    api.get.mockResolvedValue({ data: ORGS });
    const { result } = renderHook(() => useOrganization(), { wrapper });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.selectedOrg.slug).toBe('acme');

    act(() => result.current.setSelectedOrg(ORGS[1]));

    expect(result.current.selectedOrg.slug).toBe('contoso');
  });
});
