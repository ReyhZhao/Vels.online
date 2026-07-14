import { render, screen, waitFor, within } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('../lib/axios', () => ({
  default: { get: vi.fn() },
}));

import api from '../lib/axios';
import AttachmentPreviewModal from './AttachmentPreviewModal';

const noop = () => {};

describe('AttachmentPreviewModal', () => {
  beforeEach(() => vi.clearAllMocks());

  it('renders an image preview from the inline url', async () => {
    api.get.mockResolvedValue({ data: { kind: 'image', url: 'https://s3.example.com/pic', content_type: 'image/png' } });
    render(<AttachmentPreviewModal incidentId="1" attachment={{ id: 5, filename: 'pic.png' }} onClose={noop} />);
    const img = await screen.findByAltText('pic.png');
    expect(img).toHaveAttribute('src', 'https://s3.example.com/pic');
  });

  it('renders a plain-text email body without an iframe', async () => {
    api.get.mockResolvedValue({
      data: {
        kind: 'email',
        email: {
          headers: { from: 'a@evil.example', subject: 'You won' },
          text_body: 'plain body text',
          html_body: '',
          inner_attachments: [{ filename: 'x.docx', content_type: 'application/octet-stream', size_bytes: 12 }],
        },
      },
    });
    render(<AttachmentPreviewModal incidentId="1" attachment={{ id: 6, filename: 'mail.eml' }} onClose={noop} />);
    expect(await screen.findByText('plain body text')).toBeInTheDocument();
    expect(screen.getByText('a@evil.example')).toBeInTheDocument();
    expect(screen.getByText('x.docx')).toBeInTheDocument();
  });

  it('renders an HTML email body in a script-less sandboxed iframe with a remote-blocking CSP', async () => {
    api.get.mockResolvedValue({
      data: {
        kind: 'email',
        email: {
          headers: { subject: 'phish' },
          text_body: '',
          html_body: '<p>hi</p><img src="http://tracker.example/pixel.gif">',
          inner_attachments: [],
        },
      },
    });
    const { container } = render(
      <AttachmentPreviewModal incidentId="1" attachment={{ id: 7, filename: 'phish.eml' }} onClose={noop} />
    );
    const iframe = await waitFor(() => {
      const el = container.querySelector('iframe[title="Email body"]');
      if (!el) throw new Error('iframe not rendered yet');
      return el;
    });
    // sandbox with no allow-scripts token: scripts cannot run.
    expect(iframe.getAttribute('sandbox')).toBe('');
    const srcdoc = iframe.getAttribute('srcdoc');
    // remote loads are forbidden by CSP (only data: images), so tracking pixels never fire.
    expect(srcdoc).toContain("default-src 'none'");
    expect(srcdoc).toContain('img-src data:');
    // the untrusted html is confined to the srcdoc, never rendered as live DOM.
    expect(container.querySelector('img[src*="tracker.example"]')).toBeNull();
  });
});
