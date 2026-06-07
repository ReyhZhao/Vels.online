import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';

vi.mock('../lib/axios', () => ({
  default: { get: vi.fn(), post: vi.fn() },
}));

vi.mock('../context/OrgContext', () => ({
  useOrganization: () => ({ selectedOrg: { slug: 'acme' } }),
}));

import api from '../lib/axios';
import ContactsPage from './ContactsPage';

const CONTACTS = [
  { id: 1, name: 'Alice Smith', email: 'alice@acme.com', job_title: 'Analyst', department: 'SOC', created_at: '2026-01-01T00:00:00Z' },
  { id: 2, name: 'Bob Jones', email: 'bob@acme.com', job_title: 'Manager', department: 'IT', created_at: '2026-01-02T00:00:00Z' },
];

function renderPage() {
  return render(
    <MemoryRouter>
      <ContactsPage />
    </MemoryRouter>
  );
}

describe('ContactsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows loading state while fetching', () => {
    api.get.mockReturnValue(new Promise(() => {}));
    renderPage();
    expect(screen.getByText('Loading…')).toBeInTheDocument();
  });

  it('renders contact list after load', async () => {
    api.get.mockResolvedValue({ data: CONTACTS });
    renderPage();
    await waitFor(() => expect(screen.getByText('Alice Smith')).toBeInTheDocument());
    expect(screen.getByText('bob@acme.com')).toBeInTheDocument();
  });

  it('shows empty state when no contacts', async () => {
    api.get.mockResolvedValue({ data: [] });
    renderPage();
    await waitFor(() => expect(screen.getByText('No contacts yet.')).toBeInTheDocument());
  });

  it('filters contacts by search input', async () => {
    api.get.mockResolvedValue({ data: CONTACTS });
    renderPage();
    await waitFor(() => screen.getByText('Alice Smith'));
    fireEvent.change(screen.getByPlaceholderText('Search contacts…'), { target: { value: 'bob' } });
    expect(screen.queryByText('Alice Smith')).not.toBeInTheDocument();
    expect(screen.getByText('Bob Jones')).toBeInTheDocument();
  });

  it('opens create modal when New Contact is clicked', async () => {
    api.get.mockResolvedValue({ data: CONTACTS });
    renderPage();
    await waitFor(() => screen.getByText('Alice Smith'));
    fireEvent.click(screen.getByText('New Contact'));
    expect(screen.getByText('New Contact', { selector: 'h2' })).toBeInTheDocument();
  });

  it('defaults to current-org filter then toggles to all contacts with org column', async () => {
    api.get.mockResolvedValue({ data: [{ ...CONTACTS[0], org_slug: 'acme', org_name: 'Acme' }] });
    renderPage();
    await waitFor(() => screen.getByText('Alice Smith'));
    // default request scopes to the selected org
    expect(api.get).toHaveBeenCalledWith('/api/contacts/', { params: { org: 'acme' } });
    // no org column in current-org mode
    expect(screen.queryByText('Organisation')).not.toBeInTheDocument();
    // toggle to all contacts
    fireEvent.click(screen.getByText('All contacts'));
    await waitFor(() => expect(api.get).toHaveBeenCalledWith('/api/contacts/', { params: {} }));
    expect(screen.getByText('Organisation')).toBeInTheDocument();
    expect(screen.getByText('Acme')).toBeInTheDocument();
  });

  it('creates a contact and adds it to the list', async () => {
    api.get.mockResolvedValue({ data: [] });
    api.post.mockResolvedValue({ data: { id: 3, name: 'Carol White', email: 'carol@acme.com', job_title: '', department: '', created_at: '2026-01-03T00:00:00Z' } });
    renderPage();
    await waitFor(() => screen.getByText('No contacts yet.'));
    fireEvent.click(screen.getByText('New Contact'));
    fireEvent.change(screen.getByLabelText('Name *'), { target: { value: 'Carol White' } });
    fireEvent.change(screen.getByLabelText('Email *'), { target: { value: 'carol@acme.com' } });
    fireEvent.click(screen.getByText('Create'));
    await waitFor(() => expect(screen.getByText('Carol White')).toBeInTheDocument());
  });
});
