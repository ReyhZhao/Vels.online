import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';

import DocsPage from './DocsPage';
import { DOC_SECTIONS } from '../content/siteContent';

function renderPage() {
  return render(
    <MemoryRouter>
      <DocsPage />
    </MemoryRouter>
  );
}

beforeEach(() => {
  // jsdom implements neither; the page uses both for the scroll-spy sidebar.
  vi.stubGlobal(
    'IntersectionObserver',
    class {
      observe() {}
      disconnect() {}
    }
  );
  Element.prototype.scrollIntoView = vi.fn();
});

describe('DocsPage', () => {
  it('renders every article inline, so the handbook is readable and Ctrl-F-able', () => {
    renderPage();

    const total = DOC_SECTIONS.reduce((n, section) => n + section.articles.length, 0);
    expect(document.querySelectorAll('article')).toHaveLength(total);

    // A body paragraph is present without any expanding required.
    expect(screen.getByText(/Polaris uses single sign-on/i)).toBeInTheDocument();
  });

  it('renders markdown emphasis as markup rather than literal asterisks', () => {
    renderPage();

    expect(screen.queryByText(/\*\*/)).not.toBeInTheDocument();
    expect(document.querySelector('article strong')).toBeInTheDocument();
  });

  it('filters both the nav tree and the articles when searching', async () => {
    const user = userEvent.setup();
    renderPage();

    await user.type(screen.getByLabelText(/search the documentation/i), 'risk acceptance');

    const nav = screen.getByRole('navigation', { name: /documentation/i });
    expect(within(nav).getByRole('button', { name: /risk acceptance/i })).toBeInTheDocument();
    expect(within(nav).queryByRole('button', { name: /your first sign-in/i })).not.toBeInTheDocument();
    expect(screen.queryByText(/Polaris uses single sign-on/i)).not.toBeInTheDocument();
  });

  it('tells the reader when a search matches nothing', async () => {
    const user = userEvent.setup();
    renderPage();

    await user.type(screen.getByLabelText(/search the documentation/i), 'zzzznotathing');

    expect(screen.getAllByText(/nothing matches/i).length).toBeGreaterThan(0);
    expect(document.querySelectorAll('article')).toHaveLength(0);
  });

  it('scrolls to an article and marks it current when picked from the tree', async () => {
    const user = userEvent.setup();
    renderPage();

    const nav = screen.getByRole('navigation', { name: /documentation/i });
    const link = within(nav).getByRole('button', { name: /agentic triage/i });
    await user.click(link);

    expect(Element.prototype.scrollIntoView).toHaveBeenCalled();
    expect(link).toHaveAttribute('aria-current', 'true');
  });

  it('links back to the landing page', () => {
    renderPage();

    expect(screen.getByRole('link', { name: /back to polaris security/i })).toHaveAttribute(
      'href',
      '/'
    );
  });
});
