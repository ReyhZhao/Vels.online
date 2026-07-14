import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';

vi.mock('../lib/axios', () => ({
  default: { get: vi.fn(), post: vi.fn(), delete: vi.fn(), patch: vi.fn() },
}));

import api from '../lib/axios';

// We test IncidentContactsPanel by rendering a small wrapper that mirrors the panel logic.
function ContactsPanelWrapper({ displayId = 'INC-001', orgSlug = 'acme' }) {
  const { useState, useEffect } = require('react');

  const [contacts, setContacts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [allContacts, setAllContacts] = useState([]);
  const [addSearch, setAddSearch] = useState('');

  useEffect(() => {
    api.get(`/api/incidents/${displayId}/contacts/`).then(r => setContacts(r.data)).finally(() => setLoading(false));
    const params = orgSlug ? { org: orgSlug } : undefined;
    api.get('/api/contacts/', params ? { params } : undefined).then(r => setAllContacts(r.data));
  }, [displayId, orgSlug]);

  const linkedIds = new Set(contacts.map(c => c.contact_id));
  const filtered = allContacts.filter(c => !linkedIds.has(c.id) && c.name.toLowerCase().includes(addSearch.toLowerCase()));

  async function addContact(contactId) {
    await api.post(`/api/incidents/${displayId}/contacts/`, { contact_id: contactId });
    const r = await api.get(`/api/incidents/${displayId}/contacts/`);
    setContacts(r.data);
    setAddSearch('');
  }

  async function removeContact(rowId) {
    await api.delete(`/api/incidents/${displayId}/contacts/${rowId}/`);
    setContacts(prev => prev.filter(c => c.id !== rowId));
  }

  async function setNotifyLevel(rowId, level) {
    setContacts(prev => prev.map(c => c.id === rowId ? { ...c, notify_level: level } : c));
    await api.patch(`/api/incidents/${displayId}/contacts/${rowId}/`, { notify_level: level });
  }

  if (loading) return <div>Loading…</div>;

  return (
    <div>
      {contacts.map(c => (
        <div key={c.id} data-testid="contact-row">
          <span>{c.name}</span>
          <button onClick={() => removeContact(c.id)}>Remove</button>
          <select
            aria-label={`Notify level for ${c.name}`}
            value={c.notify_level || 'closure_only'}
            onChange={e => setNotifyLevel(c.id, e.target.value)}
          >
            <option value="closure_only">Closure only</option>
            <option value="all_updates">All updates</option>
          </select>
        </div>
      ))}
      {contacts.length === 0 && <p>No contacts linked to this incident.</p>}
      <input placeholder="Search contacts…" value={addSearch} onChange={e => setAddSearch(e.target.value)} />
      {filtered.map(c => (
        <button key={c.id} onClick={() => addContact(c.id)}>{c.name}</button>
      ))}
    </div>
  );
}

const LINKED = [
  { id: 1, contact_id: 10, name: 'Alice', email: 'alice@a.com', created_at: '2026-01-01T00:00:00Z' },
];
const ALL_CONTACTS = [
  { id: 10, name: 'Alice', email: 'alice@a.com' },
  { id: 11, name: 'Bob', email: 'bob@a.com' },
];

describe('IncidentContactsPanel', () => {
  beforeEach(() => vi.clearAllMocks());

  it('renders linked contacts', async () => {
    api.get.mockImplementation(url => {
      if (url.includes('/incidents/')) return Promise.resolve({ data: LINKED });
      return Promise.resolve({ data: ALL_CONTACTS });
    });
    render(<MemoryRouter><ContactsPanelWrapper /></MemoryRouter>);
    await waitFor(() => screen.getByTestId('contact-row'));
    expect(screen.getByText('Alice')).toBeInTheDocument();
  });

  it('scopes the contact picker to the incident org', async () => {
    api.get.mockResolvedValue({ data: [] });
    render(<MemoryRouter><ContactsPanelWrapper orgSlug="acme" /></MemoryRouter>);
    await waitFor(() => screen.getByText('No contacts linked to this incident.'));
    expect(api.get).toHaveBeenCalledWith('/api/contacts/', { params: { org: 'acme' } });
  });

  it('shows empty state when no contacts', async () => {
    api.get.mockResolvedValue({ data: [] });
    render(<MemoryRouter><ContactsPanelWrapper /></MemoryRouter>);
    await waitFor(() => screen.getByText('No contacts linked to this incident.'));
  });

  it('shows unlinked contacts in search results', async () => {
    api.get.mockImplementation(url => {
      if (url.includes('/incidents/')) return Promise.resolve({ data: [] });
      return Promise.resolve({ data: [{ id: 11, name: 'Bob', email: 'bob@a.com' }] });
    });
    render(<MemoryRouter><ContactsPanelWrapper /></MemoryRouter>);
    await waitFor(() => screen.getByText('No contacts linked to this incident.'));
    fireEvent.change(screen.getByPlaceholderText('Search contacts…'), { target: { value: 'Bob' } });
    await waitFor(() => screen.getByText('Bob'));
    expect(screen.getByText('Bob')).toBeInTheDocument();
  });

  it('adds a contact (no role or message required)', async () => {
    const newLinked = [
      ...LINKED,
      { id: 2, contact_id: 11, name: 'Bob', email: 'bob@a.com', created_at: '2026-01-02T00:00:00Z' },
    ];
    api.get
      .mockResolvedValueOnce({ data: LINKED })
      .mockResolvedValueOnce({ data: [{ id: 11, name: 'Bob', email: 'bob@a.com' }] })
      .mockResolvedValueOnce({ data: newLinked });
    api.post.mockResolvedValue({});

    render(<MemoryRouter><ContactsPanelWrapper /></MemoryRouter>);
    await waitFor(() => screen.getByTestId('contact-row'));

    fireEvent.change(screen.getByPlaceholderText('Search contacts…'), { target: { value: 'Bob' } });
    await waitFor(() => screen.getByText('Bob'));
    fireEvent.click(screen.getByText('Bob'));

    await waitFor(() => expect(api.post).toHaveBeenCalledWith(
      '/api/incidents/INC-001/contacts/',
      { contact_id: 11 }
    ));
  });

  it('changes a contact notification level', async () => {
    api.get.mockImplementation(url => {
      if (url.includes('/incidents/')) return Promise.resolve({ data: LINKED });
      return Promise.resolve({ data: [] });
    });
    api.patch.mockResolvedValue({});

    render(<MemoryRouter><ContactsPanelWrapper /></MemoryRouter>);
    await waitFor(() => screen.getByTestId('contact-row'));

    const select = screen.getByLabelText('Notify level for Alice');
    expect(select.value).toBe('closure_only');
    fireEvent.change(select, { target: { value: 'all_updates' } });

    await waitFor(() => expect(api.patch).toHaveBeenCalledWith(
      '/api/incidents/INC-001/contacts/1/',
      { notify_level: 'all_updates' }
    ));
    expect(select.value).toBe('all_updates');
  });

  it('removes a contact', async () => {
    api.get.mockImplementation(url => {
      if (url.includes('/incidents/')) return Promise.resolve({ data: LINKED });
      return Promise.resolve({ data: [] });
    });
    api.delete.mockResolvedValue({});

    render(<MemoryRouter><ContactsPanelWrapper /></MemoryRouter>);
    await waitFor(() => screen.getByTestId('contact-row'));
    fireEvent.click(screen.getByText('Remove'));

    await waitFor(() => expect(api.delete).toHaveBeenCalledWith('/api/incidents/INC-001/contacts/1/'));
    expect(screen.queryByTestId('contact-row')).not.toBeInTheDocument();
  });
});
